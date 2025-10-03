# scripts/adapters/intern_sites.py
from __future__ import annotations
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

INTERN_LIST_URL = "https://www.intern-list.com/"
NEWGRAD_JOBS_URL = "https://www.newgrad-jobs.com/"

def _parse_table_like(soup, role_type: str, base_url: str):
    """
    Parse the large job table:
      columns of interest: Position Title, Date, Apply (link), Work Model, Location, Company
    We try to match by header text to be robust.
    """
    rows = []
    tables = soup.select("table")
    for table in tables:
        # headers
        header_cells = []
        thead = table.find("thead")
        if thead:
            header_cells = [th.get_text(strip=True).lower() for th in thead.find_all("th")]
        else:
            first = table.find("tr")
            if first:
                header_cells = [c.get_text(strip=True).lower() for c in first.find_all(["th","td"])]

        def idx(*names):
            for name in names:
                for i, h in enumerate(header_cells):
                    if name in h:
                        return i
            return None

        i_title = idx("position title", "title", "position")
        i_date  = idx("date", "posted")
        i_apply = idx("apply", "link", "url")
        i_loc   = idx("location")
        i_comp  = idx("company")

        # must have title + link + company to be useful
        if i_title is None or i_apply is None or i_comp is None:
            continue

        tbody = table.find("tbody") or table
        for tr in tbody.find_all("tr"):
            tds = tr.find_all(["td","th"])
            if not tds:
                continue

            def text(i):
                if i is None or i >= len(tds):
                    return ""
                return tds[i].get_text(strip=True)

            # link:
            url = ""
            if i_apply is not None and i_apply < len(tds):
                a = tds[i_apply].find("a", href=True)
                if a:
                    url = a["href"].strip()
                    if url and not url.startswith("http"):
                        url = urljoin(base_url, url)

            if not url:
                continue

            # date (expect YYYY-MM-DD on these sites)
            date_posted = None
            if i_date is not None and i_date < len(tds):
                raw = text(i_date)
                try:
                    dt = raw.split("T")[0].strip()
                    if len(dt) == 10:
                        datetime.strptime(dt, "%Y-%m-%d")
                        date_posted = dt
                except Exception:
                    date_posted = None

            rows.append({
                "source": f"site:{base_url.rstrip('/')}",
                "role_type": role_type,
                "job_title": text(i_title),
                "company": text(i_comp),
                "location": text(i_loc),
                "url": url,
                "date_posted": date_posted,
                "date_seen": datetime.utcnow().isoformat(timespec="seconds"),
                "notes": "parsed from site table",
            })
    return rows

def fetch_intern_list():
    resp = requests.get(INTERN_LIST_URL, headers=DEFAULT_HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    # Site has multiple categories; we still tag as Intern
    return _parse_table_like(soup, role_type="Intern", base_url=INTERN_LIST_URL)

def fetch_newgrad_jobs():
    resp = requests.get(NEWGRAD_JOBS_URL, headers=DEFAULT_HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return _parse_table_like(soup, role_type="New Grad", base_url=NEWGRAD_JOBS_URL)
