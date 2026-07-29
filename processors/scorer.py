"""
Job processor — filters by experience level, detects H1B status,
scores resume match using TF-IDF + semantic similarity.
"""

import os
import re
from datetime import datetime, timezone
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from scrapers.ats_scraper import _parse_date


def compute_freshness(date_posted: str, config: dict) -> dict:
    """Turn a raw post date into human freshness + an urgency flag.

    Falls back gracefully when the date is unknown.
    """
    urgent_minutes = config.get("freshness", {}).get("urgent_minutes", 15)
    dt = _parse_date(date_posted)
    if dt is None:
        return {"posted_ago": "recently", "minutes_old": None, "is_urgent": False}

    minutes = max(0, int((datetime.now(timezone.utc) - dt).total_seconds() // 60))
    if minutes < 60:
        ago = f"{minutes} min ago"
    elif minutes < 60 * 48:
        ago = f"{minutes // 60} hr ago"
    else:
        ago = f"{minutes // (60 * 24)} days ago"
    return {
        "posted_ago": ago,
        "minutes_old": minutes,
        "is_urgent": minutes <= urgent_minutes,
    }


def load_resume(path: str = None) -> str:
    """Load the base resume text."""
    path = path or os.getenv("BASE_RESUME_PATH", "resume.txt")
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read()
    print(f"[SCORER] Warning: Resume not found at {path}")
    return ""


# Cache resume text and TF-IDF vectorizer
_resume_text = None
_vectorizer = None
_resume_vector = None


def _init_scorer():
    """Initialize TF-IDF vectorizer with resume."""
    global _resume_text, _vectorizer, _resume_vector
    if _resume_text is None:
        _resume_text = load_resume()
        if _resume_text:
            _vectorizer = TfidfVectorizer(
                stop_words="english", max_features=5000, ngram_range=(1, 2)
            )
            vectors = _vectorizer.fit_transform([_resume_text, "placeholder"])
            _resume_vector = vectors[0]


def check_experience_level(title: str, description: str, config: dict) -> dict:
    """
    Determine if a job matches entry-level / early career criteria.
    Returns: {"level": str, "is_match": bool, "reason": str}
    """
    text = f"{title} {description}".lower()

    include_patterns = config.get("experience_include_patterns", [])
    exclude_patterns = config.get("experience_exclude_patterns", [])

    # Check for explicit exclusions first (senior, staff, etc.)
    for pattern in exclude_patterns:
        if pattern.lower() in text:
            # Exception: "senior" in company name vs title
            if pattern.lower() == "senior" and pattern.lower() not in title.lower():
                continue
            return {
                "level": "Senior+",
                "is_match": False,
                "reason": f"Contains '{pattern}'",
            }

    # Check for explicit entry-level signals
    for pattern in include_patterns:
        if pattern.lower() in text:
            return {
                "level": "Entry/Junior",
                "is_match": True,
                "reason": f"Matches '{pattern}'",
            }

    # No explicit signal — check years of experience in description
    years_pattern = r"(\d+)\+?\s*(?:-\s*\d+)?\s*years?\s*(?:of)?\s*(?:experience|exp)"
    matches = re.findall(years_pattern, text)
    if matches:
        min_years = min(int(y) for y in matches)
        if min_years <= 3:
            return {
                "level": f"{min_years}+ years",
                "is_match": True,
                "reason": f"Requires {min_years}+ years",
            }
        else:
            return {
                "level": f"{min_years}+ years",
                "is_match": False,
                "reason": f"Requires {min_years}+ years",
            }

    # No experience mentioned — likely open to all levels, include it
    return {
        "level": "Not specified",
        "is_match": True,
        "reason": "No experience level specified",
    }


def check_h1b_status(description: str, config: dict) -> str:
    """
    Analyze job description for H1B sponsorship signals.
    Returns: "Likely Sponsors" | "No Sponsorship" | "Unknown"
    """
    text = description.lower()
    h1b_config = config.get("h1b", {})

    # Check negative signals first (more definitive)
    for pattern in h1b_config.get("no_sponsor_patterns", []):
        if pattern.lower() in text:
            return "No Sponsorship"

    # Check positive signals
    for pattern in h1b_config.get("sponsor_patterns", []):
        if pattern.lower() in text:
            return "Likely Sponsors"

    return "Unknown"


def score_keyword_match(job_description: str) -> float:
    """
    TF-IDF cosine similarity between resume and job description.
    Returns score 0-100.
    """
    _init_scorer()
    if not _resume_text or not _vectorizer:
        return 50.0  # Default if no resume loaded

    try:
        job_vec = _vectorizer.transform([job_description])
        similarity = cosine_similarity(_resume_vector, job_vec)[0][0]
        return round(similarity * 100, 1)
    except Exception:
        return 50.0


def score_skills_overlap(description: str) -> float:
    """
    Direct skills matching — checks for specific technical skills from resume
    that appear in the job description. More targeted than TF-IDF.
    Returns 0-100.
    """
    # Key skills from Riya's resume — weighted by importance
    skill_weights = {
        "python": 3,
        "pytorch": 4,
        "tensorflow": 3,
        "keras": 2,
        "scikit-learn": 2,
        "sklearn": 2,
        "langchain": 4,
        "rag": 4,
        "llm": 4,
        "large language model": 4,
        "nlp": 4,
        "natural language processing": 4,
        "deep learning": 4,
        "machine learning": 3,
        "transformer": 4,
        "bert": 3,
        "gpt": 3,
        "fine-tun": 3,
        "attention": 2,
        "aws": 2,
        "redshift": 2,
        "bedrock": 3,
        "docker": 2,
        "sql": 2,
        "pandas": 1,
        "numpy": 1,
        "flask": 2,
        "fastapi": 2,
        "data pipeline": 2,
        "etl": 2,
        "model training": 3,
        "model deploy": 3,
        "model monitor": 3,
        "computer vision": 3,
        "ner": 3,
        "named entity": 3,
        "embedding": 3,
        "vector": 3,
        "retrieval": 3,
        "interpretability": 4,
        "mechanistic": 4,
        "ablation": 3,
        "mcp": 3,
        "agent": 3,
        "agentic": 3,
        "recommendation": 2,
        "classification": 2,
        "prediction": 2,
    }

    text = description.lower()
    total_weight = sum(skill_weights.values())
    matched_weight = sum(w for skill, w in skill_weights.items() if skill in text)

    # Normalize: getting 30%+ of weighted skills is excellent
    score = min(100, (matched_weight / (total_weight * 0.25)) * 100)
    return round(score, 1)


def score_title_match(title: str) -> float:
    """
    Bonus score for titles that directly match target roles.
    Returns 0-30 (this is a bonus, not the full score).
    """
    title_lower = title.lower()

    # Perfect title matches (highest bonus)
    perfect = [
        "machine learning engineer",
        "ml engineer",
        "ai engineer",
        "ai/ml engineer",
        "applied scientist",
        "nlp engineer",
        "deep learning engineer",
        "data scientist",
        "mlops engineer",
        "computer vision engineer",
        "research engineer",
        "ai research",
    ]
    for t in perfect:
        if t in title_lower:
            return 25.0

    # Good title matches
    good = ["ml ", "ai ", "machine learning", "data scien", "artificial intelligence"]
    for t in good:
        if t in title_lower:
            return 15.0

    # Adjacent roles
    adjacent = ["software engineer", "backend engineer", "platform engineer"]
    for t in adjacent:
        if t in title_lower:
            return 5.0

    return 0.0


def score_software_relevance(title: str, description: str, config: dict) -> float:
    """Relevance for general software roles, based on software_keywords. 0-100."""
    text = f"{title} {description}".lower()
    kws = config.get("software_keywords", [])
    if not kws:
        return 50.0
    matches = sum(1 for kw in kws if kw.lower() in text)
    return round(min(100, (matches / min(3, len(kws))) * 100), 1)


def score_software_title(title: str) -> float:
    """Title bonus for software roles (0-25), mirroring score_title_match."""
    t = title.lower()
    strong = [
        "software engineer",
        "software developer",
        "backend engineer",
        "frontend engineer",
        "full stack",
        "full-stack",
        "fullstack",
        "platform engineer",
        "site reliability",
        "devops engineer",
        "cloud engineer",
        "systems engineer",
    ]
    if any(s in t for s in strong):
        return 25.0
    if any(s in t for s in ["engineer", "developer"]):
        return 12.0
    return 0.0


def score_relevance(title: str, description: str, config: dict) -> float:
    """
    Score how relevant a job is to AI/ML based on keyword density.
    Returns 0-100.
    """
    text = f"{title} {description}".lower()
    keywords = config.get("relevance_keywords", [])

    if not keywords:
        return 50.0

    matches = sum(1 for kw in keywords if kw.lower() in text)
    # Normalize: 5+ keyword matches = 100%
    score = min(100, (matches / min(5, len(keywords))) * 100)
    return round(score, 1)


def extract_skills_match(description: str, config: dict) -> str:
    """Extract which AI/ML keywords are found in the job description."""
    text = description.lower()
    keywords = config.get("relevance_keywords", [])
    found = [kw for kw in keywords if kw.lower() in text]
    return ", ".join(found[:8])  # Top 8 matching skills


def is_us_location(location: str) -> bool:
    """Check if a job location is in the United States."""
    if not location:
        return True  # No location info — include it, better safe than sorry

    loc = location.lower().strip()

    # Explicit US signals
    us_signals = [
        "united states",
        "usa",
        ", us",
        " us,",
        "remote",
        "hybrid",  # Remote/hybrid with no country = likely US
    ]
    if any(sig in loc for sig in us_signals):
        return True

    # US state abbreviations (2-letter) and common city patterns
    us_states = [
        ", al",
        ", ak",
        ", az",
        ", ar",
        ", ca",
        ", co",
        ", ct",
        ", de",
        ", fl",
        ", ga",
        ", hi",
        ", id",
        ", il",
        ", in",
        ", ia",
        ", ks",
        ", ky",
        ", la",
        ", me",
        ", md",
        ", ma",
        ", mi",
        ", mn",
        ", ms",
        ", mo",
        ", mt",
        ", ne",
        ", nv",
        ", nh",
        ", nj",
        ", nm",
        ", ny",
        ", nc",
        ", nd",
        ", oh",
        ", ok",
        ", or",
        ", pa",
        ", ri",
        ", sc",
        ", sd",
        ", tn",
        ", tx",
        ", ut",
        ", vt",
        ", va",
        ", wa",
        ", wv",
        ", wi",
        ", wy",
        ", dc",
    ]
    if any(loc.endswith(st) or st + " " in loc or st + "," in loc for st in us_states):
        return True

    # Full state names
    us_state_names = [
        "alabama",
        "alaska",
        "arizona",
        "arkansas",
        "california",
        "colorado",
        "connecticut",
        "delaware",
        "florida",
        "georgia",
        "hawaii",
        "idaho",
        "illinois",
        "indiana",
        "iowa",
        "kansas",
        "kentucky",
        "louisiana",
        "maine",
        "maryland",
        "massachusetts",
        "michigan",
        "minnesota",
        "mississippi",
        "missouri",
        "montana",
        "nebraska",
        "nevada",
        "new hampshire",
        "new jersey",
        "new mexico",
        "new york",
        "north carolina",
        "north dakota",
        "ohio",
        "oklahoma",
        "oregon",
        "pennsylvania",
        "rhode island",
        "south carolina",
        "south dakota",
        "tennessee",
        "texas",
        "utah",
        "vermont",
        "virginia",
        "washington",
        "west virginia",
        "wisconsin",
        "wyoming",
        "district of columbia",
    ]
    if any(state in loc for state in us_state_names):
        return True

    # Non-US signals — reject these
    non_us = [
        "india",
        "germany",
        "uk",
        "united kingdom",
        "canada",
        "france",
        "australia",
        "singapore",
        "japan",
        "china",
        "brazil",
        "mexico",
        "ireland",
        "netherlands",
        "spain",
        "italy",
        "sweden",
        "switzerland",
        "israel",
        "korea",
        "taiwan",
        "hong kong",
        "bangalore",
        "mumbai",
        "hyderabad",
        "delhi",
        "pune",
        "chennai",
        "kolkata",
        "ahmedabad",
        "london",
        "berlin",
        "munich",
        "paris",
        "amsterdam",
        "dublin",
        "toronto",
        "vancouver",
        "montreal",
        "sydney",
        "melbourne",
        "karnataka",
        "telangana",
        "maharashtra",
        "tamil nadu",
        "gujarat",
        "bavaria",
        "ontario",
        "british columbia",
        "quebec",
        "bengaluru",
        "noida",
        "gurgaon",
        "gurugram",
    ]
    if any(place in loc for place in non_us):
        return False

    # No clear signal either way — include it
    return True


def is_staffing(title: str, company: str, description: str, config: dict) -> bool:
    """Detect staffing / recruiting-agency reposts so they never alert.

    Uses two signals:
      1. Strong staffing words in the COMPANY NAME (e.g. "Staffing", "Recruiting").
      2. Tell-tale phrases in the DESCRIPTION that only staffing/body-shop posts
         use ("our client", "corp to corp", "C2C", "W2 only", "end client"...).
    Name-only matching is deliberately narrow to avoid nuking real employers
    like "Palantir Technologies" or "Scale Solutions".
    """
    cfg = config.get("staffing", {})
    if not cfg.get("enabled", True):
        return False

    name = (company or "").lower()
    for pat in cfg.get("exclude_company_patterns", []):
        if pat.lower() in name:
            return True

    text = f"{title} {description}".lower()
    for pat in cfg.get("exclude_description_patterns", []):
        if pat.lower() in text:
            return True

    return False


def process_jobs(raw_jobs: list[dict], config: dict) -> list[dict]:
    """
    Full processing pipeline:
    1. Deduplicate
    2. Filter by experience level
    3. Check H1B status
    4. Score resume match
    5. Sort by score
    """
    from storage.db import (
        is_duplicate,
        mark_seen,
        is_board_initialized,
        mark_board_initialized,
    )

    processed = []
    seen_urls = set()

    # ── Cold-start guard ────────────────────────────────────────────────
    # The first time we ever poll a company's board, silently seed its current
    # postings as "seen" (no alert) so a newly added company never floods you
    # with its whole backlog marked "new". Boards present in this batch that
    # we've never seen before are collected here and marked initialized at the
    # end of processing.
    silent_first_poll = config.get("cold_start", {}).get("silent_first_poll", True)
    boards_in_batch = set()
    silent_boards = set()
    if silent_first_poll:
        for job in raw_jobs:
            bkey = f"{job.get('source', '')}:{job.get('company', '')}"
            if bkey in boards_in_batch:
                continue
            boards_in_batch.add(bkey)
            if not is_board_initialized(bkey):
                silent_boards.add(bkey)
        if silent_boards:
            print(
                f"[PROCESSOR] Cold-start: silently seeding {len(silent_boards)} "
                f"new board(s) — their existing jobs won't alert."
            )

    for job in raw_jobs:
        url = job.get("url", "")
        title = job.get("title", "")
        company = job.get("company", "")
        description = job.get("description", "")

        # Skip if no URL or already processed in this batch
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        # Cold-start: a board we've never polled — seed silently, don't alert.
        bkey = f"{job.get('source', '')}:{company}"
        if bkey in silent_boards:
            mark_seen(url, title, company, score=0)
            continue

        # Skip if we've seen this before
        if is_duplicate(url, title, company):
            continue

        # Filter non-US locations
        location = job.get("location", "")
        if not is_us_location(location):
            mark_seen(url, title, company, score=0)
            continue

        # Filter staffing / recruiting-agency reposts
        if is_staffing(title, company, description, config):
            mark_seen(url, title, company, score=0)
            continue

        # Check experience level
        exp = check_experience_level(title, description, config)
        if not exp["is_match"]:
            mark_seen(url, title, company, score=0)
            continue

        category = job.get("role_category", "ml")
        keyword_score = score_keyword_match(description)  # TF-IDF vs résumé
        skills_score = score_skills_overlap(description)

        if category == "software":
            # Software roles are scored on software signals (the ML-tuned
            # relevance would zero them out). Kept a notch below ML overall.
            relevance = score_software_relevance(title, description, config)
            title_bonus = score_software_title(title)
            if relevance < 10 and title_bonus == 0:
                mark_seen(url, title, company, score=0)
                continue
            base_score = (
                (0.15 * keyword_score)
                + (0.30 * relevance)
                + (0.20 * skills_score)
                + (0.30 * title_bonus * 4)
            )
            combined_score = min(100, base_score) * 0.9
        else:
            # AI/ML path
            relevance = score_relevance(title, description, config)
            if relevance < 20:
                mark_seen(url, title, company, score=0)
                continue
            title_bonus = score_title_match(title)
            # 15% TF-IDF keyword overlap / 25% AI-ML relevance /
            # 35% skills overlap / 25% title-match bonus
            base_score = (
                (0.15 * keyword_score)
                + (0.25 * relevance)
                + (0.35 * skills_score)
                + (0.25 * title_bonus * 4)
            )
            combined_score = min(100, base_score)

        # H1B check
        h1b = check_h1b_status(description, config)

        # Skills extraction
        skills = extract_skills_match(description, config)

        # Freshness — real "posted X ago" + urgency flag
        fresh = compute_freshness(job.get("date_posted", ""), config)

        # Build processed job
        processed_job = {
            **job,
            "score": round(combined_score, 1),
            "keyword_score": keyword_score,
            "skills_score": skills_score,
            "relevance_score": relevance,
            "title_bonus": title_bonus,
            "h1b_status": h1b,
            "experience_level": exp["level"],
            "skills_match": skills,
            "description_preview": description[:300] if description else "",
            "role_category": job.get("role_category", "ml"),
            "posted_ago": fresh["posted_ago"],
            "minutes_old": fresh["minutes_old"],
            "is_urgent": fresh["is_urgent"],
        }

        processed.append(processed_job)
        mark_seen(url, title, company, score=combined_score)

    # Record any first-time boards as initialized now that their backlog is seeded.
    for bkey in silent_boards:
        mark_board_initialized(bkey)
    for bkey in boards_in_batch:
        mark_board_initialized(bkey)

    # Sort: urgent first, then by score.
    processed.sort(key=lambda j: (j.get("is_urgent", False), j["score"]), reverse=True)

    print(
        f"[PROCESSOR] {len(processed)} new jobs after filtering (from {len(raw_jobs)} raw)"
    )
    return processed
