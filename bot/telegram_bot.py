import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

BATCH_SIZE = 5


def _send(method: str, **kwargs) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/{method}",
        json=kwargs,
        timeout=15,
    )
    data = resp.json()
    if not data.get("ok"):
        print(f"[Telegram] API error: {data.get('description')}")
    return data


def _escape(text: str) -> str:
    """Escape special Markdown v1 characters in dynamic content."""
    if not text:
        return ""
    return re.sub(r"([*_`\[\]])", r"\\\1", str(text))


def send_message(text: str, parse_mode: str = "Markdown") -> None:
    try:
        kwargs = dict(
            chat_id=os.environ["TELEGRAM_CHAT_ID"],
            text=text,
            disable_web_page_preview=True,
        )
        if parse_mode:
            kwargs["parse_mode"] = parse_mode

        result = _send("sendMessage", **kwargs)

        if not result.get("ok"):
            # Retry as plain text if formatting caused the failure
            _send(
                "sendMessage",
                chat_id=os.environ["TELEGRAM_CHAT_ID"],
                text=re.sub(r"[*_`\[\]()]", "", text),
                disable_web_page_preview=True,
            )
    except Exception as e:
        print(f"[Telegram] Failed to send message: {e}")


def send_daily_digest(jobs: list[dict]) -> None:
    if not jobs:
        send_message("No new jobs found today. Check back tomorrow!")
        return

    send_message(
        f"Good morning! Here are your top {len(jobs)} new jobs for today.\n\n"
        f"Reply with:\n"
        f"cover [#] — generate cover letter\n"
        f"skip [#] — dismiss\n"
        f"applied [#] — mark as applied"
    )

    for batch_start in range(0, len(jobs), BATCH_SIZE):
        batch = jobs[batch_start: batch_start + BATCH_SIZE]
        lines = []
        for i, job in enumerate(batch, batch_start + 1):
            score_pct = int(job.get("score", 0) * 100)
            title = _escape(job.get("role") or job.get("title", ""))
            company = _escape(job.get("company", ""))
            location = _escape(job.get("location", "See listing"))
            source = job.get("source", "")
            url = job.get("url", "")
            lines.append(
                f"*{i}. {title}*\n"
                f"   {company} | {location} | {source}\n"
                f"   Match: {score_pct}% | [View Job]({url})"
            )
        send_message("\n\n".join(lines))


def send_cover_letter(job: dict, text: str) -> None:
    company = _escape(job.get("company", ""))
    role = _escape(job.get("role") or job.get("title", ""))
    header = f"*Cover Letter — {company} | {role}*\n\n"
    footer = "\n\n_Saved to your applications/ folder._"
    max_body = 4096 - len(header) - len(footer)
    send_message(header + text[:max_body] + footer)


def register_webhook(vercel_url: str) -> dict:
    url = vercel_url.rstrip("/") + "/webhook"
    return _send("setWebhook", url=url)
