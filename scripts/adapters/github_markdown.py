# scripts/adapters/github_markdown.py
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime

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
    h = (h or "").strip().lower()
    return h

def fetch_tables_from_github():
    """
    Scrape markdown tables (as rendered on GitHub) and extract:
    - company, job title, location
    - link (real <a href>)
    - optional posted/date column if present
    """
    rows = []

    for repo_url in GITHUB_REPOS:
        role_type = role_type_from_repo(repo_url)
        resp = requests.get(repo_url, headers=DEFAULT_HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # GitHub renders README tables as <table> elements
        for table in soup.select("table"):
            # Build header map
            thead = table.find("thead")
            if not thead:
                # some tables omit <thead>, try first row as header
                first_tr = table.find("tr")
                header_cells = [c.get_text(strip=True) for c in (first_tr.find_all(["th", "td"]) if first_tr else [])]
            else:
                header_cells = [c.get_text(strip=True) for c in thead.find_all("th")]

            headers = [_normalize_header(h) for h in header_cells]

            # Identify best-guess columns
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
            idx_date   = find_col("date", "posted", "post")

            # If we don't at least have company + link columns, skip this table
            if idx_company is None or idx_link is None:
                continue

            # Iterate data rows
            tbody = table.find("tbody") or table
            for tr in tbody.find_all("tr"):
                tds = tr.find_all(["td", "th"])
                if not tds:
                    continue

                def safe_text(i):
                    if i is None or i >= len(tds):
                        return ""
                    return tds[i].get_text(strip=True)

                # Extract URL from the "link/apply" cell by finding <a href=...>
                link_url = ""
                if idx_link is not None and idx_link < len(tds):
                    link_cell = tds[idx_link]
                    a = link_cell.find("a", href=True)
                    if a and a["href"]:
                        link_url = a["href"].strip()
                # Basic sanity
                if not link_url or not link_url.startswith("http"):
                    continue

                company = safe_text(idx_company)
                job_title = safe_text(idx_title) if idx_title is not None else ""
                location = safe_text(idx_loc) if idx_loc is not None else ""

                date_posted = None
                if idx_date is not None and idx_date < len(tds):
                    raw = safe_text(idx_date)
                    # Try to normalize 'YYYY-MM-DD'; if not parseable, leave as None
                    # (your README builder will fall back to date_seen)
                    try:
                        # try iso-ish first
                        if len(raw) >= 8:
                            # very light normalization; adjust if your sources include other formats
                            dt = raw.split("T")[0].strip()
                            datetime.strptime(dt, "%Y-%m-%d")
                            date_posted = dt
                    except Exception:
                        date_posted = None

                rows.append({
                    "source": f"github:{urlparse(repo_url).path.strip('/')}",
                    "role_type": role_type,
                    "job_title": job_title,
                    "company": company,
                    "location": location,
                    "url": link_url,
                    "date_posted": date_posted,  # may be None
                    "date_seen": datetime.utcnow().isoformat(timespec="seconds"),
                    "notes": "",
                })

    return rows
