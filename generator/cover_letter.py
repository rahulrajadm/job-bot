import anthropic
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

RESUME_PATH = Path(__file__).parent.parent / "data" / "resume.txt"
APPLICATIONS_DIR = Path(__file__).parent.parent / "applications"

_resume_text: str | None = None


def _get_resume() -> str:
    global _resume_text
    if _resume_text is None:
        _resume_text = RESUME_PATH.read_text()
    return _resume_text


def generate_cover_letter(job: dict) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resume = _get_resume()

    system_prompt = f"""You are a professional cover letter writer helping the applicant apply for jobs.

Here is the applicant's resume:

{resume}

Write cover letters that are:
- Professional but warm and genuine in tone
- Concise (3 short paragraphs max)
- Specific to the job — reference the company name and role
- Grounded in the applicant's real experience as described in the resume above
- Honest about their background
- Never fabricate experience or credentials not in the resume"""

    user_prompt = f"""Write a cover letter for this job:

Company: {job.get('company')}
Role: {job.get('role') or job.get('title')}
Job description / snippet: {job.get('snippet', 'No description available')}
URL: {job.get('url')}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    return response.content[0].text


def save_cover_letter(job: dict, text: str) -> str:
    company = (job.get("company") or "unknown").replace(" ", "-").lower()
    role = (job.get("role") or job.get("title") or "role").replace(" ", "-").lower()
    folder = APPLICATIONS_DIR / f"{company}-{role}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "cover-letter.md"
    path.write_text(f"# Cover Letter — {job.get('company')} | {job.get('role') or job.get('title')}\n\n{text}\n")
    return str(path)
