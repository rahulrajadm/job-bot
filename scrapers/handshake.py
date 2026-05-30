"""
Handshake scraper — requires Playwright and your Handshake login credentials.

Install Playwright: pip install playwright && playwright install chromium

Set in .env:
  HANDSHAKE_EMAIL=your@email.com
  HANDSHAKE_PASSWORD=yourpassword
"""

import os
import time
from datetime import date
from dotenv import load_dotenv

load_dotenv()

SEARCH_TERMS = [
    "data science",
    "machine learning",
    "biomedical engineer",
    "data analyst",
    "research scientist",
    "AI engineer",
]


def scrape_handshake(max_results: int = 25) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[Handshake] Playwright not installed. Run: pip install playwright && playwright install chromium")
        return []

    email = os.environ.get("HANDSHAKE_EMAIL")
    password = os.environ.get("HANDSHAKE_PASSWORD")
    if not email or not password:
        print("[Handshake] HANDSHAKE_EMAIL and HANDSHAKE_PASSWORD not set in .env — skipping.")
        return []

    jobs = []
    seen_urls: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # Log in
            page.goto("https://app.joinhandshake.com/login")
            page.fill('input[type="email"]', email)
            page.click('button[type="submit"]')
            page.fill('input[type="password"]', password)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=15000)

            for term in SEARCH_TERMS:
                if len(jobs) >= max_results:
                    break
                try:
                    page.goto(
                        f"https://app.joinhandshake.com/jobs?query={term.replace(' ', '+')}"
                        f"&job_type=full_time%2Cinternship&sort_direction=desc&sort_column=created_at",
                        timeout=15000,
                    )
                    page.wait_for_load_state("networkidle", timeout=10000)
                    time.sleep(2)

                    cards = page.query_selector_all("[data-testid='job-card'], .job-card, article")
                    for card in cards:
                        if len(jobs) >= max_results:
                            break
                        try:
                            title = card.query_selector("h3, h2, .job-title")
                            company = card.query_selector(".employer-name, .company-name")
                            location = card.query_selector(".location")
                            link = card.query_selector("a")

                            title_text = title.inner_text().strip() if title else ""
                            company_text = company.inner_text().strip() if company else "Unknown"
                            location_text = location.inner_text().strip() if location else "Unknown"
                            href = link.get_attribute("href") if link else ""
                            url = f"https://app.joinhandshake.com{href}" if href and href.startswith("/") else href

                            if not url or url in seen_urls:
                                continue
                            seen_urls.add(url)
                            jobs.append({
                                "title": title_text,
                                "company": company_text,
                                "location": location_text,
                                "url": url,
                                "snippet": "",
                                "source": "Handshake",
                                "query": term,
                                "date_found": str(date.today()),
                            })
                        except Exception:
                            continue

                except Exception as e:
                    print(f"[Handshake] Error on '{term}': {e}")
                    continue

        except Exception as e:
            print(f"[Handshake] Login failed: {e}")
        finally:
            browser.close()

    return jobs
