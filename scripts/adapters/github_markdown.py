# scripts/adapters/github_markdown.py
import requests
import pandas as pd
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

def _rendered_readme_url(raw_url: str) -> str:
    # Normalize blob paths to the HTML view that renders tables
    # e.g. https://github.com/owner/repo[/blob/branch/file.md]
    # We'll hit the normal GitHub page; read_html can parse tables from it.
    return raw_url

def role_type_from_repo(url: str) -> str:
    lowered = url.lower()
    if "intern" in lowered:
        return "Intern"
    if "new-grad" in lowered:
        return "New Grad"
    return "Other"

def fetch_tables_from_github():
    rows = []
    for url in GITHUB_REPOS:
        role_type = role_type_from_repo(url)
        r = requests.get(_rendered_readme_url(url), timeout=30)
        r.raise_for_status()
        # Heuristic: extract all tables on the page
        try:
            tables = pd.read_html(r.text)
        except ValueError:
            tables = []

        for df in tables:
            # Try to guess standard columns, then normalize
            cols = [c.strip().lower() for c in df.columns.astype(str)]
            # common names we see in these repos
            col_map = {}
            for i, c in enumerate(cols):
                if "company" in c:
                    col_map["company"] = df.columns[i]
                elif "role" in c or "position" in c or "title" in c:
                    col_map["job_title"] = df.columns[i]
                elif "location" in c:
                    col_map["location"] = df.columns[i]
                elif "link" in c or "apply" in c or "url" in c:
                    col_map["url"] = df.columns[i]

            # If at least company + url exist, take a swing
            if "company" in col_map and "url" in col_map:
                for _, row in df.iterrows():
                    company = str(row.get(col_map.get("company", ""), "")).strip()
                    job_title = str(row.get(col_map.get("job_title", ""), "")).strip()
                    location = str(row.get(col_map.get("location", ""), "")).strip()
                    url_val = str(row.get(col_map.get("url", ""), "")).strip()

                    if not company or not url_val:
                        continue

                    rows.append({
                        "source": f"github:{urlparse(url).path.strip('/')}",
                        "role_type": role_type,
                        "job_title": job_title or "",
                        "company": company,
                        "location": location or "",
                        "url": url_val,
                        "date_posted": None,
                        "date_seen": datetime.utcnow().isoformat(timespec="seconds"),
                        "notes": "",
                    })
    return rows
