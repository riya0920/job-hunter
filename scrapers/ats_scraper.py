"""
Direct ATS API scrapers — Greenhouse, Lever, Ashby, SmartRecruiters, Workday.
These are public, unauthenticated JSON APIs — the SOURCE OF TRUTH, hit before a
job is ever syndicated to LinkedIn/Indeed.

Every board is scraped CONCURRENTLY (one task per company) so a full sweep of
hundreds of boards finishes in seconds — that's what makes a 5-minute cron mean
"within seconds of posting."
"""

import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from tenacity import retry, stop_after_attempt, wait_exponential

# How many boards to fetch in parallel. Kept modest to stay polite.
MAX_WORKERS = 16

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
def _get_json(url: str, timeout: int = 30):
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _get_json_safe(url: str, timeout: int = 30):
    try:
        return _get_json(url, timeout)
    except Exception:
        return None


def _post_json_safe(url: str, payload: dict, timeout: int = 30):
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={**_HEADERS, "Content-Type": "application/json"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _parse_date(date_str: str):
    """Best-effort parse of an ISO / epoch-ms / relative date into aware UTC datetime.

    Returns None if it can't be parsed confidently.
    """
    if not date_str or str(date_str) in ("None", "nan", ""):
        return None
    s = str(date_str).strip()

    # ISO 8601
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        pass

    # Epoch milliseconds (Lever)
    try:
        ts = int(s) / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, TypeError):
        pass

    # Workday-style relative text: "Posted Today", "Posted Yesterday",
    # "Posted 3 Days Ago"
    low = s.lower()
    now = datetime.now(timezone.utc)
    if "today" in low:
        return now
    if "yesterday" in low:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*day", low)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\+?\s*hour", low)
    if m:
        return now - timedelta(hours=int(m.group(1)))

    return None


def _too_old(date_str: str, max_hours: int) -> bool:
    """True only when we can CONFIDENTLY tell the post is older than max_hours.

    If the date is unparseable we return False (keep it) and let dedup +
    cold-start handle it.
    """
    dt = _parse_date(date_str)
    if dt is None:
        return False
    return dt < datetime.now(timezone.utc) - timedelta(hours=max_hours)


def _clean_html(html_text: str) -> str:
    if not html_text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", html_text)
    return re.sub(r"\s+", " ", clean).strip()


def classify_role(title: str, description: str, config: dict):
    """Return 'ml', 'software', or None based on keyword presence.

    ML takes precedence. Software only counts when include_software_roles is on.
    """
    text = f"{title} {description}".lower()
    ml_kws = config.get("relevance_keywords", [])
    if any(kw.lower() in text for kw in ml_kws):
        return "ml"
    if config.get("include_software_roles", False):
        sw_kws = config.get("software_keywords", [])
        if any(kw.lower() in text for kw in sw_kws):
            return "software"
    return None


# =========================================================
# GREENHOUSE
# =========================================================
GREENHOUSE_URLS = [
    "https://boards-api.greenhouse.io/v1/boards/{}/jobs?content=true",
    "https://api.greenhouse.io/v1/boards/{}/jobs?content=true",
]


def _scrape_greenhouse_one(company: str, config: dict) -> list[dict]:
    max_hours = config.get("freshness", {}).get("max_post_age_hours", 72)
    data = None
    for tmpl in GREENHOUSE_URLS:
        data = _get_json_safe(tmpl.format(company))
        if data and "jobs" in data:
            break
    if not data or "jobs" not in data:
        return []

    out = []
    for j in data["jobs"]:
        title = j.get("title", "")
        description = _clean_html(j.get("content", ""))
        updated = j.get("updated_at", "")
        # Greenhouse updated_at is noisy; only drop when clearly ancient.
        if _too_old(updated, max_hours):
            continue
        cat = classify_role(title, description, config)
        if not cat:
            continue
        out.append(
            {
                "title": title,
                "company": company.replace("-", " ").title(),
                "location": j.get("location", {}).get("name", ""),
                "url": j.get("absolute_url", ""),
                "description": description,
                "date_posted": updated,
                "job_type": "fulltime",
                "source": "greenhouse",
                "role_category": cat,
            }
        )
    return out


