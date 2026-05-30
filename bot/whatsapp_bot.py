import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

_twilio: Client | None = None


def get_twilio() -> Client:
    global _twilio
    if _twilio is None:
        _twilio = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    return _twilio


def send_message(body: str) -> None:
    try:
        get_twilio().messages.create(
            from_=os.environ["TWILIO_WHATSAPP_FROM"],
            to=os.environ["TWILIO_WHATSAPP_TO"],
            body=body,
        )
    except Exception as e:
        print(f"[WhatsApp] Failed to send message: {e}")


BATCH_SIZE = 5


def send_daily_digest(jobs: list[dict]) -> None:
    if not jobs:
        send_message("No new jobs found today. Check back tomorrow!")
        return

    send_message(
        f"Good morning! Here are your top {len(jobs)} new jobs for today.\n"
        f"Reply *cover [#]*, *skip [#]*, or *applied [#]* for any job."
    )

    for batch_start in range(0, len(jobs), BATCH_SIZE):
        batch = jobs[batch_start: batch_start + BATCH_SIZE]
        lines = []
        for i, job in enumerate(batch, batch_start + 1):
            score_pct = int(job.get("score", 0) * 100)
            source = job.get("source", "")
            lines.append(
                f"*{i}. {job.get('role') or job.get('title')}*\n"
                f"   {job.get('company')} | {job.get('location', 'See listing')} | {source}\n"
                f"   Match: {score_pct}% | {job.get('url')}"
            )
        send_message("\n\n".join(lines))


def send_cover_letter(job: dict, cover_letter_text: str) -> None:
    header = f"Cover Letter — {job.get('company')} | {job.get('role') or job.get('title')}\n\n"
    footer = "\n\n_Also saved to your applications/ folder._"
    max_body = 4096 - len(header) - len(footer)
    body = cover_letter_text[:max_body]
    send_message(header + body + footer)
