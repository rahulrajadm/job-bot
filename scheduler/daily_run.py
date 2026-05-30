"""
Orchestrator — scrapes, scores, deduplicates, saves to Supabase, sends WhatsApp digest.
Runs daily at 10:00 AM via APScheduler.

To start the scheduler: python scheduler/daily_run.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

load_dotenv()


def run_daily_job():
    print("[Job Bot] Starting daily run...")

    from scrapers.jobspy_scraper import scrape_all
    from matcher.scorer import score_and_rank
    from tracker.supabase_client import get_seen_urls, insert_jobs, insert_filtered_out, get_pending_jobs
    from bot.telegram_bot import send_daily_digest

    print("[1/5] Scraping Indeed, LinkedIn, ZipRecruiter...")
    raw_passed, raw_rejected = scrape_all(max_results=75)
    print(f"      {len(raw_passed)} passed filters, {len(raw_rejected)} rejected by filters")

    print("[2/5] Deduplicating against Supabase...")
    seen = get_seen_urls()
    new_passed = [j for j in raw_passed if j["url"] not in seen]
    new_rejected = [j for j in raw_rejected if j["url"] not in seen]
    print(f"      {len(new_passed)} new jobs to score, {len(new_rejected)} new rejected jobs")

    print("[3/5] Saving filter-rejected jobs to Supabase...")
    insert_filtered_out(new_rejected)

    if not new_passed:
        from bot.telegram_bot import send_message
        send_message("No new jobs found today. Check back tomorrow!")
        print("[Job Bot] Done — nothing new today.")
        return

    print("[4/5] Scoring and ranking...")
    ranked = score_and_rank(new_passed)
    top = ranked[:25]
    low_score = [dict(j, status="low_score") for j in ranked[25:]]
    insert_filtered_out(low_score)
    print(f"      Top {len(top)} jobs selected, {len(low_score)} saved as low_score")

    print("[5/5] Saving to Supabase and sending digest...")
    inserted = insert_jobs(top)
    print(f"      Inserted {inserted} jobs into Supabase")
    send_daily_digest(top)

    print(f"[Job Bot] Done — sent {len(top)} jobs to Telegram.")


def send_backlog():
    """Send all previously saved but undelivered 'found' jobs to Telegram."""
    from tracker.supabase_client import get_pending_jobs
    from bot.telegram_bot import send_daily_digest, send_message

    print("[Job Bot] Fetching backlog of undelivered jobs...")
    jobs = get_pending_jobs(limit=25)
    if not jobs:
        print("[Job Bot] No backlog jobs found.")
        send_message("No backlog jobs to send.")
        return
    print(f"[Job Bot] Sending {len(jobs)} backlog jobs to Telegram...")
    send_daily_digest(jobs)
    print("[Job Bot] Backlog sent.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="Run immediately instead of waiting for 10am")
    parser.add_argument("--backlog", action="store_true", help="Send all saved but undelivered jobs")
    args = parser.parse_args()

    if args.backlog:
        send_backlog()
    elif args.now:
        run_daily_job()
    else:
        scheduler = BlockingScheduler()
        scheduler.add_job(run_daily_job, "cron", hour=10, minute=0)
        print("[Job Bot] Scheduler started — will run daily at 10:00 AM.")
        print("          Run with --now to trigger immediately.")
        scheduler.start()
