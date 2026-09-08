"""do_not_apply radar: fuzzy company matching + cooldown checks + a small CLI.

Fuzzy match is deliberately conservative. It normalizes away legal suffixes and
punctuation, then matches when one name's token set is a subset of the other
("Micron" ⊆ "Micron Technology, Inc.", "IBM" ⊆ "IBM Corporation"), or when the
normalized strings are near-identical. It will NOT match unrelated names that
merely share a prefix ("Micron" vs "Microsoft").
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Optional

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "do_not_apply.json",
)

# Legal suffixes / filler tokens stripped before comparison.
_SUFFIX_TOKENS = {
    "inc", "llc", "corp", "corporation", "co", "ltd", "limited", "plc",
    "group", "holdings", "holding", "technologies", "technology", "labs",
    "systems", "solutions", "the", "company", "gmbh", "sa", "ag", "nv",
    "international", "global", "usa", "us",
}


def data_path() -> str:
    return _DATA_PATH


def load(path: Optional[str] = None) -> list[dict]:
    path = path or _DATA_PATH
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(entries: list[dict], path: Optional[str] = None) -> None:
    path = path or _DATA_PATH
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
        f.write("\n")


def normalize(name: str) -> str:
    """Lowercase, drop punctuation and legal suffixes, collapse whitespace."""
    if not name:
        return ""
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)  # punctuation -> space
    tokens = [t for t in s.split() if t and t not in _SUFFIX_TOKENS]
    return " ".join(tokens)


def _matches(a: str, b: str) -> bool:
    """True if normalized company names a and b refer to the same employer."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = set(na.split()), set(nb.split())
    # Subset containment: the shorter name's tokens all appear in the longer.
    if ta and tb and (ta <= tb or tb <= ta):
        return True
    # Near-identical strings (typo / spacing) — high bar to avoid false hits.
    if SequenceMatcher(None, na, nb).ratio() >= 0.92:
        return True
    return False


def find_entry(company: str, entries: Optional[list[dict]] = None) -> Optional[dict]:
    """Return the do_not_apply entry matching `company`, or None."""
    entries = entries if entries is not None else load()
    for e in entries:
        if _matches(company, e.get("company", "")):
            return e
    return None


def _as_date(value) -> Optional[date]:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def check(company: str, today=None, entries: Optional[list[dict]] = None) -> Optional[dict]:
    """If `company` is on the radar AND still cooling down, return a dict:

        {"company", "rejections", "cooldown_until", "blocked": bool}

    `blocked` is True when today < cooldown_until (Path A should drop the job;
    Path B should raise a radar warning). Returns None if not on the radar.
    """
    entry = find_entry(company, entries)
    if entry is None:
        return None
    today = _as_date(today) or date.today()
    cutoff = _as_date(entry.get("cooldown_until"))
    blocked = cutoff is not None and today < cutoff
    return {
        "company": entry.get("company"),
        "rejections": entry.get("rejections", 0),
        "cooldown_until": entry.get("cooldown_until"),
        "blocked": blocked,
    }


# ── CLI: add / remove / list as new rejections arrive ───────────────────────
def _cli(argv=None) -> int:
    p = argparse.ArgumentParser(prog="outreach.do_not_apply", description="Manage the do_not_apply radar.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("add", help="Add a rejection (creates or bumps the company).")
    pa.add_argument("company")
    pa.add_argument("--rejections", type=int, default=1, help="Set the count outright (default: increment by 1).")
    pa.add_argument("--increment", action="store_true", help="Increment the existing count by 1.")
    pa.add_argument("--last-rejection", default=date.today().isoformat())
    pa.add_argument("--cooldown-months", type=int, default=6)

    pr = sub.add_parser("remove", help="Remove a company from the radar.")
    pr.add_argument("company")

    sub.add_parser("list", help="List all companies on the radar.")

    args = p.parse_args(argv)
    entries = load()

    if args.cmd == "list":
        for e in sorted(entries, key=lambda x: -x.get("rejections", 0)):
            print(f"{e['company']:<30} {e.get('rejections', 0):>2} rejections  "
                  f"cooldown_until {e.get('cooldown_until', '?')}")
        print(f"\n{len(entries)} companies on the radar.")
        return 0

    if args.cmd == "remove":
        existing = find_entry(args.company, entries)
        if not existing:
            print(f"'{args.company}' is not on the radar.")
            return 1
        entries = [e for e in entries if e is not existing]
        _save(entries)
        print(f"Removed {existing['company']}.")
        return 0

    # add
    last = _as_date(args.last_rejection) or date.today()
    cd_month = last.month - 1 + args.cooldown_months
    cd_year = last.year + cd_month // 12
    cooldown = date(cd_year, cd_month % 12 + 1, min(last.day, 28))
    existing = find_entry(args.company, entries)
    if existing:
        if args.increment or args.rejections == 1:
            existing["rejections"] = existing.get("rejections", 0) + 1
        else:
            existing["rejections"] = args.rejections
        existing["last_rejection"] = last.isoformat()
        existing["cooldown_until"] = cooldown.isoformat()
        print(f"Updated {existing['company']}: {existing['rejections']} rejections, "
              f"cooldown_until {existing['cooldown_until']}.")
    else:
        entries.append({
            "company": args.company,
            "rejections": args.rejections,
            "last_rejection": last.isoformat(),
            "cooldown_until": cooldown.isoformat(),
        })
        print(f"Added {args.company}: {args.rejections} rejections, cooldown_until {cooldown.isoformat()}.")
    _save(entries)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
