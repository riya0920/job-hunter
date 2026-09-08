"""Outreach Assistant CLI.

    python -m outreach.cli poll                 # Path B (applied): the 4h cron
    python -m outreach.cli poll --dry-run       # print the queue, write nothing
    python -m outreach.cli poll --source discovered   # run Path A off a fresh scrape
    python -m outreach.cli poll --source both

Manage the do_not_apply radar with:
    python -m outreach.do_not_apply add "Company" [--rejections N]
    python -m outreach.do_not_apply list
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date

from dotenv import load_dotenv

load_dotenv()


def _run_applied(args) -> dict:
    from . import gmail_confirmations as gc
    from . import pipeline, store

    store.init()
    if not gc.credentials_present():
        print("[POLL] GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN not set - Path B skipped.")
        print("       Get a read-only token once via "
              "job-tracker/backend/scripts/get_gmail_token.py")
        return {"items": [], "warnings": [], "dropped": []}

    after_ts = store.get_last_gmail_ts()
    confirmations = list(gc.fetch_confirmations(after_ts, max_results=args.max, lookback_days=args.lookback_days))
    print(f"[POLL] {len(confirmations)} confirmation email(s) since last run")

    result = pipeline.process_applied(confirmations, today=date.today())

    # Advance the watermark only on a real (non-dry) run.
    if confirmations and not args.dry_run:
        store.set_last_gmail_ts(max(c.ts for c in confirmations))
    return result


def _run_discovered(args) -> dict:
    from . import pipeline

    # Reuse job-hunter's own scrape+score to get scored matches.
    sys.path.insert(0, ".")
    import main as jobhunter  # main.py at repo root

    config = jobhunter.load_config()
    from scrapers.ats_scraper import scrape_all_ats
    from processors.scorer import process_jobs

    raw = scrape_all_ats(config)
    jobs = process_jobs(raw, config)
    print(f"[POLL] {len(jobs)} scored discovered job(s) to run through the outreach filter")
    return pipeline.process_discovered(jobs, today=date.today())


def _merge(a: dict, b: dict) -> dict:
    return {
        "items": a.get("items", []) + b.get("items", []),
        "warnings": a.get("warnings", []) + b.get("warnings", []),
        "dropped": a.get("dropped", []) + b.get("dropped", []),
    }


def cmd_poll(args) -> int:
    from . import digest, queue

    result = {"items": [], "warnings": [], "dropped": []}
    if args.source in ("applied", "both"):
        result = _merge(result, _run_applied(args))
    if args.source in ("discovered", "both"):
        result = _merge(result, _run_discovered(args))

    items, warnings, dropped = result["items"], result["warnings"], result["dropped"]
    print(f"\n[POLL] {len(items)} new draft(s), {len(warnings)} radar warning(s), "
          f"{len(dropped)} filtered out")

    queue.write_items(items, dry_run=args.dry_run)

    if args.dry_run:
        if warnings:
            print("\n[DRY RUN] Radar warnings:")
            for w in warnings:
                print("  " + w)
    else:
        digest.send_digest(items, warnings, dropped)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="outreach.cli", description="Outreach Assistant")
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("poll", help="Run the outreach pipeline.")
    pp.add_argument("--source", choices=["applied", "discovered", "both"], default="applied")
    pp.add_argument("--dry-run", action="store_true", help="Print the queue; write nothing, send nothing.")
    pp.add_argument("--max", type=int, default=50, help="Max Gmail confirmations to pull (Path B).")
    pp.add_argument("--lookback-days", type=int, default=7, help="First-run Gmail lookback window (Path B).")
    pp.set_defaults(func=cmd_poll)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
