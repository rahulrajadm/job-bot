"""
Maps LinkedIn Easy Apply form question labels to the applicant's answers.
Uses qa_profile.yaml for structured fields, Claude Haiku for open-ended questions.
"""

import os
import yaml
import anthropic
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

QA_PROFILE_PATH = Path(__file__).parent.parent / "data" / "qa_profile.yaml"
_profile: dict | None = None


def _load_profile() -> dict:
    global _profile
    if _profile is None:
        _profile = yaml.safe_load(QA_PROFILE_PATH.read_text())
    return _profile


def answer_question(label: str, job: dict | None = None) -> str:
    """Return the best answer for a form question based on its label text."""
    profile = _load_profile()
    L = label.lower().strip().rstrip("*").strip()

    p = profile["personal"]
    edu = profile["education"]
    wa = profile["work_authorization"]
    sal = profile["salary"]
    avail = profile["availability"]
    exp = profile["experience"]
    cq = profile["common_question_answers"]

    # ----- Contact / Identity -----
    if _any(L, ["first name", "given name"]):
        return p["first_name"]
    if _any(L, ["last name", "family name", "surname"]):
        return p["last_name"]
    if _any(L, ["full name", "your name", "legal name"]):
        return p["full_name"]
    if _any(L, ["phone", "mobile", "cell"]):
        return p["phone"]
    if "email" in L:
        return p["email"]
    if _any(L, ["linkedin", "linkedin url", "linkedin profile"]):
        return p["linkedin_url"]
    if _any(L, ["city", "current city"]):
        return p["city"]
    if "state" in L and "united states" not in L:
        return p["state"]
    if _any(L, ["country", "country of residence"]):
        return p["country"]
    if _any(L, ["zip", "postal code"]):
        return p["zip"]
    if _any(L, ["address", "street address"]):
        return f"{p['city']}, {p['state_abbr']}"
    if "location" in L:
        return f"{p['city']}, {p['state_abbr']}"

    # ----- Work Authorization -----
    if _any(L, ["authorized to work", "legally authorized", "work authorization",
                "eligible to work", "legally eligible", "work in the u.s",
                "work in the us", "right to work"]):
        return "Yes"
    if _any(L, ["require sponsorship", "need sponsorship", "visa sponsorship",
                "require work authorization", "sponsorship now or in the future"]):
        return "No"
    if "visa" in L and "sponsorship" not in L:
        return wa["visa_type"]

    # ----- Education -----
    if _any(L, ["gpa", "grade point"]):
        return edu["gpa"]
    if _any(L, ["graduation date", "expected graduation", "graduation year",
                "date of graduation", "when will you graduate", "when did you graduate"]):
        return edu["graduation_date"]
    if _any(L, ["degree", "highest degree", "highest level of education",
                "education level", "highest education"]):
        return edu["level"]
    if _any(L, ["university", "college", "school", "institution", "attended"]):
        return edu["university"]
    if _any(L, ["field of study", "major", "concentration", "area of study", "discipline"]):
        return edu["major"]
    if _any(L, ["minor"]):
        return edu["minor"]

    # ----- Salary -----
    if _any(L, ["salary", "compensation", "expected salary", "desired salary",
                "pay expectations", "salary expectations", "pay range"]):
        return sal["preferred_range"]
    if _any(L, ["salary minimum", "minimum salary"]):
        return str(sal["min"])
    if _any(L, ["salary maximum", "maximum salary"]):
        return str(sal["max"])

    # ----- Availability / Timing -----
    if _any(L, ["start date", "when can you start", "earliest start",
                "available to start", "date available"]):
        return avail["start_date"]
    if _any(L, ["notice period", "notice required"]):
        return "2 weeks"

    # ----- Experience -----
    if _any(L, ["years of experience", "how many years", "years experience",
                "total years", "professional experience"]):
        return exp["years_total"]
    if _any(L, ["years of python", "python experience"]):
        return exp["years_python"]
    if _any(L, ["years of machine learning", "ml experience"]):
        return exp["years_machine_learning"]

    # ----- Employment -----
    if _any(L, ["current employer", "current company", "current organization"]):
        return cq["current_employer"]
    if _any(L, ["current title", "current position", "current role", "job title"]):
        return cq["current_title"]
    if _any(L, ["reason for leaving", "why leaving", "why are you leaving"]):
        return cq["reason_leaving"]
    if _any(L, ["employment type", "job type"]):
        return "Full-time"
    if _any(L, ["willing to relocate", "open to relocation", "relocation"]):
        return "Yes"
    if _any(L, ["willing to travel", "travel requirement", "travel percentage"]):
        return "Yes, up to 25%"
    if _any(L, ["remote work", "work remotely", "open to remote"]):
        return "Yes"

    # ----- Diversity / Legal -----
    if _any(L, ["veteran", "military service", "military status"]):
        return profile["diversity"]["veteran"]
    if _any(L, ["disability", "disabled", "accommodation"]):
        return "No"
    if "gender" in L:
        return profile["diversity"]["gender"]
    if _any(L, ["hispanic", "latino"]):
        return profile["diversity"]["hispanic"]
    if _any(L, ["ethnicity", "race"]):
        return profile["diversity"]["ethnicity"]

    # ----- Other structured answers -----
    if _any(L, ["references", "reference available"]):
        return "Yes, available upon request"
    if _any(L, ["certifications", "certificates", "licenses"]):
        return profile["certifications"]
    if _any(L, ["languages", "language skills"]):
        return profile["languages"]
    if _any(L, ["cover letter"]):
        return ""  # handled separately

    # ----- Fallback: Claude for open-ended questions -----
    return _ask_claude(label, job, profile)


