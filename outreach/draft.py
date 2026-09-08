"""Stage 4 — Draft a short, human outreach message grounded in the posting.

Two variants:
  * draft_message  — full 3-line version, < 500 chars
  * draft_short    — LinkedIn connection-note friendly, < 300 chars

Structure: (1) name the role + one specific thing from the posting, (2) connect
one of Riya's projects to their problem with the repo link, (3) soft close
asking for a referral or a quick look. Tone: plain, human, no buzzwords, no
"I am excited", no em dashes. Everything is marked DRAFT.
"""

from __future__ import annotations

import re

from . import config, llm

MAX_LONG = 500
MAX_SHORT = 300


def _strip_dashes(text: str) -> str:
    return text.replace("—", ",").replace("–", "-").replace(" -- ", ", ")


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(",.; ") + "…"


def _template(job: dict, repo: str) -> tuple[str, str]:
    company = job.get("company", "the team") or "the team"
    role = job.get("role") or job.get("title") or "the role"
    blurb = config.REPO_BLURB.get(repo, "a relevant project of mine")

    long_msg = (
        f"Hi, I saw the {role} opening at {company} and it lines up closely with what I build. "
        f"I recently built {blurb} ({repo}), which maps to the kind of problem this role owns. "
        f"Would you be open to a referral, or a quick look at my background?"
    )
    short_msg = (
        f"Hi, I'm applying for the {role} role at {company}. "
        f"I built {blurb} ({repo}) that fits this work well. "
        f"Open to a referral or a quick look?"
    )
    return _clip(_strip_dashes(long_msg), MAX_LONG), _clip(_strip_dashes(short_msg), MAX_SHORT)


def draft(job: dict, repo: str) -> dict:
    """Return {"draft_message", "draft_short"} — both prefixed DRAFT."""
    long_fb, short_fb = _template(job, repo)

    system = (
        "You write short outreach notes for a new-grad ML/software candidate (Riya) "
        "seeking a referral. Rules: plain, human language. No buzzwords. No em dashes. "
        "Do not write 'I am excited'. Ground every claim in the posting text or the named "
        "project. Include the repo URL verbatim. Respond with ONLY a JSON object: "
        '{"long": string, "short": string}. long is <=480 chars, three sentences: '
        "(1) name the role and one specific detail from the posting, (2) connect the "
        "project to their problem with the repo link, (3) a soft close asking for a "
        "referral or a quick look. short is <=280 chars, same idea, connection-note length."
    )
    posting = (job.get("description") or job.get("description_preview") or "")[:1200]
    user = (
        f"Company: {job.get('company', '')}\n"
        f"Role: {job.get('role') or job.get('title', '')}\n"
        f"Project to reference: {config.REPO_BLURB.get(repo, repo)}\n"
        f"Repo URL: {repo}\n"
        f"Posting text: {posting}"
    )
    data = llm.call_json(system, user, max_tokens=500)

    long_msg = long_fb
    short_msg = short_fb
    if data:
        cand_long = _strip_dashes(str(data.get("long", "")).strip())
        cand_short = _strip_dashes(str(data.get("short", "")).strip())
        # Only accept the model's text if it kept the repo link and fits.
        if repo in cand_long:
            long_msg = _clip(cand_long, MAX_LONG)
        if repo in cand_short:
            short_msg = _clip(cand_short, MAX_SHORT)

    return {
        "draft_message": f"[DRAFT] {long_msg}",
        "draft_short": f"[DRAFT] {short_msg}",
    }
