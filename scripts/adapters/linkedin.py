# scripts/adapters/linkedin.py
from datetime import datetime
# import your existing helpers (tokenize, company_name_match, etc.)
# plus requests, BeautifulSoup, tqdm, etc.

def fetch_linkedin_jobs(job_titles, locations, role_type: str):
    """
    role_type: 'Intern' or 'New Grad'
    Returns normalized rows matching the common schema.
    """
    rows = []
    # ... your scraping logic ...
    # For each found job:
    rows.append({
        "source": "linkedin",
        "role_type": role_type,
        "job_title": title,
        "company": company,
        "location": job_location,
        "url": url,
        "date_posted": date_posted or None,   # ISO if possible
        "date_seen": datetime.utcnow().isoformat(timespec="seconds"),
        "notes": "LinkedIn",
    })
    return rows
