"""
Scraper using JobSpy library — covers LinkedIn, Indeed, Glassdoor, Google Jobs, ZipRecruiter.
"""
import traceback
from jobspy import scrape_jobs


def scrape_aggregators(search_queries: list[str], config: dict) -> list[dict]:
    """
    Run searches across multiple job aggregators using JobSpy.
    Returns a list of normalized job dicts.
    """
    all_jobs = []
    # Glassdoor's API is broken (400 errors on location parsing) — skip it
    sites = ["indeed", "linkedin", "google", "zip_recruiter"]
    
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
