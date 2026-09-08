"""Stage 3 — Match a bucket to Riya's most relevant repo."""

from __future__ import annotations

from . import config


def match_repo(bucket: str, job: dict) -> str:
    """Return the repo URL for this bucket, with the fintech recon override."""
    if bucket == "fintech":
        text = f"{job.get('title', '')} {job.get('description', '') or job.get('description_preview', '')}".lower()
        if any(hint in text for hint in config.FINTECH_RECON_HINTS):
            return config.FINTECH_RECON_REPO
    return config.BUCKET_REPOS.get(bucket, config.BUCKET_REPOS["general"])
