"""
Direct ATS API scrapers — Greenhouse, Lever, Ashby.
These are public, unauthenticated JSON APIs. Extremely reliable.
"""
import requests
import traceback
from datetime import datetime, timedelta, timezone
from tenacity import retry, stop_after_attempt, wait_exponential
import re
import time


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
def _get_json(url: str, timeout: int = 30) -> dict | list | None:
    """Fetch JSON with retries."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _get_json_safe(url: str, timeout: int = 30) -> dict | list | None:
    """Fetch JSON, return None on any error (no retry noise)."""
    try:
        return _get_json(url, timeout)
    except Exception:
        return None


def _is_recent(date_str: str, max_hours: int = 24) -> bool:
    """Check if a date string is within the last N hours.
    
    NOTE: Greenhouse's updated_at is unreliable for freshness — it changes
    on any metadata edit, not just initial posting. For Greenhouse, we rely
    on deduplication (SQLite DB) to avoid re-processing old jobs, and let
    the experience-level + scoring filters handle quality.
    """
    if not date_str or date_str == "None" or date_str == "nan":
        return True  # If no date, include it (better safe than sorry)
    
    try:
        # Try ISO format
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_hours)
        return dt >= cutoff
    except (ValueError, TypeError):
        pass
    
    try:
        # Try epoch milliseconds (Lever uses this)
        ts = int(date_str) / 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_hours)
        return dt >= cutoff
    except (ValueError, TypeError):
        pass
    
    return True  # Default: include


def _is_ai_ml_relevant(title: str, description: str, keywords: list[str]) -> bool:
    """Quick check if a job is AI/ML related."""
    text = f"{title} {description}".lower()
    return any(kw.lower() in text for kw in keywords)


def _clean_html(html_text: str) -> str:
    """Strip HTML tags for plain text."""
    if not html_text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', html_text)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


# =========================================================
# GREENHOUSE — tries both old and new API endpoints
# =========================================================
GREENHOUSE_URLS = [
    "https://boards-api.greenhouse.io/v1/boards/{}/jobs?content=true",
    "https://api.greenhouse.io/v1/boards/{}/jobs?content=true",
]


def scrape_greenhouse(companies: list[str], config: dict) -> list[dict]:
    """Scrape Greenhouse boards API for each company."""
    jobs = []
    max_hours = config.get("max_hours_old", 24)
    keywords = config.get("relevance_keywords", [])
    
    for company in companies:
        data = None
        for url_template in GREENHOUSE_URLS:
            url = url_template.format(company)
            data = _get_json_safe(url)
            if data and "jobs" in data:
                break
        
        if not data or "jobs" not in data:
            # Silently skip — board slug may be wrong or company moved platforms
            continue
        
        count = 0
        for j in data["jobs"]:
            title = j.get("title", "")
            updated = j.get("updated_at", "")
            desc_html = j.get("content", "")
            description = _clean_html(desc_html)
            location_name = j.get("location", {}).get("name", "")
            job_url = j.get("absolute_url", "")
            
            if not _is_recent(updated, max_hours):
                continue
            if not _is_ai_ml_relevant(title, description, keywords):
                continue
            
            jobs.append({
                "title": title,
                "company": company.replace("-", " ").title(),
                "location": location_name,
                "url": job_url,
                "description": description,
                "date_posted": updated,
                "job_type": "fulltime",
                "source": "greenhouse",
            })
            count += 1
        
        if count > 0:
            print(f"[GREENHOUSE] {company}: {count} AI/ML jobs")
        
        time.sleep(0.5)  # Be polite
    
    print(f"[GREENHOUSE] Total: {len(jobs)} jobs")
    return jobs


# =========================================================
# LEVER
# =========================================================
def scrape_lever(companies: list[str], config: dict) -> list[dict]:
    """Scrape Lever postings API for each company."""
    jobs = []
    max_hours = config.get("max_hours_old", 24)
    keywords = config.get("relevance_keywords", [])
    
    for company in companies:
        url = f"https://api.lever.co/v0/postings/{company}?mode=json"
        data = _get_json_safe(url)
        
        if not data or not isinstance(data, list):
            continue
        
        count = 0
        for j in data:
            title = j.get("text", "")
            created = str(j.get("createdAt", ""))
            desc_html = j.get("descriptionPlain", j.get("description", ""))
            description = _clean_html(desc_html) if "<" in str(desc_html) else str(desc_html)
            
            categories = j.get("categories", {})
            location_name = categories.get("location", "")
            team = categories.get("team", "")
            commitment = categories.get("commitment", "")
            
            job_url = j.get("hostedUrl", j.get("applyUrl", ""))
            
            if not _is_recent(created, max_hours):
                continue
            if not _is_ai_ml_relevant(title, f"{description} {team}", keywords):
                continue
            
            job_type = "internship" if "intern" in commitment.lower() else "fulltime"
            
            jobs.append({
                "title": title,
                "company": company.replace("-", " ").title(),
                "location": location_name,
                "url": job_url,
                "description": description,
                "date_posted": created,
                "job_type": job_type,
                "source": "lever",
            })
            count += 1
        
        if count > 0:
            print(f"[LEVER] {company}: {count} AI/ML jobs")
        
        time.sleep(0.5)
    
    print(f"[LEVER] Total: {len(jobs)} jobs")
    return jobs


# =========================================================
# ASHBY
# =========================================================
def scrape_ashby(companies: list[str], config: dict) -> list[dict]:
    """Scrape Ashby job board API for each company."""
    jobs = []
    max_hours = config.get("max_hours_old", 24)
    keywords = config.get("relevance_keywords", [])
    
    for company in companies:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true"
        data = _get_json_safe(url)
        
        if not data or "jobs" not in data:
            continue
        
        count = 0
        for j in data["jobs"]:
            title = j.get("title", "")
            published = j.get("publishedAt", "")
            description = _clean_html(j.get("descriptionHtml", ""))
            location_name = j.get("location", "")
            job_url = j.get("jobUrl", j.get("applyUrl", ""))
            
            if not _is_recent(published, max_hours):
                continue
            if not _is_ai_ml_relevant(title, description, keywords):
                continue
            
            jobs.append({
                "title": title,
                "company": company.replace("-", " ").title(),
                "location": location_name if isinstance(location_name, str) else str(location_name),
                "url": job_url,
                "description": description,
                "date_posted": published,
                "job_type": "fulltime",
                "source": "ashby",
            })
            count += 1
        
        if count > 0:
            print(f"[ASHBY] {company}: {count} AI/ML jobs")
        
        time.sleep(0.5)
    
    print(f"[ASHBY] Total: {len(jobs)} jobs")
    return jobs


# =========================================================
# REMOTIVE — free API for remote jobs
# =========================================================
def scrape_remotive(config: dict) -> list[dict]:
    """Scrape Remotive's free public API for remote AI/ML jobs."""
    jobs = []
    keywords = config.get("relevance_keywords", [])
    
    url = "https://remotive.com/api/remote-jobs?category=software-dev&limit=50"
    data = _get_json_safe(url)
    
    if not data or "jobs" not in data:
        print("[REMOTIVE] Total: 0 jobs")
        return jobs
    
    count = 0
    for j in data["jobs"]:
        title = j.get("title", "")
        description = j.get("description", "")
        company = j.get("company_name", "")
        job_url = j.get("url", "")
        pub_date = j.get("publication_date", "")
        
        if not _is_ai_ml_relevant(title, _clean_html(description), keywords):
            continue
        
        jobs.append({
            "title": title,
            "company": company,
            "location": "Remote",
            "url": job_url,
            "description": _clean_html(description),
            "date_posted": pub_date,
            "job_type": "fulltime",
            "source": "remotive",
        })
        count += 1
    
    if count > 0:
        print(f"[REMOTIVE] {count} AI/ML jobs")
    print(f"[REMOTIVE] Total: {len(jobs)} jobs")
    return jobs


def scrape_all_ats(config: dict) -> list[dict]:
    """Run all ATS scrapers and combine results."""
    all_jobs = []
    
    gh = config.get("greenhouse_companies", [])
    lv = config.get("lever_companies", [])
    ab = config.get("ashby_companies", [])
    
    if gh:
        all_jobs.extend(scrape_greenhouse(gh, config))
    if lv:
        all_jobs.extend(scrape_lever(lv, config))
    if ab:
        all_jobs.extend(scrape_ashby(ab, config))
    
    # Extra free API sources
    extra = config.get("extra_api_sources", {})
    if extra.get("remotive"):
        all_jobs.extend(scrape_remotive(config))
    
    return all_jobs