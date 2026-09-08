"""Path B — extract {company, role, ats} from an application-confirmation email.

Email formats vary wildly across ATSs, so the primary path is a single Claude
call returning JSON. A deterministic regex fallback keeps the pipeline (and the
golden tests) working with no network / no key.
"""

from __future__ import annotations

import re
from typing import Optional

from . import llm

# ── ATS detection from the sender address / body domains ────────────────────
_ATS_DOMAINS = [
    ("workday", ("myworkday.com", "myworkdayjobs.com", "workday.com", "@myworkday")),
    ("greenhouse", ("greenhouse.io", "greenhouse-mail.io", "us.greenhouse-mail.io")),
    ("lever", ("lever.co", "hire.lever.co")),
    ("icims", ("icims.com", "talent.icims.com")),
    ("successfactors", ("successfactors.com", "successfactors.eu", "sapsf.com", "@sap")),
    ("ashby", ("ashbyhq.com",)),
    ("smartrecruiters", ("smartrecruiters.com",)),
]


def _detect_ats(sender: str, body: str) -> str:
    blob = f"{sender}\n{body}".lower()
    for name, domains in _ATS_DOMAINS:
        if any(d in blob for d in domains):
            return name
    return "unknown"


# Subject/body phrasings, most specific first. Group 1 = role, group 2 = company
# where both are present; single-group patterns capture company only.
_ROLE_COMPANY = [
    # "...application for the <role> position at <company>."
    re.compile(r"appl(?:ication|ying|ied)[^.\n]*?\bfor\b\s+(?:the\s+)?(.+?)\s+(?:position|role|opening|req)\b[^.\n]*?\bat\s+(.+?)[.!\n]", re.I),
    # "applying to the <role> position/role at <company>."
    re.compile(r"appl(?:ying|ication|ied)\s+(?:to|for)\s+(?:the\s+)?(.+?)\s+(?:position|role|opening)\s+at\s+(.+?)[.!\n]", re.I),
    # "interest in / application for the <role> position at <company>."
    re.compile(r"(?:interest in|application for)\s+(?:the\s+)?(.+?)\s+(?:position|role|opening)\s+at\s+(.+?)[.!\n]", re.I),
    # "applying to <role> at <company>." (no explicit "position" word)
    re.compile(r"appl(?:ying|ied)\s+to\s+(.+?)\s+at\s+(.+?)[.!\n]", re.I),
    # "your application to the <role> position at <company>."
    re.compile(r"your application (?:to|for)\s+(?:the\s+)?(.+?)\s+(?:position|role)\s+at\s+(.+?)[.!\n]", re.I),
]
_COMPANY_ONLY = [
    re.compile(r"thank you for (?:applying|your (?:interest|application)) (?:to|at|in)\s+(.+?)[.!\n]", re.I),
    re.compile(r"your application (?:to|at)\s+(.+?)[.!\n]", re.I),
    re.compile(r"received your application(?:\s+to\s+(.+?))?[.!\n]", re.I),
    re.compile(r"applying to\s+(.+?)[.!\n]", re.I),
]
_ROLE_ONLY = [
    re.compile(r"(?:position|role|opening)\s*[:\-]\s*(.+?)[.!\n]", re.I),
    re.compile(r"appl(?:ication|ied|ying)[^.\n]*?\bfor\b[^.\n]*?\b(?:the\s+)?(.+?)\s+(?:position|role|opening)\b", re.I),
]

_JUNK = re.compile(r"\b(inc|llc|corp|corporation|co|ltd|team|careers|recruiting|talent)\b\.?$", re.I)


def _clean(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.strip().strip(",.;:!").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _regex_extract(subject: str, sender: str, body: str) -> dict:
    text = f"{subject}\n{body}"
    company, role = "", ""
    for pat in _ROLE_COMPANY:
        m = pat.search(text)
        if m:
            role, company = _clean(m.group(1)), _clean(m.group(2))
            break
    if not company:
        for pat in _COMPANY_ONLY:
            m = pat.search(text)
            if m and m.group(1):
                company = _clean(m.group(1))
                break
    if not role:
        for pat in _ROLE_ONLY:
            m = pat.search(text)
            if m and m.group(1):
                role = _clean(m.group(1))
                break
    # Fallback company from a friendly sender name: "Careers at Acme <no-reply@..>"
    if not company and sender:
        m = re.search(r"(?:careers|recruiting|talent|no-?reply)\s+(?:at|@)\s+([A-Z][\w& .-]+)", sender, re.I)
        if m:
            company = _clean(m.group(1))
        else:
            m = re.match(r"\s*([A-Z][\w& .-]{1,40}?)\s*<", sender)
            if m:
                company = _JUNK.sub("", _clean(m.group(1))).strip()
    return {
        "company": company,
        "role": role,
        "ats": _detect_ats(sender, body),
    }


def extract(subject: str, sender: str, body: str) -> dict:
    """Return {company, role, ats}. Claude first, regex fallback on failure."""
    fallback = _regex_extract(subject, sender, body)

    system = (
        "You extract structured fields from a job-application confirmation email. "
        "Respond with ONLY a JSON object of the form "
        '{"company": string, "role": string, "ats": string}. '
        "company is the employer, NOT the applicant tracking system. "
        "role is the job title applied for (empty string if not stated). "
        "ats is one of workday, greenhouse, lever, icims, successfactors, ashby, "
        "smartrecruiters, or unknown."
    )
    user = f"Subject: {subject}\nFrom: {sender}\n\n{body[:3000]}"
    data = llm.call_json(system, user, max_tokens=200)
    if not data:
        return fallback

    company = _clean(str(data.get("company", "")))
    role = _clean(str(data.get("role", "")))
    ats = str(data.get("ats", "")).strip().lower() or fallback["ats"]
    return {
        "company": company or fallback["company"],
        "role": role or fallback["role"],
        "ats": ats if ats != "unknown" else fallback["ats"],
    }
