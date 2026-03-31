"""
Job processor — filters by experience level, detects H1B status,
scores resume match using TF-IDF + semantic similarity.
"""
import os
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


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
                stop_words="english",
                max_features=5000,
                ngram_range=(1, 2)
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
                "reason": f"Contains '{pattern}'"
            }
    
    # Check for explicit entry-level signals
    for pattern in include_patterns:
        if pattern.lower() in text:
            return {
                "level": "Entry/Junior",
                "is_match": True,
                "reason": f"Matches '{pattern}'"
            }
    
    # No explicit signal — check years of experience in description
    years_pattern = r'(\d+)\+?\s*(?:-\s*\d+)?\s*years?\s*(?:of)?\s*(?:experience|exp)'
    matches = re.findall(years_pattern, text)
    if matches:
        min_years = min(int(y) for y in matches)
        if min_years <= 3:
            return {"level": f"{min_years}+ years", "is_match": True, "reason": f"Requires {min_years}+ years"}
        else:
            return {"level": f"{min_years}+ years", "is_match": False, "reason": f"Requires {min_years}+ years"}
    
    # No experience mentioned — likely open to all levels, include it
    return {"level": "Not specified", "is_match": True, "reason": "No experience level specified"}


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
        "python": 3, "pytorch": 4, "tensorflow": 3, "keras": 2,
        "scikit-learn": 2, "sklearn": 2, "langchain": 4, "rag": 4,
        "llm": 4, "large language model": 4, "nlp": 4, "natural language processing": 4,
        "deep learning": 4, "machine learning": 3, "transformer": 4,
        "bert": 3, "gpt": 3, "fine-tun": 3, "attention": 2,
        "aws": 2, "redshift": 2, "bedrock": 3,
        "docker": 2, "sql": 2, "pandas": 1, "numpy": 1,
        "flask": 2, "fastapi": 2, "data pipeline": 2, "etl": 2,
        "model training": 3, "model deploy": 3, "model monitor": 3,
        "computer vision": 3, "ner": 3, "named entity": 3,
        "embedding": 3, "vector": 3, "retrieval": 3,
        "interpretability": 4, "mechanistic": 4, "ablation": 3,
        "mcp": 3, "agent": 3, "agentic": 3,
        "recommendation": 2, "classification": 2, "prediction": 2,
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
        "machine learning engineer", "ml engineer", "ai engineer",
        "ai/ml engineer", "applied scientist", "nlp engineer",
        "deep learning engineer", "data scientist",
        "mlops engineer", "computer vision engineer",
        "research engineer", "ai research",
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


def process_jobs(raw_jobs: list[dict], config: dict) -> list[dict]:
    """
    Full processing pipeline:
    1. Deduplicate
    2. Filter by experience level
    3. Check H1B status
    4. Score resume match
    5. Sort by score
    """
    from storage.db import is_duplicate, mark_seen
    
    processed = []
    seen_urls = set()
    
    for job in raw_jobs:
        url = job.get("url", "")
        title = job.get("title", "")
        company = job.get("company", "")
        description = job.get("description", "")
        
        # Skip if no URL or already processed in this batch
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        
        # Skip if we've seen this before
        if is_duplicate(url, title, company):
            continue
        
        # Check experience level
        exp = check_experience_level(title, description, config)
        if not exp["is_match"]:
            mark_seen(url, title, company, score=0)
            continue
        
        # Check AI/ML relevance
        relevance = score_relevance(title, description, config)
        if relevance < 20:
            mark_seen(url, title, company, score=0)
            continue
        
        # Score resume match — multi-signal approach
        keyword_score = score_keyword_match(description)
        skills_score = score_skills_overlap(description)
        title_bonus = score_title_match(title)
        
        # Combined score:
        # 15% TF-IDF keyword overlap (broad similarity)
        # 25% AI/ML relevance (are the right topics mentioned?)
        # 35% Skills overlap (specific technical skills match)
        # 25% Title match bonus (is this actually a target role?)
        base_score = (0.15 * keyword_score) + (0.25 * relevance) + (0.35 * skills_score) + (0.25 * title_bonus * 4)
        combined_score = min(100, base_score)
        
        # H1B check
        h1b = check_h1b_status(description, config)
        
        # Skills extraction
        skills = extract_skills_match(description, config)
        
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
        }
        
        processed.append(processed_job)
        mark_seen(url, title, company, score=combined_score)
    
    # Sort by score descending
    processed.sort(key=lambda j: j["score"], reverse=True)
    
    print(f"[PROCESSOR] {len(processed)} new jobs after filtering (from {len(raw_jobs)} raw)")
    return processed