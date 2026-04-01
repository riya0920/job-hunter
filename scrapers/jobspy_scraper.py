"""
Scraper using JobSpy library — covers LinkedIn, Indeed, Google Jobs, ZipRecruiter.
Plus a dedicated LinkedIn backup scraper hitting the public guest API directly.
"""
import traceback
import time
import os
import requests
from bs4 import BeautifulSoup
from jobspy import scrape_jobs


def scrape_aggregators(search_queries: list[str], config: dict) -> list[dict]:
    """
    Run searches across multiple job aggregators using JobSpy.
    Returns a list of normalized job dicts.
    """
    all_jobs = []
    # Glassdoor: broken API (400 errors). ZipRecruiter: blocks cloud IPs (403 Cloudflare WAF)
    sites = ["indeed", "linkedin", "google"]
    
    location = config.get("location", "United States")
    hours_old = config.get("max_hours_old", 24)
    results_wanted = config.get("results_per_query", 25)

    for query in search_queries:
        print(f"[JOBSPY] Searching: '{query}'")
        try:
            df = scrape_jobs(
                site_name=sites,
                search_term=query,
                location=location,
                results_wanted=results_wanted,
                hours_old=hours_old,
                country_indeed="USA",
                linkedin_fetch_description=True,  # Get full descriptions for better scoring
            )
            
            if df is None or df.empty:
                print(f"  → 0 results")
                continue

            print(f"  → {len(df)} results")

            for _, row in df.iterrows():
                job = {
                    "title": str(row.get("title", "")).strip(),
                    "company": str(row.get("company_name", row.get("company", ""))).strip(),
                    "location": str(row.get("location", "")).strip(),
                    "url": str(row.get("job_url", row.get("link", ""))).strip(),
                    "description": str(row.get("description", "")).strip(),
                    "date_posted": str(row.get("date_posted", "")),
                    "job_type": str(row.get("job_type", "fulltime")).strip(),
                    "salary": str(row.get("min_amount", "")) if row.get("min_amount") else "",
                    "source": str(row.get("site", "jobspy")).strip(),
                }
                
                # Skip jobs with no title or URL
                if job["title"] and job["url"] and job["url"] != "nan":
                    all_jobs.append(job)

        except Exception as e:
            print(f"[JOBSPY] Error scraping '{query}': {e}")
            traceback.print_exc()

    print(f"[JOBSPY] Total jobs collected: {len(all_jobs)}")
    return all_jobs


# =========================================================
# DEDICATED LINKEDIN BACKUP — hits the public guest API
# This catches jobs that JobSpy misses due to rate limiting
# =========================================================
LINKEDIN_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
SCRAPERAPI_BASE = "https://api.scraperapi.com"


def _linkedin_fetch(url: str, params: dict) -> requests.Response | None:
    """Fetch LinkedIn URL, using ScraperAPI proxy if available, else direct."""
    api_key = os.environ.get("SCRAPERAPI_KEY", "")
    
    # Build the full LinkedIn URL with params
    from urllib.parse import urlencode
    full_url = f"{url}?{urlencode(params)}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }
    
    try:
        if api_key:
            # Route through ScraperAPI — different IP each request
            resp = requests.get(
                SCRAPERAPI_BASE,
                params={"api_key": api_key, "url": full_url},
                timeout=30
            )
        else:
            # Direct — works locally, may get rate limited on cloud
            resp = requests.get(full_url, headers=headers, timeout=15)
        
        return resp if resp.status_code == 200 else None
    except Exception:
        return None


def scrape_linkedin_direct(search_queries: list[str], config: dict) -> list[dict]:
    """
    Scrape LinkedIn's public guest API directly.
    Uses ScraperAPI proxy if SCRAPERAPI_KEY is set (bypasses rate limits).
    Falls back to direct requests if no key.
    """
    all_jobs = []
    location = config.get("location", "United States")
    seen_ids = set()
    
    has_proxy = bool(os.environ.get("SCRAPERAPI_KEY", ""))
    if has_proxy:
        print("[LINKEDIN] Using ScraperAPI proxy for LinkedIn")
    
    # With proxy: use all queries, more pages. Without: limit to avoid blocks.
    max_queries = len(search_queries) if has_proxy else 5
    max_pages = 6 if has_proxy else 3

    for query in search_queries[:max_queries]:
        print(f"[LINKEDIN] Searching: '{query}'")
        page_jobs = 0
        
        for page in range(max_pages):
            params = {
                "keywords": query,
                "location": location,
                "start": page * 25,
                "f_TPR": "r86400",    # Past 24 hours
                "f_E": "2,3",         # Entry level (2) + Associate (3)
                "sortBy": "DD",       # Sort by date (most recent first)
            }
            
            resp = _linkedin_fetch(LINKEDIN_SEARCH_URL, params)
            if not resp:
                break
            
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("div", class_="base-card")
            
            if not cards:
                break
            
            for card in cards:
                try:
                    title_el = card.find("h3", class_="base-search-card__title")
                    company_el = card.find("h4", class_="base-search-card__subtitle")
                    location_el = card.find("span", class_="job-search-card__location")
                    link_el = card.find("a", class_="base-card__full-link")
                    time_el = card.find("time")
                    
                    title = title_el.get_text(strip=True) if title_el else ""
                    company = company_el.get_text(strip=True) if company_el else ""
                    loc = location_el.get_text(strip=True) if location_el else ""
                    url = link_el["href"].split("?")[0] if link_el and link_el.get("href") else ""
                    date_posted = time_el.get("datetime", "") if time_el else ""
                    
                    job_id = url.split("-")[-1] if url else ""
                    if not title or not url or job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    
                    all_jobs.append({
                        "title": title,
                        "company": company,
                        "location": loc,
                        "url": url,
                        "description": "",
                        "date_posted": date_posted,
                        "job_type": "fulltime",
                        "source": "linkedin_direct",
                    })
                    page_jobs += 1
                except Exception:
                    continue
            
            time.sleep(1.5 if has_proxy else 2.5)
        
        if page_jobs > 0:
            print(f"  → {page_jobs} jobs")
        time.sleep(2 if has_proxy else 3)

    if all_jobs:
        print(f"[LINKEDIN] Total: {len(all_jobs)} jobs")
    else:
        print(f"[LINKEDIN] Total: 0 (may be rate limited — add SCRAPERAPI_KEY for better coverage)")
    
    return all_jobs