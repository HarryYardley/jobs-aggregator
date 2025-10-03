# scripts/adapters/github_markdown.py
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone

GITHUB_REPOS = [
    # Intern lists
    "https://github.com/SimplifyJobs/Summer2026-Internships",
    "https://github.com/vanshb03/Summer2026-Internships",
    "https://github.com/SimplifyJobs/Summer2026-Internships/blob/dev/README-Off-Season.md",
    # New grad lists
    "https://github.com/SimplifyJobs/New-Grad-Positions",
    "https://github.com/vanshb03/New-Grad-2026",
]

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

def role_type_from_repo(url: str) -> str:
    lowered = url.lower()
    if "intern" in lowered:
        return "Intern"
    if "new-grad" in lowered:
        return "New Grad"
    return "Other"

def _normalize_header(h: str) -> str:
    return (h or "").strip().lower()

def _parse_date_cell(raw: str) -> str | None:
    """
    Accepts:
      - 'YYYY-MM-DD'  -> keep as is
      - 'Oct 01'      -> infer year; convert to YYYY-MM-DD
    Returns ISO 'YYYY-MM-DD' or None if unparseable.
    """
    if not raw:
        return None
    raw = raw.strip()
    # Try direct ISO first
    try:
        dt = datetime.strptime(raw.split("T")[0], "%Y-%m-%d")
        return dt.date().isoformat()
    except Exception:
        pass

    # Try 'Mon DD' (e.g., 'Oct 01')
    try:
        today = datetime.now(timezone.utc).date()
        # Assume current year; if it lands in the future (by >1 day), roll back a year.
        guessed = datetime.strptime(raw, "%b %d").date().replace(year=today.year)
        if guessed > today + timedelta(days=1):
            guessed = guessed.replace(year=today.year - 1)
        return guessed.isoformat()
    except Exception:
        return None

def _parse_age_cell(raw: str) -> str | None:
    """
    Accepts:
      - '0d', '3d', '14d'  -> today - N days, as ISO 'YYYY-MM-DD'
    """
    if not raw:
        return None
    raw = raw.strip().lower()
    # Common formats: '0d', '3d'
    try:
        if raw.endswith('d'):
            days = int(''.join(ch for ch in raw if ch.isdigit()))
            today = datetime.now(timezone.utc).date()
            dt = today - timedelta(days=days)
            return dt.isoformat()
    except Exception:
        pass
    return None

def fetch_tables_from_github():
    """
    Scrape markdown tables as rendered on GitHub:
      - company, title, location, link (<a href>)
      - posted/date if the table includes either a Date column (e.g., 'Oct 01'/'2025-10-03')
        or an Age column (e.g., '0d', '3d').
    If no date is present, we leave date_posted=None (we do NOT default to 'today').
    """
    rows = []

    for repo_url in GITHUB_REPOS:
        role_type = role_type_from_repo(repo_url)
        resp = requests.get(repo_url, headers=DEFAULT_HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for table in soup.select("table"):
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
            idx_title  = find_col("role", "position", "title")
            idx_loc    = find_col("location")
            idx_link   = find_col("apply", "link", "url")
            idx_date   = find_col("date", "posted")  # handles 'Date' column
            idx_age    = find_col("age")             # handles 'Age' column like '0d'

            if idx_company is None or idx_link is None:
                continue

            tbody = table.find("tbody") or table
            for tr in tbody.find_all("tr"):
                tds = tr.find_all(["td", "th"])
                if not tds:
                    continue

                def safe_text(i):
                    if i is None or i >= len(tds):
                        return ""
                    return tds[i].get_text(strip=True)

                # Link:
                link_url = ""
                if idx_link is not None and idx_link < len(tds):
                    a = tds[idx_link].find("a", href=True)
                    if a and a["href"]:
                        link_url = a["href"].strip()
                if not link_url or not link_url.startswith("http"):
                    continue

                company = safe_text(idx_company)
                job_title = safe_text(idx_title) if idx_title is not None else ""
                location = safe_text(idx_loc) if idx_loc is not None else ""

                date_posted = None
                # Prefer explicit Date column over Age.
                if idx_date is not None and idx_date < len(tds):
                    raw = safe_text(idx_date)
                    date_posted = _parse_date_cell(raw)

                if date_posted is None and idx_age is not None and idx_age < len(tds):
                    raw_age = safe_text(idx_age)
                    date_posted = _parse_age_cell(raw_age)

                rows.append({
                    "source": f"github:{urlparse(repo_url).path.strip('/')}",
                    "role_type": role_type,
                    "job_title": job_title,
                    "company": company,
                    "location": location,
                    "url": link_url,
                    "date_posted": date_posted,  # ISO YYYY-MM-DD or None
                    "date_seen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "notes": "",
                })

    return rows
