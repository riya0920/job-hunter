"""
Instant-apply assist.

Knowing about a job first only wins if you also APPLY first. For the strongest
matches, this drafts a one-line, resume-grounded pitch (via Gemini) and attaches
it to the job so it rides along in your alert — turning "I heard about it early"
into "I applied within minutes."

Fully optional and defensive: no GEMINI_API_KEY, or any error, and it simply
skips (jobs pass through unchanged). Costs a fraction of a cent per job and only
runs for jobs above `tailor_min_score`, capped at `tailor_max_jobs` per cycle.
"""

import os
import requests

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)


def _load_resume() -> str:
    path = os.getenv("BASE_RESUME_PATH", "resume.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def _draft_pitch(job: dict, resume: str, model: str, key: str) -> str | None:
    prompt = (
        "You are helping a candidate apply FAST to a freshly posted job. "
        "Using only facts supported by the resume, write ONE punchy sentence "
        "(max 30 words) the candidate can drop into an application's "
        "'why you' box. No preamble, no dashes, plain text only.\n\n"
        f"JOB TITLE: {job.get('title', '')}\n"
        f"COMPANY: {job.get('company', '')}\n"
        f"JOB SNIPPET: {job.get('description_preview', '')[:600]}\n\n"
        f"RESUME:\n{resume[:3000]}"
    )
    try:
        resp = requests.post(
            _GEMINI_URL.format(model=model, key=key),
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.4, "maxOutputTokens": 80},
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text.replace("\n", " ").replace("—", " ").replace("–", " ").strip() or None
    except Exception:
        return None


def add_tailored_pitches(jobs: list[dict], config: dict) -> list[dict]:
    """Attach `tailored_pitch` to the strongest matches. Mutates and returns jobs."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return jobs

    tcfg = config.get("tailor", {})
    if not tcfg.get("enabled", True):
        return jobs
    min_score = tcfg.get("min_score", 60)
    max_jobs = tcfg.get("max_jobs", 8)
    model = os.getenv("GEMINI_MODEL", tcfg.get("model", "gemini-2.5-flash"))

    resume = _load_resume()
    if not resume:
        return jobs

    # Best matches first, capped for cost control.
    candidates = sorted(
        [j for j in jobs if j.get("score", 0) >= min_score],
        key=lambda j: j.get("score", 0),
        reverse=True,
    )[:max_jobs]

    drafted = 0
    for job in candidates:
        pitch = _draft_pitch(job, resume, model, key)
        if pitch:
            job["tailored_pitch"] = pitch
            drafted += 1
    if drafted:
        print(f"[TAILOR] Drafted {drafted} instant-apply pitches")
    return jobs
