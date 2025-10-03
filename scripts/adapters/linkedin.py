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
            locat
