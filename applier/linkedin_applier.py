"""
LinkedIn Easy Apply automation via Playwright.

Flow:
  1. Log in to LinkedIn with stored credentials.
  2. Navigate to the job URL.
  3. Click "Easy Apply", step through the modal form.
  4. Answer each question via form_answerer (qa_profile + Claude fallback).
  5. Upload resume PDF if present.
  6. Submit on the final step.

Runs locally only — Playwright cannot run on Vercel/serverless.
Browser runs VISIBLE (headless=False) so you can intervene if needed.
"""

import os
import time
import threading
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

load_dotenv()

RESUME_PDF = Path(__file__).parent.parent / "data" / "resume.pdf"


# ── Public entry points ───────────────────────────────────────────────────────

def apply_to_job(
    job: dict,
    on_status: Callable[[str], None] | None = None,
) -> dict:
    """
    Attempt LinkedIn Easy Apply for *job*.

    Returns:
        {"success": bool, "answers": dict, "error": str | None}
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    def log(msg: str) -> None:
        print(f"[LinkedIn] {msg}")
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass

    answers: dict = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,  # visible — user can watch and intervene
            slow_mo=50,      # slight delay makes actions more human-like
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()

        try:
            # 1. Login
            log("Logging in to LinkedIn...")
            err = _login(page)
            if err:
                return {"success": False, "answers": {}, "error": err}

            # 2. Navigate to job
            url = job.get("url", "")
            log(f"Opening job: {url}")
            page.goto(url, timeout=30_000)
            page.wait_for_load_state("domcontentloaded", timeout=15_000)
            time.sleep(2)

            # 3. Click Easy Apply
            try:
                btn = page.wait_for_selector(
                    'button.jobs-apply-button, '
                    'button[data-job-id], '
                    'button:has-text("Easy Apply")',
                    timeout=10_000,
                )
                btn.click()
                time.sleep(1.5)
            except PWTimeout:
                return {
                    "success": False,
                    "answers": {},
                    "error": "No Easy Apply button — this job may redirect to an external ATS.",
                }

            log("Modal open. Filling form...")

            # 4. Step through form pages
            for step in range(12):
                page.wait_for_load_state("domcontentloaded")
                time.sleep(1)

                # Resume upload
                _handle_file_upload(page, log)

                # Fill visible questions
                step_answers = _fill_current_step(page, job)
                answers.update(step_answers)
                if step_answers:
                    log(f"Step {step + 1}: filled {len(step_answers)} field(s).")

                # Navigation
                nav = _next_button(page)
                if nav == "submit":
                    _click(page, 'button[aria-label="Submit application"], button:has-text("Submit application")')
                    time.sleep(2)
                    log("Application submitted!")
                    return {"success": True, "answers": answers, "error": None}
                elif nav == "review":
                    _click(page, 'button:has-text("Review"), button[aria-label*="Review"]')
                    log("Reviewing...")
                elif nav == "next":
                    _click(page, 'button:has-text("Continue to next step"), button:has-text("Next")')
                    log(f"Moving to step {step + 2}...")
                else:
                    log("No navigation button found — stopping.")
                    break

            return {"success": False, "answers": answers, "error": "Reached max steps without submitting."}

        except Exception as exc:
            import traceback
            log(f"Error: {exc}")
            traceback.print_exc()
            return {"success": False, "answers": answers, "error": str(exc)}

        finally:
            time.sleep(1)
            browser.close()


def apply_in_background(
    job: dict,
    on_status: Callable[[str], None] | None = None,
) -> threading.Thread:
    """Run apply_to_job in a daemon thread and return it immediately."""
    t = threading.Thread(target=lambda: apply_to_job(job, on_status), daemon=True)
    t.start()
    return t


# ── Internal helpers ──────────────────────────────────────────────────────────

def _login(page) -> str | None:
    """Log in to LinkedIn. Returns error string or None on success."""
    from playwright.sync_api import TimeoutError as PWTimeout

    email = os.environ.get("LINKEDIN_EMAIL", "")
    password = os.environ.get("LINKEDIN_PASSWORD", "")
    if not email or not password:
        return "LINKEDIN_EMAIL / LINKEDIN_PASSWORD not set in .env"

    page.goto("https://www.linkedin.com/login", timeout=30_000)
    page.fill('input[name="session_key"]', email)
    page.fill('input[name="session_password"]', password)
    page.click('button[type="submit"]')

    try:
        # Wait for redirect away from /login
        page.wait_for_function(
            "() => !window.location.href.includes('/login')",
            timeout=20_000,
        )
    except PWTimeout:
        return "Login failed — check credentials, 2FA, or CAPTCHA in the browser window."

    if "checkpoint" in page.url or "challenge" in page.url:
        return "LinkedIn security check triggered — complete it in the browser window then re-run."

    return None


def _handle_file_upload(page, log: Callable) -> None:
    """Upload resume PDF if a file input is visible."""
    try:
        f = page.query_selector("input[type='file']")
        if f and RESUME_PDF.exists():
            f.set_input_files(str(RESUME_PDF))
            log("Uploaded resume.pdf.")
        elif f and not RESUME_PDF.exists():
            log("WARNING: file upload field found but data/resume.pdf missing — skipping upload.")
    except Exception:
        pass


def _fill_current_step(page, job: dict) -> dict:
    """Find and fill all form fields on the current modal page."""
    from applier.form_answerer import answer_question

    filled = {}

    # Collect all labeled form elements
    containers = page.query_selector_all(
        ".fb-form-element, "
        ".jobs-easy-apply-form-element, "
        ".jobs-easy-apply-form-section__field-set"
    )

    for container in containers:
        label_el = container.query_selector(
            "label.fb-form-element__label, "
            "label[for], "
            ".fb-form-element__label"
        )
        if not label_el:
            continue

        label_text = label_el.inner_text().strip()
        if not label_text:
            continue

        # --- Text / email / tel inputs ---
        inp = container.query_selector(
            "input[type='text'], input[type='email'], input[type='tel'], input[type='number']"
        )
        if inp:
            # Skip pre-filled required fields that look correct
            current_val = inp.input_value()
            if current_val and len(current_val) > 2:
                filled[label_text] = f"[pre-filled: {current_val}]"
                continue
            answer = answer_question(label_text, job)
            if answer:
                inp.click()
                inp.fill(answer)
                filled[label_text] = answer
            continue

        # --- Textarea ---
        ta = container.query_selector("textarea")
        if ta:
            answer = answer_question(label_text, job)
            if answer:
                ta.click()
                ta.fill(answer)
                filled[label_text] = answer
            continue

        # --- Select dropdown ---
        sel = container.query_selector("select")
        if sel:
            answer = answer_question(label_text, job)
            opts = sel.query_selector_all("option")
            opt_texts = [o.inner_text().strip() for o in opts]
            best = _match_option(answer, opt_texts)
            if best:
                sel.select_option(label=best)
                filled[label_text] = best
            continue

        # --- Radio buttons (Yes/No) ---
        radios = container.query_selector_all("input[type='radio']")
        if radios:
            answer = answer_question(label_text, job)
            _select_radio(radios, answer)
            filled[label_text] = answer
            continue

    return filled


def _match_option(answer: str, options: list[str]) -> str | None:
    """Find the closest dropdown option to the given answer string."""
    a = answer.lower()
    # Exact match
    for opt in options:
        if opt.lower() == a:
            return opt
    # Substring match
    for opt in options:
        if a in opt.lower() or opt.lower() in a:
            return opt
    # First word match
    first_word = a.split()[0] if a else ""
    for opt in options:
        if first_word and first_word in opt.lower():
            return opt
    return None


def _select_radio(radios, answer: str) -> None:
    """Check the radio button whose value/label best matches *answer*."""
    answer_lower = answer.lower()
    for r in radios:
        val = (r.get_attribute("value") or "").lower()
        if val and (val in answer_lower or answer_lower in val):
            r.check()
            return
    # If answer looks like "yes" / "true", check first radio; "no" → second
    if answer_lower in ("yes", "true", "1", "agree"):
        radios[0].check()
    elif answer_lower in ("no", "false", "0") and len(radios) > 1:
        radios[1].check()


def _next_button(page) -> str | None:
    """Return 'submit', 'review', 'next', or None based on visible buttons."""
    if page.query_selector('button[aria-label="Submit application"], button:has-text("Submit application")'):
        return "submit"
    if page.query_selector('button:has-text("Review"), button[aria-label*="Review"]'):
        return "review"
    if page.query_selector('button:has-text("Continue to next step"), button:has-text("Next")'):
        return "next"
    return None


def _click(page, selector: str) -> None:
    try:
        page.click(selector, timeout=5_000)
        time.sleep(1)
    except Exception:
        pass
