"""Static configuration for the Outreach Assistant.

Everything here is data the pipeline reads. No side effects on import.
"""

from __future__ import annotations

import os

# ── Claude model ────────────────────────────────────────────────────────────
# One model for extraction, classification, and drafting. Override with
# OUTREACH_MODEL if you want to pin a different snapshot.
MODEL = os.getenv("OUTREACH_MODEL", "claude-sonnet-5")

# ── Filter: kill-words in the posting text (case-insensitive substring) ─────
KILL_WORDS = [
    "will not sponsor",
    "unable to sponsor",
    "without sponsorship",
    "no sponsorship",
    "not provide sponsorship",
    "citizenship required",
    "security clearance",
    "us citizens only",
]

# ── Filter: seniority / level words in the TITLE (case-insensitive) ─────────
# Matched on word boundaries so "Leadership" won't trip "Lead", etc.
TITLE_KILL_WORDS = [
    "senior",
    "staff",
    "principal",
    "lead",
    "director",
    "intern",
    "co-op",
    "co op",
    "phd",
]

# Experience requirement: "3 years", "5+ years", "12 years", etc. (3–19).
EXPERIENCE_REGEX = r"\b(?:[3-9]|1[0-9])\+?\s*(?:\+)?\s*years?\b"

# Postings older than this are dropped (only when a posting date is present).
MAX_AGE_HOURS = 72

# ── Mega-pool companies: never dropped, tagged referral_only=True ───────────
MEGA_POOL = [
    "Amazon",
    "Google",
    "Meta",
    "Apple",
    "Microsoft",
    "Stripe",
    "McKinsey",
    "Netflix",
    "Nvidia",
    "Uber",
    "Airbnb",
    "Salesforce",
    "Oracle",
    "Bloomberg",
    "Databricks",
]

# ── Classify: industry buckets and their keyword rules ──────────────────────
# First rule whose keyword appears (case-insensitive) in title+description wins.
# If nothing fires, one Claude call decides. Order matters (most specific first).
BUCKETS = ["fintech", "healthcare", "quant", "infra_mlops", "general"]

CLASSIFY_RULES = {
    "quant": [
        "trading",
        "hedge",
        "quantitative",
        "quant",
        "market maker",
        "market making",
        "alpha",
        "systematic",
    ],
    "fintech": [
        "bank",
        "banking",
        "payments",
        "payment",
        "fraud",
        "fintech",
        "lending",
        "credit",
        "reconciliation",
        "ledger",
    ],
    "healthcare": [
        "health",
        "clinical",
        "pharma",
        "payer",
        "provider",
        "patient",
        "medical",
        "biotech",
        "life sciences",
    ],
    "infra_mlops": [
        "platform",
        "infrastructure",
        "mlops",
        "kubernetes",
        "k8s",
        "sre",
        "reliability",
        "serving",
        "inference",
        "distributed systems",
    ],
}

# ── Match: bucket → Riya's most relevant repo ───────────────────────────────
BUCKET_REPOS = {
    "fintech": "https://github.com/riya0920/governed-fraud-detection",
    "healthcare": "https://github.com/riya0920/preauth-decision-gateway",
    "quant": "https://github.com/riya0920/walk-forward-backtest-engine",
    "infra_mlops": "https://github.com/riya0920/asr-serving-vllm-k8s",
    "general": "https://github.com/riya0920/earnings-intelligence-platform",
}

# Alternate repo for reconciliation / payments-ops fintech roles.
FINTECH_RECON_REPO = "https://github.com/riya0920/reconciliation-platform"
FINTECH_RECON_HINTS = ["reconciliation", "payments ops", "payment operations", "settlement"]

# One-line problem framing per repo, used to ground draft messages.
REPO_BLURB = {
    "https://github.com/riya0920/governed-fraud-detection":
        "a governed fraud-detection pipeline with policy checks on every decision",
    "https://github.com/riya0920/reconciliation-platform":
        "a reconciliation platform that matches and explains payment breaks",
    "https://github.com/riya0920/preauth-decision-gateway":
        "a prior-authorization decision gateway for payer/provider workflows",
    "https://github.com/riya0920/walk-forward-backtest-engine":
        "a walk-forward backtest engine with leakage-safe evaluation",
    "https://github.com/riya0920/asr-serving-vllm-k8s":
        "a Whisper ASR service on Kubernetes with autoscaling and canary deploys",
    "https://github.com/riya0920/earnings-intelligence-platform":
        "a self-evaluating RAG platform over SEC filings with a numeric auditor",
}

# ── Path B: Gmail confirmation search query ─────────────────────────────────
# Proven to work on Riya's inbox. `after:` is appended at run time.
CONFIRMATION_QUERY = (
    '{"thank you for applying" "thank you for your application" '
    '"application has been received" "we have received your application" '
    '"received your application" "application was successfully submitted" '
    '"confirm receipt of your application"}'
)

# ── Sheet ───────────────────────────────────────────────────────────────────
OUTREACH_TAB = "Outreach"
OUTREACH_HEADERS = [
    "date",
    "source",
    "company",
    "role",
    "posting_url",
    "industry",
    "matched_repo",
    "draft_message",
    "draft_short",
    "linkedin_search_url",
    "linkedin_alumni_url",
    "status",
    "notes",
]

STATUS_NEW = "NEEDS_REVIEW"  # the ONLY status the system ever writes

# Dedupe window: same company + fuzzy role within N days is merged.
DEDUP_WINDOW_DAYS = 14

# Alumni search adds this token (Riya's school) to the people search.
ALUMNI_TOKEN = "Stevens"
