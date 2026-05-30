import os
from supabase import create_client, Client
from dotenv import load_dotenv
from utils.url import clean_url

load_dotenv()

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    return _client


def get_seen_urls() -> set[str]:
    res = get_client().table("jobs").select("url").execute()
    return {clean_url(row["url"]) for row in res.data}


def insert_jobs(jobs: list[dict]) -> int:
    if not jobs:
        return 0
    rows = [
        {
            "company": j.get("company"),
            "role": j.get("title"),
            "url": clean_url(j.get("url", "")),
            "source": j.get("source"),
            "date_found": j.get("date_found"),
            "score": j.get("score"),
            "snippet": j.get("snippet"),
            "work_auth_ok": True,
            "status": "found",
        }
        for j in jobs
    ]
    res = get_client().table("jobs").insert(rows).execute()
    return len(res.data)


def update_status(job_url: str, status: str) -> None:
    get_client().table("jobs").update({"status": status}).eq("url", clean_url(job_url)).execute()


def update_cover_letter_path(job_url: str, path: str) -> None:
    get_client().table("jobs").update({"cover_letter_path": path}).eq("url", clean_url(job_url)).execute()


def insert_filtered_out(jobs: list[dict]) -> None:
    """Save filter-rejected and low-score jobs so they're skipped on future runs."""
    if not jobs:
        return
    rows = [
        {
            "company": j.get("company"),
            "role": j.get("title"),
            "url": clean_url(j.get("url", "")),
            "source": j.get("source"),
            "date_found": j.get("date_found"),
            "score": j.get("score"),
            "work_auth_ok": j.get("status") != "rejected",
            "status": j.get("status", "rejected"),
        }
        for j in jobs
        if j.get("url")
    ]
    if rows:
        get_client().table("jobs").upsert(rows, on_conflict="url").execute()


def get_pending_jobs(limit: int = 25) -> list[dict]:
    res = (
        get_client()
        .table("jobs")
        .select("*")
        .eq("status", "found")
        .order("score", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data


def get_active_jobs(limit: int = 25) -> list[dict]:
    """Return found + pending_approval jobs sorted by score (stable numbering for commands)."""
    res = (
        get_client()
        .table("jobs")
        .select("*")
        .in_("status", ["found", "pending_approval"])
        .order("score", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data


def store_application_data(job_url: str, data: dict) -> None:
    """Save planned application answers and set status to pending_approval."""
    import json
    get_client().table("jobs").update({
        "status": "pending_approval",
        "application_data": json.dumps(data),
    }).eq("url", clean_url(job_url)).execute()


def get_job_by_url(job_url: str) -> dict | None:
    """Fetch a single job row by URL."""
    res = (
        get_client()
        .table("jobs")
        .select("*")
        .eq("url", clean_url(job_url))
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None
