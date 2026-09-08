"""Stage 5 — Queue rows into the Google Sheet "Outreach" tab (or print them).

The system only ever writes status = NEEDS_REVIEW. LinkedIn appears solely as
pre-built people-search URLs for Riya to click herself.
"""

from __future__ import annotations

import os
from urllib.parse import quote

from . import config


def linkedin_urls(company: str) -> tuple[str, str]:
    """Return (people search URL, alumni-narrowed URL) for a company.

    These are plain search links Riya opens in her own browser. No LinkedIn
    auth, scraping, or automation of any kind happens here.
    """
    base = "https://www.linkedin.com/search/results/people/?keywords="
    people = base + quote(f'"{company}" machine learning')
    alumni = base + quote(f'"{company}" machine learning {config.ALUMNI_TOKEN}')
    return people, alumni


def row_from_item(item: dict) -> list:
    """Turn a pipeline item dict into a sheet row (order = OUTREACH_HEADERS)."""
    people, alumni = linkedin_urls(item.get("company", ""))
    return [
        item.get("date", ""),
        item.get("source", ""),
        item.get("company", ""),
        item.get("role", ""),
        item.get("posting_url", ""),
        item.get("industry", ""),
        item.get("matched_repo", ""),
        item.get("draft_message", ""),
        item.get("draft_short", ""),
        people,
        alumni,
        config.STATUS_NEW,
        item.get("notes", ""),
    ]


def _get_sheet():
    from storage.sheets import get_client  # reuse the service-account client

    sheet_id = os.getenv("GOOGLE_SHEETS_ID")
    if not sheet_id:
        return None
    import gspread

    gc = get_client()
    ss = gc.open_by_key(sheet_id)
    try:
        sheet = ss.worksheet(config.OUTREACH_TAB)
    except gspread.WorksheetNotFound:
        sheet = ss.add_worksheet(config.OUTREACH_TAB, rows=1000, cols=len(config.OUTREACH_HEADERS))
    first = sheet.row_values(1)
    if not first or first[0] != config.OUTREACH_HEADERS[0]:
        sheet.insert_row(config.OUTREACH_HEADERS, 1)
    return sheet


def write_items(items: list[dict], dry_run: bool = False) -> int:
    """Append items to the Outreach tab. In dry-run, print the rows instead."""
    rows = [row_from_item(it) for it in items]

    if dry_run:
        print("\n" + "=" * 70)
        print(f"[DRY RUN] {len(rows)} outreach rows (status={config.STATUS_NEW}):")
        print("=" * 70)
        for it, row in zip(items, rows):
            print(f"\n- {it.get('company','?')} | {it.get('role','?')}  "
                  f"[{it.get('source','?')} / {it.get('industry','?')}]")
            print(f"  repo:  {it.get('matched_repo','')}")
            print(f"  draft: {it.get('draft_message','')}")
            print(f"  short: {it.get('draft_short','')}")
            print(f"  li:    {row[9]}")
            if it.get("notes"):
                print(f"  note:  {it['notes']}")
        return len(rows)

    if not rows:
        return 0
    sheet = _get_sheet()
    if sheet is None:
        print("[OUTREACH] No GOOGLE_SHEETS_ID set — skipping sheet write")
        return 0
    sheet.append_rows(rows, value_input_option="USER_ENTERED")
    print(f"[OUTREACH] Wrote {len(rows)} rows to '{config.OUTREACH_TAB}' tab")
    return len(rows)
