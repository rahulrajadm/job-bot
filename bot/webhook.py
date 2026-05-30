"""
Telegram webhook — handles incoming messages.

Commands:
  cover [#]   — generate cover letter
  skip [#]    — dismiss job
  applied [#] — mark as applied
  apply [#]   — preview application answers + queue for submission
  go [#]      — submit queued application via LinkedIn Easy Apply (LOCAL only)

Run locally: python bot/webhook.py
Vercel:      auto-served via api/webhook.py (go command unavailable there)
"""

import re
import os
import sys
import json
import traceback
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

_IS_VERCEL = bool(os.environ.get("VERCEL"))


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        from tracker.supabase_client import (
            update_status, update_cover_letter_path,
            get_active_jobs, store_application_data,
        )
        from generator.cover_letter import generate_cover_letter, save_cover_letter
        from bot.telegram_bot import send_message, send_cover_letter
        from applier.form_answerer import preview_application

        data = request.json or {}
        message = data.get("message", {})
        body = message.get("text", "").strip().lower()

        if not body:
            return "", 200

        print(f"[Webhook] Received: '{body}'")

        if body == "/chatid":
            chat_id = message.get("chat", {}).get("id", "unknown")
            send_message(f"Your chat ID is: `{chat_id}`")
            return "", 200

        # All number-based commands use the same active list (found + pending_approval)
        jobs = get_active_jobs(25)
        print(f"[Webhook] Loaded {len(jobs)} active jobs")

        match = re.match(r"(cover|skip|applied|apply|go)\s+(\d+)", body)
        if not match:
            send_message(
                "Commands:\n"
                "`cover [#]` — generate cover letter\n"
                "`apply [#]` — preview + queue LinkedIn Easy Apply\n"
                "`go [#]` — submit queued application *(run locally)*\n"
                "`skip [#]` — dismiss job\n"
                "`applied [#]` — mark as applied"
            )
            return "", 200

        action, num = match.group(1), int(match.group(2)) - 1
        if num < 0 or num >= len(jobs):
            send_message(f"Job #{num + 1} not found. Try a number between 1 and {len(jobs)}.")
            return "", 200

        job = jobs[num]
        print(f"[Webhook] Action={action} on: {job.get('company')} — {job.get('role')}")

        # ── cover ──────────────────────────────────────────────────────────────
        if action == "cover":
            send_message(f"Generating cover letter for *{_esc(job['company'])}*...")
            text = generate_cover_letter(job)
            path = save_cover_letter(job, text)
            update_cover_letter_path(job["url"], path)
            send_cover_letter(job, text)

        # ── skip ───────────────────────────────────────────────────────────────
        elif action == "skip":
            update_status(job["url"], "skipped")
            send_message(f"Skipped _{_esc(job['company'])} — {_esc(job['role'])}_.")

        # ── applied ────────────────────────────────────────────────────────────
        elif action == "applied":
            update_status(job["url"], "applied")
            send_message(f"Marked as applied: _{_esc(job['company'])} — {_esc(job['role'])}_. Good luck!")

        # ── apply — preview answers, queue for submission ──────────────────────
        elif action == "apply":
            source = job.get("source", "").lower()
            if "linkedin" not in source:
                send_message(
                    f"Job #{num + 1} is from *{_esc(job.get('source', 'unknown'))}*.\n"
                    f"Easy Apply automation only works for LinkedIn jobs right now."
                )
                return "", 200

            if job.get("status") == "pending_approval":
                send_message(
                    f"Job #{num + 1} is already queued.\n"
                    f"Reply `go {num + 1}` to submit or `skip {num + 1}` to cancel."
                )
                return "", 200

            send_message(f"Building application preview for *{_esc(job['company'])}*...")
            preview = preview_application(job)
            store_application_data(job["url"], preview)

            lines = [f"*Apply #{num + 1}: {_esc(job['company'])} — {_esc(job['role'])}*\n"]
            lines.append("Planned answers:")
            for k, v in preview.items():
                lines.append(f"  • {_esc(k)}: {_esc(str(v))}")
            lines.append(
                f"\nReply `go {num + 1}` to submit via LinkedIn Easy Apply.\n"
                f"Reply `skip {num + 1}` to cancel."
            )
            send_message("\n".join(lines))

        # ── go — submit via Playwright (LOCAL only) ────────────────────────────
        elif action == "go":
            if _IS_VERCEL:
                send_message(
                    "The `go` command runs LinkedIn Easy Apply via your local machine.\n"
                    "Run `python bot/webhook.py` locally and try again."
                )
                return "", 200

            if job.get("status") != "pending_approval":
                send_message(
                    f"Job #{num + 1} hasn't been queued yet.\n"
                    f"Reply `apply {num + 1}` first to preview and queue it."
                )
                return "", 200

            from bot.telegram_bot import send_message as tg_send

            def on_status(msg: str) -> None:
                tg_send(f"_{_esc(msg)}_")

            company = job.get("company", "")
            role = job.get("role") or job.get("title", "")
            send_message(
                f"Starting LinkedIn Easy Apply for *{_esc(company)} — {_esc(role)}*.\n"
                f"A browser window will open on your machine."
            )

            def run_and_report():
                from applier.linkedin_applier import apply_to_job
                result = apply_to_job(job, on_status=on_status)
                if result["success"]:
                    update_status(job["url"], "applied")
                    tg_send(
                        f"*Applied!* {_esc(company)} — {_esc(role)}\n"
                        f"Status updated to applied in Supabase. Good luck!"
                    )
                else:
                    tg_send(
                        f"*Application failed* for {_esc(company)}.\n"
                        f"Error: {_esc(result.get('error', 'Unknown error'))}\n"
                        f"You can apply manually at the link in your digest."
                    )

            threading.Thread(target=run_and_report, daemon=True).start()

    except Exception as e:
        print(f"[Webhook] ERROR: {e}")
        traceback.print_exc()
        try:
            import requests as _req, os as _os
            token = _os.environ.get("TELEGRAM_BOT_TOKEN", "")
            chat_id = _os.environ.get("TELEGRAM_CHAT_ID", "")
            if token and chat_id:
                _req.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": f"[Bot error] {e}"},
                    timeout=5,
                )
        except Exception:
            pass

    return "", 200


def _esc(text: str) -> str:
    if not text:
        return ""
    import re as _re
    return _re.sub(r"([*_`\[\]])", r"\\\1", str(text))


if __name__ == "__main__":
    app.run(port=5001, debug=True)