def _any(text: str, keywords: list[str]) -> bool:
    return any(kw in text for kw in keywords)


def _ask_claude(question: str, job: dict | None, profile: dict) -> str:
    """Use Claude Haiku to answer an open-ended application question."""
    company = (job.get("company", "the company") if job else "the company")
    role = (job.get("role") or job.get("title", "this role") if job else "this role")
    snippet = (job.get("snippet", "") if job else "")

    p = profile["personal"]
    edu = profile["education"]
    wa = profile["work_authorization"]
    sal = profile["salary"]

    background_lines = [
        f"- Name: {p['full_name']}",
        f"- Degree: {edu['level']} in {edu['major']}, {edu['university']} ({edu['graduation_date']}), GPA {edu['gpa']}",
        f"- Work auth: {wa['visa_type']}, no sponsorship needed",
        f"- Expected salary: {sal['preferred_range']}",
        f"- Skills: {profile.get('skills', 'See resume')}",
        f"- Languages: {profile.get('languages', 'See resume')}",
    ]

    prompt = f"""You are filling out a job application form for {p['full_name']}.

Job: {role} at {company}
Job description: {snippet[:300] if snippet else "Not provided"}

Applicant background (key facts):
{chr(10).join(background_lines)}

Answer this application question concisely (2–3 sentences max). Be specific and genuine. Use first person. No preamble, no sign-off — just the answer itself.

Question: {question}"""

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def preview_application(job: dict) -> dict:
    """Return an ordered preview of answers for common Easy Apply fields."""
    profile = _load_profile()
    p = profile["personal"]
    edu = profile["education"]

    return {
        "Name": p["full_name"],
        "Email": p["email"],
        "Phone": p["phone"],
        "Location": f"{p['city']}, {p['state_abbr']}",
        "LinkedIn": p["linkedin_url"],
        "Work authorized (US)": f"Yes — {profile['work_authorization']['visa_type']}",
        "Requires sponsorship": "No",
        "Degree": f"{edu['level']} — {edu['major']}, {edu['university_short']} ({edu['graduation_date']})",
        "GPA": edu["gpa"],
        "Expected salary": profile["salary"]["preferred_range"],
        "Available from": profile["availability"]["start_date"],
        "Open to relocation": "Yes",
    }
