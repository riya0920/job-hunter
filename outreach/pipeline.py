"""Orchestration — intake → Filter → Classify → Match → Draft → dedup → Queue.

Path A (discovered): job-hunter's scored matches, run through the Filter.
Path B (applied): Gmail confirmation emails, extracted, always queued (Riya
already applied) plus a radar warning when the company is on cooldown.

Nothing is ever sent. Every produced item carries status NEEDS_REVIEW.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from . import classify, config, do_not_apply, draft, extract, filter as filt, match, store


def _today_iso() -> str:
    return date.today().isoformat()


def _enrich(job: dict, source: str, tags: Optional[dict] = None) -> dict:
    """Classify, match, and draft for one job/confirmation → a queue item."""
    tags = tags or {}
    bucket = classify.classify(job)
    repo = match.match_repo(bucket, job)
    drafts = draft.draft(job, repo)

    notes = []
    if tags.get("referral_only"):
        notes.append("mega-pool: referral only")

    return {
        "date": _today_iso(),
        "source": source,
        "company": job.get("company", ""),
        "role": job.get("role") or job.get("title", ""),
        "posting_url": job.get("url", ""),
        "industry": bucket,
        "matched_repo": repo,
        "draft_message": drafts["draft_message"],
        "draft_short": drafts["draft_short"],
        "notes": "; ".join(notes),
    }


def _dedup(item: dict) -> Optional[dict]:
    """Return the item if new; None if it duplicates a recent row (merge note)."""
    dup = store.find_duplicate(item["company"], item["role"])
    if dup:
        note = f"dup of earlier {dup.get('source','?')} row on {dup.get('first_date','')[:10]}"
        print(f"[OUTREACH] Merged duplicate: {item['company']} / {item['role']} ({note})")
        return None
    store.record_item(item["company"], item["role"], item["source"], item.get("posting_url", ""), config.STATUS_NEW)
    return item


# ── Path A ──────────────────────────────────────────────────────────────────
def process_discovered(jobs: list[dict], today=None, dna_entries=None) -> dict:
    store.init()
    dna_entries = dna_entries if dna_entries is not None else do_not_apply.load()
    today = today or date.today()

    items, dropped = [], []
    for job in jobs:
        res = filt.filter_job(job, today=today, dna_entries=dna_entries)
        if not res.passed:
            dropped.append({"company": job.get("company", ""), "role": job.get("title", ""), "reason": res.reason})
            continue
        item = _enrich(job, source="discovered", tags=res.tags)
        kept = _dedup(item)
        if kept:
            items.append(kept)
    return {"items": items, "dropped": dropped, "warnings": []}


# ── Path B ──────────────────────────────────────────────────────────────────
def process_applied(confirmations: list, today=None, dna_entries=None) -> dict:
    """confirmations: iterable of gmail_confirmations.Confirmation (or dicts)."""
    store.init()
    dna_entries = dna_entries if dna_entries is not None else do_not_apply.load()
    today = today or date.today()

    items, warnings = [], []
    for c in confirmations:
        subject = getattr(c, "subject", None) if not isinstance(c, dict) else c.get("subject", "")
        sender = getattr(c, "sender", None) if not isinstance(c, dict) else c.get("sender", "")
        body = getattr(c, "body", None) if not isinstance(c, dict) else c.get("body", "")
        fields = extract.extract(subject or "", sender or "", body or "")
        company, role = fields["company"], fields["role"]
        if not company:
            continue  # nothing actionable

        # Radar warning (does NOT drop — she already applied)
        radar = do_not_apply.check(company, today=today, entries=dna_entries)
        if radar and radar["blocked"]:
            warnings.append(
                f"⚠️ Applied to {radar['company']}: {radar['rejections']} prior rejections, "
                f"cooldown until {radar['cooldown_until']}."
            )

        synthetic = {"company": company, "title": role, "role": role, "description": body or ""}
        item = _enrich(synthetic, source="applied")
        if fields.get("ats"):
            item["notes"] = "; ".join(n for n in [item.get("notes", ""), f"ats: {fields['ats']}"] if n)
        kept = _dedup(item)
        if kept:
            items.append(kept)
    return {"items": items, "dropped": [], "warnings": warnings}