# =========================================================
# LEVER
# =========================================================
def _scrape_lever_one(company: str, config: dict) -> list[dict]:
    max_hours = config.get("freshness", {}).get("max_post_age_hours", 72)
    data = _get_json_safe(f"https://api.lever.co/v0/postings/{company}?mode=json")
    if not data or not isinstance(data, list):
        return []

    out = []
    for j in data:
        title = j.get("text", "")
        raw_desc = j.get("descriptionPlain", j.get("description", ""))
        description = _clean_html(raw_desc) if "<" in str(raw_desc) else str(raw_desc)
        created = str(j.get("createdAt", ""))
        if _too_old(created, max_hours):
            continue
        cats = j.get("categories", {})
        team = cats.get("team", "")
        cat = classify_role(title, f"{description} {team}", config)
        if not cat:
            continue
        commitment = cats.get("commitment", "")
        out.append(
            {
                "title": title,
                "company": company.replace("-", " ").title(),
                "location": cats.get("location", ""),
                "url": j.get("hostedUrl", j.get("applyUrl", "")),
                "description": description,
                "date_posted": created,
                "job_type": "internship" if "intern" in commitment.lower() else "fulltime",
                "source": "lever",
                "role_category": cat,
            }
        )
    return out


# =========================================================
# ASHBY
# =========================================================
def _scrape_ashby_one(company: str, config: dict) -> list[dict]:
    max_hours = config.get("freshness", {}).get("max_post_age_hours", 72)
    data = _get_json_safe(
        f"https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true"
    )
    if not data or "jobs" not in data:
        return []

    out = []
    for j in data["jobs"]:
        title = j.get("title", "")
        description = _clean_html(j.get("descriptionHtml", ""))
        published = j.get("publishedAt", "")
        if _too_old(published, max_hours):
            continue
        cat = classify_role(title, description, config)
        if not cat:
            continue
        loc = j.get("location", "")
        out.append(
            {
                "title": title,
                "company": company.replace("-", " ").title(),
                "location": loc if isinstance(loc, str) else str(loc),
                "url": j.get("jobUrl", j.get("applyUrl", "")),
                "description": description,
                "date_posted": published,
                "job_type": "fulltime",
                "source": "ashby",
                "role_category": cat,
            }
        )
    return out


# =========================================================
# SMARTRECRUITERS — public postings API, ISO release dates
# =========================================================
def _scrape_smartrecruiters_one(slug: str, config: dict) -> list[dict]:
    max_hours = config.get("freshness", {}).get("max_post_age_hours", 72)
    data = _get_json_safe(
        f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"
    )
    if not data or "content" not in data:
        return []

    out = []
    for j in data["content"]:
        title = j.get("name", "")
        released = j.get("releasedDate", "")
        if _too_old(released, max_hours):
            continue
        loc = j.get("location", {}) or {}
        location = ", ".join(
            x for x in [loc.get("city", ""), loc.get("region", ""), loc.get("country", "")] if x
        )
        cat = classify_role(title, "", config)
        if not cat:
            continue
        pid = j.get("id", "")
        out.append(
            {
                "title": title,
                "company": (j.get("company", {}) or {}).get("name", slug),
                "location": location,
                "url": f"https://jobs.smartrecruiters.com/{slug}/{pid}",
                "description": "",  # detail requires a second call; title carries the signal
                "date_posted": released,
                "job_type": "fulltime",
                "source": "smartrecruiters",
                "role_category": cat,
            }
        )
    return out


# =========================================================
# WORKDAY — per-tenant CXS endpoint (POST). Where big employers post FIRST.
# =========================================================
_WORKDAY_QUERIES = ["machine learning", "software engineer", "data scientist"]


