import re
import os
import sys
import traceback

from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Add project root to path for imports
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@app.route("/webhook", methods=["POST"])
@app.route("/api/webhook", methods=["POST"])
def webhook():
    try:
        from tracker.supabase_client import update_status, update_cover_letter_path, get_pending_jobs
        from generator.cover_letter import generate_cover_letter, save_cover_letter
        from bot.whatsapp_bot import send_message, send_cover_letter

        body = request.form.get("Body", "").strip().lower()
        print(f"[Webhook] Received: '{body}'")

        jobs = get_pending_jobs(25)
        print(f"[Webhook] Loaded {len(jobs)} pending jobs")

        match = re.match(r"(cover|skip|applied)\s+(\d+)", body)
        if not match:
            send_message("Commands: *cover [#]*, *skip [#]*, *applied [#]*")
            return "", 204

        action, num = match.group(1), int(match.group(2)) - 1
        if num < 0 or num >= len(jobs):
            send_message(f"Job #{num + 1} not found. Try a number between 1 and {len(jobs)}.")
            return "", 204

        job = jobs[num]
        print(f"[Webhook] Action={action} on: {job.get('company')} — {job.get('role')}")

        if action == "cover":
            text = generate_cover_letter(job)
            save_cover_letter(job, text)
            update_cover_letter_path(job["url"], "vercel")
            send_message(f"Generating cover letter for {job['company']}...")
            send_cover_letter(job, text)

        elif action == "skip":
            update_status(job["url"], "skipped")
            send_message(f"Skipped {job['company']} — {job['role']}.")

        elif action == "applied":
            update_status(job["url"], "applied")
            send_message(f"Marked as applied: {job['company']} — {job['role']}. Good luck!")

    except Exception as e:
        print(f"[Webhook] ERROR: {e}")
        traceback.print_exc()

    return "", 204


if __name__ == "__main__":
    app.run(port=5001, debug=True)
