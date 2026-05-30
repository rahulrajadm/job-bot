from jobspy import scrape_jobs
from datetime import date
import pandas as pd
from utils.url import clean_url

SEARCH_QUERIES = [
    "data scientist entry level",
    "machine learning engineer new grad",
    "AI engineer entry level",
    "biomedical data analyst entry level",
    "computational research scientist entry level",
    "consulting analyst entry level",
    "data analyst entry level",
    "research scientist machine learning",
    "summer 2026 data science internship",
    "summer 2026 machine learning internship",
    "biomedical engineer data science",
    "junior software engineer machine learning",
]

SOURCES = ["indeed", "linkedin", "zip_recruiter"]

REJECT_CITIZENSHIP = [
    "must be a us citizen",
    "us citizenship required",
    "requires us citizenship",
    "active security clearance",
    "secret clearance",
    "top secret",
    "green card required",
    "permanent resident required",
    "no work visa",
    "no sponsorship",
]

REJECT_EXPERIENCE = [
    "3+ years", "4+ years", "5+ years", "6+ years", "7+ years", "8+ years",
    "three or more years", "minimum 3 years", "minimum 4 years",
    "at least 3 years", "at least 4 years",
    "3 years of experience", "4 years of experience", "5 years of experience",
    "3 or more years", "4 or more years",
    # PhD filters
    "ph.d. required", "phd required", "ph.d required",
    "requires a ph.d", "requires a phd", "requires ph.d",
    "must have a ph.d", "must have a phd",
    "ph.d. or equivalent", "phd or equivalent",
    "doctorate required", "doctoral degree required",
]

REJECT_TITLE_WORDS = [
    "senior", "sr.", "sr ", " sr ", "staff ", "principal", " lead ", "director",
    "vice president", " vp ", "head of", "manager", "chief", "architect",
    "distinguished", "fellow",
]

ALLOW_TITLE_WORDS = ["associate", "junior", "jr.", "entry", "intern", "co-op", "new grad"]


def _passes_title(title: str) -> bool:
    lowered = title.lower()
    if any(w in lowered for w in ALLOW_TITLE_WORDS):
        return True
    if any(w in lowered for w in REJECT_TITLE_WORDS):
        return False
    return True


def _passes_filters(title: str, description: str) -> bool:
    lowered = description.lower()
    if any(phrase in lowered for phrase in REJECT_CITIZENSHIP):
        return False
    if any(phrase in lowered for phrase in REJECT_EXPERIENCE):
        return False
    if not _passes_title(title):
        return False
    return True


def _row_to_job(row: pd.Series, query: str, source: str) -> dict:
    description = str(row.get("description") or "")
    title = str(row.get("title") or "")
    company = str(row.get("company") or "Unknown")
    location = str(row.get("location") or "Unknown")
    url = clean_url(str(row.get("job_url") or ""))
    snippet = description[:300].strip()

    return {
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "snippet": snippet,
        "source": source,
        "query": query,
        "date_found": str(date.today()),
    }


def scrape_all(max_results: int = 75) -> tuple[list[dict], list[dict]]:
    """Scrape Indeed, LinkedIn, and ZipRecruiter via JobSpy.

    Returns:
        (passed, rejected) — passed jobs cleared all filters,
        rejected jobs failed at least one filter.
    """
    passed = []
    rejected = []
    seen_urls: set[str] = set()

    for query in SEARCH_QUERIES:
        if len(passed) >= max_results:
            break
        for source in SOURCES:
            try:
                kwargs = dict(
                    site_name=[source],
                    search_term=query,
                    location="United States",
                    results_wanted=10,
                    hours_old=48,
                )
                if source == "indeed":
                    kwargs["country_indeed"] = "USA"

                df = scrape_jobs(**kwargs)
                if df is None or df.empty:
                    continue

                for _, row in df.iterrows():
                    url = clean_url(str(row.get("job_url") or ""))
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    title = str(row.get("title") or "")
                    description = str(row.get("description") or "")
                    job = _row_to_job(row, query, source.title())
                    if not _passes_filters(title, description):
                        job["status"] = "rejected"
                        rejected.append(job)
                    else:
                        passed.append(job)

            except Exception as e:
                print(f"[{source.title()}] Error on '{query}': {e}")
                continue

    return passed[:max_results], rejected
