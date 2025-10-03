# scripts/adapters/github_markdown.py
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Iterable

import requests
from bs4 import BeautifulSoup
from markdown_it import MarkdownIt

# ---------------------------
# Sources to pull from (RAW)
# ---------------------------

@dataclass
class Source:
    owner: str
    repo: str
    paths: List[Tuple[str, str]]  # list of (path, branch)
    role_type: str                # "Intern" | "New Grad"

SOURCES: List[Source] = [
    # Intern lists
    Source("SimplifyJobs", "Summer2026-Internships",
           paths=[("README.md", "main"), ("README-Off-Season.md", "dev")],
           role_type="Intern"),
    Source("vanshb03", "Summer2026-Internships",
           paths=[("README.md", "main")],
           role_type="Intern"),

    # New grad lists
    Source("SimplifyJobs", "New-Grad-Positions",
           paths=[("README.md", "main")],
           role_type="New Grad"),
    Source("vanshb03", "New-Grad-2026",
           paths=[("README.md", "main")],
           role_type="New Grad"),
]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

def _raw_url(owner: str, repo: str, branch: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"

def _http_get(url: str, *, retries: int = 4, backoff: float = 1.5) -> requests.Response:
    """
    Simple GET with retry/backoff on 429/5xx.
    """
    for attempt in range(retries):
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if resp.status_code < 400:
            return resp
        if resp.status_code in (429, 500, 502, 503, 504):
            sleep = backoff ** attempt
            time.sleep(sleep)
            continue
        resp.raise_for_status()
    # final raise if still bad
    resp.raise_for_status()
    return resp  # unreachable

_md = MarkdownIt()

def _md_to_html(md_text: str) -> str:
    return _md.render(md_text)

def _normalize_header(h: str) -> str:
    return (h or "").strip().lower()

def _parse_date_cell(raw: str) -> str | None:
    """
    Accepts:
      - 'YYYY-MM-DD'
      - 'Oct 01'  (year inferred; if in the future -> previous year)
    Returns ISO 'YYYY-MM-DD' or None.
    """
    if not raw:
        return None
    raw = raw.strip()
    # ISO
    try:
        dt = datetime.strptime(raw.split("T")[0], "%Y-%m-%d")
        return dt.date().isoformat()
    except Exception:
        pass
    # 'Mon DD'
    try:
        today = datetime.now(timezone.utc).date()
        guessed = datetime.strptime(raw, "%b %d").date().replace(year=today.year)
        if guessed > today + timedelta(days=1):
            guessed = guessed.replace(year=today.year - 1)
        return guessed.isoformat()
    except Exception:
        return None

def _parse_age_cell(raw: str) -> str | None:
    """
    Accepts '0d', '3d', etc. -> today - N days (ISO).
    """
    if not raw:
        return None
    raw = raw.strip().lower()
    try:
        if raw.endswith("d"):
            n = int("".join(ch for ch in raw if ch.isdigit()))
            today = datetime.now(timezone.utc).date()
            dt = today - timedelta(days=n)
            return dt.isoformat()
    except Exception:
        pass
    return None

def _iter_tables_from_html(html: str) -> Iterable[BeautifulSoup]:
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.select("table"):
        yield table

def _extract_rows_from_table(table: BeautifulSoup, role_type: str, source_label: str):
    """
    Extract rows from a single HTML table produced by markdown-it
    (so <a href> links are preserved).
    """
    # headers
    thead = table.find("thead")
    if not thead:
        first_tr = table.find("tr")
        header_cells = [c.get_text(strip=True) for c in (first_tr.find_all(["th", "td"]) if first_tr else [])]
    else:
        header_cells = [c.get_text(strip=True) for c in thead.find_all("th")]
    headers = [_normalize_header(h) for h in header_cells]

    def find_col(*candidates):
        for cand in candidates:
            for idx, h in enumerate(headers):
                if cand in h:
                    return idx
        return None

    idx_company = find_col("company")
    idx_title   = find_col("role", "position", "title")
    idx_loc     = find_col("location")
    idx_link    = find_col("apply", "link", "url")
    idx_date    = find_col("date", "posted")
    idx_age     = find_col("age")

    # Need at least company + link
    if idx_company is None or idx_link is None:
        return []

    tbody = table.find("tbody") or table
    out = []

    for tr in tbody.find_all("tr"):
        tds = tr.find_all(["td", "th"])
        if not tds:
            continue

        def txt(i: int | None) -> str:
            if i is None or i >= len(tds):
                return ""
            return tds[i].get_text(strip=True)

        # link from Link/Apply cell
        link_url = ""
        if idx_link is not None and idx_link < len(tds):
            a = tds[idx_link].find("a", href=True)
            if a and a.get("href"):
                link_url = a["href"].strip()
        if not link_url or not link_url.startswith("http"):
            continue

        company = txt(idx_company)
        job_title = txt(idx_title) if idx_title is not None else ""
        location = txt(idx_loc) if idx_loc is not None else ""

        date_posted = None
        if idx_date is not None and idx_date < len(tds):
            date_posted = _parse_date_cell(txt(idx_date))
        if date_posted is None and idx_age is not None and idx_age < len(tds):
            date_posted = _parse_age_cell(txt(idx_age))

        out.append({
            "source": source_label,
            "role_type": role_type,
            "job_title": job_title,
            "company": company,
            "location": location,
            "url": link_url,
            "date_posted": date_posted,  # ISO or None
            "date_seen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "notes": "github raw markdown",
        })
    return out

def fetch_tables_from_github():
    """
    Fetch RAW Markdown from GitHub, convert to HTML locally, then parse tables.
    This avoids 429 from the rendered GitHub HTML pages.
    """
    rows = []

    for src in SOURCES:
        for path, branch in src.paths:
            url = _raw_url(src.owner, src.repo, branch, path)
            try:
                resp = _http_get(url)  # with retry/backoff
            except requests.HTTPError as e:
                # Skip missing path/branch
                continue

            md_text = resp.text
            html = _md_to_html(md_text)

            for table in _iter_tables_from_html(html):
                rows.extend(_extract_rows_from_table(
                    table,
                    role_type=src.role_type,
                    source_label=f"github:{src.owner}/{src.repo}@{branch}/{path}"
                ))

    return rows