def _scrape_workday_one(entry: dict, config: dict) -> list[dict]:
    tenant = entry.get("tenant")
    host = entry.get("host", "wd5")
    site = entry.get("site")
    name = entry.get("name", tenant)
    if not (tenant and site):
        return []

    base = f"https://{tenant}.{host}.myworkdayjobs.com/{site}"
    api = f"https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    max_hours = config.get("freshness", {}).get("max_post_age_hours", 72)

    seen_paths, out = set(), []
    for q in _WORKDAY_QUERIES:
        data = _post_json_safe(
            api, {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": q}
        )
        if not data or "jobPostings" not in data:
            continue
        for j in data["jobPostings"]:
            path = j.get("externalPath", "")
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            title = j.get("title", "")
            posted_on = j.get("postedOn", "")
            if _too_old(posted_on, max_hours):
                continue
            cat = classify_role(title, " ".join(j.get("bulletFields", []) or []), config)
            if not cat:
                continue
            out.append(
                {
                    "title": title,
                    "company": name,
                    "location": j.get("locationsText", ""),
                    "url": base + path,
                    "description": "",
                    "date_posted": posted_on,
                    "job_type": "fulltime",
                    "source": "workday",
                    "role_category": cat,
                }
            )
    return out


# =========================================================
# REMOTIVE — free remote-jobs API
# =========================================================
def _scrape_remotive(config: dict) -> list[dict]:
    data = _get_json_safe(
        "https://remotive.com/api/remote-jobs?category=software-dev&limit=50"
    )
    if not data or "jobs" not in data:
        return []
    out = []
    for j in data["jobs"]:
        title = j.get("title", "")
        description = _clean_html(j.get("description", ""))
        cat = classify_role(title, description, config)
        if not cat:
            continue
        out.append(
            {
                "title": title,
                "company": j.get("company_name", ""),
                "location": "Remote",
                "url": j.get("url", ""),
                "description": description,
                "date_posted": j.get("publication_date", ""),
                "job_type": "fulltime",
                "source": "remotive",
                "role_category": cat,
            }
        )
    return out


# =========================================================
# CONCURRENT ORCHESTRATION
# =========================================================
def scrape_all_ats(config: dict) -> list[dict]:
    """Run every board concurrently (one task per company) and combine results."""
    tasks = []  # (label, callable)

    for c in config.get("greenhouse_companies", []):
        tasks.append((f"greenhouse:{c}", lambda c=c: _scrape_greenhouse_one(c, config)))
    for c in config.get("lever_companies", []):
        tasks.append((f"lever:{c}", lambda c=c: _scrape_lever_one(c, config)))
    for c in config.get("ashby_companies", []):
        tasks.append((f"ashby:{c}", lambda c=c: _scrape_ashby_one(c, config)))
    for c in config.get("smartrecruiters_companies", []):
        tasks.append((f"smartrecruiters:{c}", lambda c=c: _scrape_smartrecruiters_one(c, config)))
    for e in config.get("workday_companies", []):
        tasks.append((f"workday:{e.get('name')}", lambda e=e: _scrape_workday_one(e, config)))

    extra = config.get("extra_api_sources", {})
    if extra.get("remotive"):
        tasks.append(("remotive", lambda: _scrape_remotive(config)))

    all_jobs, source_counts = [], {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fn): label for label, fn in tasks}
        for fut in as_completed(futures):
            label = futures[fut]
            try:
                jobs = fut.result() or []
            except Exception as e:
                print(f"[ATS] {label} failed: {e}")
                jobs = []
            if jobs:
                all_jobs.extend(jobs)
                platform = label.split(":")[0]
                source_counts[platform] = source_counts.get(platform, 0) + len(jobs)

    for platform, n in sorted(source_counts.items()):
        print(f"[{platform.upper()}] {n} relevant jobs")
    print(f"[ATS] Total: {len(all_jobs)} jobs across {len(tasks)} boards")
    return all_jobs
