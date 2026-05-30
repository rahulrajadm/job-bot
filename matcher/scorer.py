from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from pathlib import Path

RESUME_PATH = Path(__file__).parent.parent / "data" / "resume.txt"

BONUS_KEYWORDS = [
    "python", "machine learning", "ml", "data science", "ai", "artificial intelligence",
    "biomedical", "computational", "r statistics", "sql", "modeling", "analytics",
    "research", "oncology", "clinical", "jupyter", "scikit", "tensorflow", "pytorch",
    "consulting", "entry level", "new grad", "internship",
]

_resume_text: str | None = None


def _get_resume() -> str:
    global _resume_text
    if _resume_text is None:
        _resume_text = RESUME_PATH.read_text()
    return _resume_text


def score_job(job: dict) -> float:
    resume = _get_resume()
    job_text = f"{job.get('title', '')} {job.get('company', '')} {job.get('snippet', '')}"

    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf = vectorizer.fit_transform([resume, job_text])
    similarity = float(cosine_similarity(tfidf[0], tfidf[1])[0][0])

    lowered = job_text.lower()
    bonus = sum(0.02 for kw in BONUS_KEYWORDS if kw in lowered)

    return round(min(similarity + bonus, 1.0), 4)


def score_and_rank(jobs: list[dict]) -> list[dict]:
    if not jobs:
        return []

    resume = _get_resume()
    job_texts = [
        f"{j.get('title', '')} {j.get('company', '')} {j.get('snippet', '')}"
        for j in jobs
    ]

    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf = vectorizer.fit_transform([resume] + job_texts)
    raw_scores = cosine_similarity(tfidf[0:1], tfidf[1:])[0]

    # Add keyword bonuses
    adjusted = []
    for job, base_score in zip(jobs, raw_scores):
        job_text = f"{job.get('title', '')} {job.get('snippet', '')}".lower()
        bonus = sum(0.02 for kw in BONUS_KEYWORDS if kw in job_text)
        adjusted.append(float(base_score) + bonus)

    # Normalize to 50–95% range so scores feel meaningful and relative
    min_s, max_s = min(adjusted), max(adjusted)
    spread = max_s - min_s if max_s > min_s else 1.0
    for job, raw in zip(jobs, adjusted):
        normalized = 0.50 + ((raw - min_s) / spread) * 0.45
        job["score"] = round(normalized, 4)

    return sorted(jobs, key=lambda j: j["score"], reverse=True)
