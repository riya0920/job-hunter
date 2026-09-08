"""Stage 2 — Classify each job into one industry bucket.

Keyword rules run first (cheap, deterministic). Only when no rule fires do we
spend one Claude call. If Claude is unavailable, we fall back to "general".
"""

from __future__ import annotations

from . import config, llm


def _keyword_bucket(text: str) -> str | None:
    low = text.lower()
    for bucket in ("quant", "fintech", "healthcare", "infra_mlops"):
        for kw in config.CLASSIFY_RULES[bucket]:
            if kw in low:
                return bucket
    return None


def classify(job: dict) -> str:
    """Return one of config.BUCKETS."""
    text = f"{job.get('title', '')}\n{job.get('company', '')}\n" \
           f"{job.get('description', '') or job.get('description_preview', '')}"

    bucket = _keyword_bucket(text)
    if bucket:
        return bucket

    # No rule fired — ask Claude, constrained to the known buckets.
    system = (
        "You label a job posting with exactly one industry bucket. "
        "Respond with ONLY one of these words and nothing else: "
        "fintech, healthcare, quant, infra_mlops, general."
    )
    user = f"Title: {job.get('title', '')}\nCompany: {job.get('company', '')}\n" \
           f"Posting: {(job.get('description', '') or job.get('description_preview', ''))[:1500]}"
    ans = llm.call_text(system, user, max_tokens=8)
    if ans:
        ans = ans.strip().lower().split()[0].strip(".,")
        if ans in config.BUCKETS:
            return ans
    return "general"
