# scripts/adapters/linkedin.py
from __future__ import annotations

import time
import random
from typing import List, Dict, Optional
from urllib.parse import quote_plus
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# -----------------------------
# LinkedIn "guest" search notes
# -----------------------------
# We scrape the public "seeMoreJobPostings" endpoint with query params.
# This can break at any time if LinkedIn changes the markup or rate-limits.
# Use polite throttling and small page sizes. Consider switching to tracking
# Greenhouse/Lever boards if you run into reliability issues.

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

SEARCH_BASE = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)

def _search_url(keywords: str, location: str, start: int) -> str:
    """
    f_TPR=r5184000 => last 60 days window (60 * 24 * 60 * 60 = 5,184,000 seconds)
    You can widen or narrow this if you want.
    """
    return (
        f"{SEARCH_BASE}?keywords={quote_plus(keywords)}"
        f"&location={quote_plus(location)}"
        f"&f_TPR=r5184000&start={start}"
    )

def _parse_iso_date_from_time_tag(tag) -> Optional[str]:
    """
    LinkedIn often sets <time datetime="2025-10-01">. Return ISO 'YYYY-MM-DD' if present.
    """
    if not tag:
        return None
    dt = tag.get("datetime")
    if not dt:
        return None
    # Normalize to YYYY-MM-DD
    try:
        if "T" in dt:
            dt = dt.split("T")[0]
        datetime.strptime(dt, "%Y-%m-%d")
        return dt
    except Exception:
        return None

def _extract_jobs_from_html(html: str, role_type: str) -> List[Dict]:
    """
    Parse one "page" of results and return normalized job rows.
    """
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("li")  # each job is usually one <li>
    rows: List[Dict] = []

    for card in cards:
        try:
            title_el = (
                card.select_one("h3.base-search-card__title")
                or card.select_one("h3")
            )
            company_el = (
                card.select_one("h4.base-search-card__subtitle")
                or card.select_one("a.hidden-nested-link")  # sometimes company is a link
                or card.select_one("h4")
            )
            location_el = (
                card.select_one("span.job-search-card__location")
                or card.select_one("span")
            )
            link_el = (
                card.select_one("a.base-card__full-link")
                or card.select_one("a.result-card__full-card-link")
                or card.select_one("a")
            )
            time_el = (
                card.select_one("time.job-search-card__listdate")
                or card.select_one("time.job-search-card__listed-date")
                or card.select_one("time")
            )

            # Minimal required fields
            if not (title_el and company_el and location_el and link_el):
                continue

            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True)
            location = location_el.get_text(strip=True)
            url = link_el.get("href", "").strip()
            date_posted = _parse_iso_date_from_time_tag(time_el)

            # Normalize into your schema
            rows.append({
                "source": "linkedin",
                "role_type": role_type,                   # 'Intern' or 'New Grad'
                "job_title": title,
                "company": company,
                "location": location,
                "url": url,
                "date_posted": date_posted,               # 'YYYY-MM-DD' or None
                "date_seen": datetime.utcnow().isoformat(timespec="seconds"),
                "notes": "LinkedIn guest search",
            })
        except Exception:
            # Swallow single-card parse errors to keep scraping robust
            continue

    return rows

def fetch_linkedin_jobs(
    job_titles: List[str],
    locations: List[str],
    role_type: str,
    *,
    max_pages_per_query: int = 4,
    page_size_hint: int = 25,
    request_headers: Optional[Dict[str, str]] = None,
    sleep_between_requests: tuple[float, float] = (1.0, 2.0),
) -> List[Dict]:
    """
    Public adapter function used by the pipeline.

    Args:
        job_titles: e.g., ["Mechanical Engineering Intern", "Software Engineering Intern"]
        locations: e.g., ["San Francisco, CA", "New York, NY"]
        role_type: "Intern" or "New Grad"
        max_pages_per_query: number of "start" pages (25-ish results per page)
        page_size_hint: LinkedIn typically returns ~25 items per page
        request_headers: override default headers if desired
        sleep_between_requests: (min,max) seconds randomized per request

    Returns:
        List of normalized rows (see schema above).
    """
    headers = dict(DEFAULT_HEADERS)
    if request_headers:
        headers.update(request_headers)

    all_rows: List[Dict] = []
    seen_urls: set[str] = set()

    for title in job_titles:
        for loc in locations:
            start = 0
            for page in range(max_pages_per_query):
                url = _search_url(title, loc, start)
                try:
                    resp = requests.get(url, headers=headers, timeout=30)
                    if resp.status_code == 429:
                        # Rate-limited: back off a little longer
                        time.sleep(10.0)
                        continue
                    resp.raise_for_status()
                except Exception:
                    # network / status error => move on to next query
                    break

                rows = _extract_jobs_from_html(resp.text, role_type=role_type)

                # Dedup by URL immediately to reduce memory
                unique_rows = []
                for r in rows:
                    u = r.get("url", "").strip()
                    if not u or u in seen_urls:
                        continue
                    seen_urls.add(u)
                    unique_rows.append(r)

                if not unique_rows:
                    # Probably no more results for this query
                    break

                all_rows.extend(unique_rows)

                # Prepare next page
                start += page_size_hint

                # Polite random sleep
                time.sleep(random.uniform(*sleep_between_requests))

    return all_rows

if __name__ == "__main__":
    # Simple manual smoke test (prints counts only).
    # You can run:  python scripts/adapters/linkedin.py
    INTERN_TITLES = [
        "Software Engineering Intern",
        "Data Science Intern",
    ]
    NEWGRAD_TITLES = [
        "Software Engineer",
        "Data Scientist",
        "Machine Learning Engineer",
    ]
    LOCS = ["San Francisco, CA", "New York, NY", "Seattle, WA"]

    print("Testing intern fetch...")
    intern_rows = fetch_linkedin_jobs(INTERN_TITLES, LOCS, role_type="Intern", max_pages_per_query=1)
    print(f"Intern rows: {len(intern_rows)}")

    print("Testing new grad fetch...")
    ng_rows = fetch_linkedin_jobs(NEWGRAD_TITLES, LOCS, role_type="New Grad", max_pages_per_query=1)
    print(f"New grad rows: {len(ng_rows)}")
