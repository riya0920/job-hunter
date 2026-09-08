"""Stage 1 — Filter (Path A only).

Drops a discovered job if any kill condition fires. Mega-pool companies are
never dropped; they are tagged referral_only=True. Every drop is returned with
its reason so the weekly "what got filtered" digest can report it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import config, do_not_apply

_EXPERIENCE_RE = re.compile(config.EXPERIENCE_REGEX, re.IGNORECASE)


@dataclass
class FilterResult:
    passed: bool
    reason: Optional[str] = None          # why it was dropped (None if passed)
    tags: dict = field(default_factory=dict)  # e.g. {"referral_only": True}


def _title_hit(title: str) -> Optional[str]:
    low = f" {title.lower()} "
    for word in config.TITLE_KILL_WORDS:
        # word-boundary match so "Lead" doesn't fire on "Leadership"
        if re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", low):
            return word
    return None


def _killword_hit(text: str) -> Optional[str]:
    low = text.lower()
    for kw in config.KILL_WORDS:
        if kw in low:
            return kw
    return None


def _is_mega_pool(company: str) -> bool:
    norm = do_not_apply.normalize(company)
    tokens = set(norm.split())
    for mp in config.MEGA_POOL:
        mpn = do_not_apply.normalize(mp)
        if norm == mpn or (mpn and set(mpn.split()) <= tokens):
            return True
    return False


def _too_old(date_posted: str) -> bool:
    """True only when a parseable posting date is older than MAX_AGE_HOURS."""
    if not date_posted:
        return False  # unknown date → do not drop
    dt = _parse_date(date_posted)
    if dt is None:
        return False
    now = datetime.now(timezone.utc)
    return (now - dt) > timedelta(hours=config.MAX_AGE_HOURS)


def _parse_date(value: str) -> Optional[datetime]:
    value = value.strip()
    # ISO 8601 first (handles "2026-09-05T12:00:00", "...+00:00", trailing Z).
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def filter_job(job: dict, today=None, dna_entries=None) -> FilterResult:
    """Apply every Path A filter rule. Order: hard drops first, mega-pool last."""
    company = job.get("company", "") or ""
    title = job.get("title", "") or ""
    description = job.get("description", "") or job.get("description_preview", "") or ""

    # 1. do_not_apply cooldown
    radar = do_not_apply.check(company, today=today, entries=dna_entries)
    if radar and radar["blocked"]:
        return FilterResult(False, reason=(
            f"do_not_apply: {radar['company']} ({radar['rejections']} prior rejections, "
            f"cooldown until {radar['cooldown_until']})"
        ))

    # 2. sponsorship / clearance kill-words in the posting text
    kw = _killword_hit(f"{title}\n{description}")
    if kw:
        return FilterResult(False, reason=f"kill-word: '{kw}'")

    # 3. seniority / level words in the title
    th = _title_hit(title)
    if th:
        return FilterResult(False, reason=f"title level: '{th}'")

    # 4. 3+ years experience required
    if _EXPERIENCE_RE.search(description):
        return FilterResult(False, reason="requires 3+ years experience")

    # 5. stale posting (only when a date is available)
    if _too_old(job.get("date_posted", "") or ""):
        return FilterResult(False, reason=f"posting older than {config.MAX_AGE_HOURS}h")

    # 6. mega-pool → keep, but tag referral_only
    if _is_mega_pool(company):
        return FilterResult(True, tags={"referral_only": True})

    return FilterResult(True)
