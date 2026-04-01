#!/usr/bin/env python3
"""
JOB HUNTER — Automated AI/ML Job Discovery & Alert System
==========================================================
Main orchestrator that runs the full pipeline:
1. Scrape jobs from ATS APIs + job aggregators
2. Filter & score against your resume
3. Write to Google Sheets
4. Send email + push notifications

Usage:
    python main.py              # Full run
    python main.py --dry-run    # Scrape & score only, no notifications
    python main.py --ats-only   # Only scrape ATS APIs (faster, always reliable)
    python main.py --stats      # Show database stats
"""
import os
import sys
import yaml
import time
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_config() -> dict:
    """Load search configuration from YAML."""
    config_path = os.path.join(os.path.dirname(__file__), "config", "search_config.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def run(dry_run: bool = False, ats_only: bool = False):
    """Execute the full job hunting pipeline."""
    start = time.time()
    config = load_config()
    
    print("=" * 60)
    print(f"🎯 JOB HUNTER — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # ── Step 1: Scrape ──────────────────────────────────────────
    print("\n📡 STEP 1: Scraping job sources...")
    all_raw_jobs = []
    
    # Always scrape ATS APIs (fast, reliable, free)
    from scrapers.ats_scraper import scrape_all_ats
    ats_jobs = scrape_all_ats(config)
    all_raw_jobs.extend(ats_jobs)
    
    # Scrape aggregators unless --ats-only
    if not ats_only:
        from scrapers.jobspy_scraper import scrape_aggregators, scrape_linkedin_direct
        queries = config.get("search_queries", [])
        
        # JobSpy (Indeed/LinkedIn/Google) — slow, use core queries only
        agg_jobs = scrape_aggregators(queries[:10], config)
        all_raw_jobs.extend(agg_jobs)
        
        # LinkedIn direct — fast, use ALL queries for max coverage
        li_jobs = scrape_linkedin_direct(queries, config)
        all_raw_jobs.extend(li_jobs)
    
    print(f"\n   Total raw jobs collected: {len(all_raw_jobs)}")
    
    if not all_raw_jobs:
        print("\n   No jobs found in this cycle. Will try again next run.")
        return
    
    # ── Step 2: Process & Score ──────────────────────────────────
    print("\n🔍 STEP 2: Filtering, scoring & deduplication...")
    from processors.scorer import process_jobs
    processed_jobs = process_jobs(all_raw_jobs, config)
    
    if not processed_jobs:
        print("\n   No new matching jobs after filtering.")
        elapsed = time.time() - start
        print(f"\n⏱  Completed in {elapsed:.1f}s")
        return
    
    # Print summary
    high = [j for j in processed_jobs if j["score"] >= 70]
    medium = [j for j in processed_jobs if 50 <= j["score"] < 70]
    low = [j for j in processed_jobs if j["score"] < 50]
    
    print(f"\n   Results: {len(high)} high / {len(medium)} medium / {len(low)} low match")
    
    # Show top 5
    print("\n   Top matches:")
    for j in processed_jobs[:5]:
        h1b_icon = "✅" if "Sponsor" in j.get("h1b_status", "") else ("❌" if "No" in j.get("h1b_status", "") else "❓")
        print(f"   {j['score']:5.1f}% │ {j['title'][:45]:<45} │ {j['company'][:20]:<20} │ H1B:{h1b_icon}")
    
    if dry_run:
        print("\n   [DRY RUN] Skipping sheets write and notifications")
        elapsed = time.time() - start
        print(f"\n⏱  Completed in {elapsed:.1f}s")
        return
    
    # ── Step 3: Write to Google Sheets ───────────────────────────
    print("\n📊 STEP 3: Writing to Google Sheets...")
    from storage.sheets import write_jobs
    written = write_jobs(processed_jobs)
    
    # ── Step 4: Notify ───────────────────────────────────────────
    print("\n📬 STEP 4: Sending notifications...")
    from notifications.notifier import notify
    result = notify(processed_jobs)
    
    # ── Summary ──────────────────────────────────────────────────
    elapsed = time.time() - start
    print("\n" + "=" * 60)
    print(f"✅ COMPLETE — {len(processed_jobs)} new jobs processed")
    print(f"   📊 Sheets: {'Written' if written else 'Skipped'}")
    print(f"   📧 Email:  {'Sent' if result.get('email') else 'Skipped'}")
    print(f"   📱 Push:   {'Sent' if result.get('push') else 'Skipped'}")
    print(f"   ⏱  Time:   {elapsed:.1f}s")
    print("=" * 60)


def show_stats():
    """Display database statistics."""
    from storage.db import get_stats
    stats = get_stats()
    print("\n📈 Job Hunter Statistics")
    print(f"   Total jobs tracked: {stats['total_jobs_tracked']}")
    print(f"   New today:          {stats['new_today']}")


if __name__ == "__main__":
    args = sys.argv[1:]
    
    if "--stats" in args:
        show_stats()
    elif "--help" in args or "-h" in args:
        print(__doc__)
    else:
        dry_run = "--dry-run" in args
        ats_only = "--ats-only" in args
        run(dry_run=dry_run, ats_only=ats_only)