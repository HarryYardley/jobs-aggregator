# scripts/run_pipeline.py
import json, csv, os
from datetime import datetime
from pathlib import Path
from adapters.github_markdown import fetch_tables_from_github
from adapters.linkedin import fetch_linkedin_jobs
from adapters.intern_sites import fetch_intern_list, fetch_newgrad_jobs
from adapters.common import company_name_match

def _load_priority_companies_list() -> list[str]:
    p = Path("companies.txt")
    if not p.exists():
        return []
    return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]

# Customize searches for LinkedIn (these seed your focus terms)
INTERN_TITLES = [
    "Mechanical Engineering Intern",
    "Software Engineering Intern",
    "Data Science Intern",
    "Machine Learning Intern",
    "AI Engineer Intern",
    "Summer Intern 2026",
]
NEWGRAD_TITLES = [
    "Mechanical Engineer",
    "Software Engineer",
    "Software Developer",
    "Data Scientist",
    "Machine Learning Engineer",
    "AI Engineer",
    "Quantitative Developer",
    "Quant Developer",
    "New Grad Software Engineer",
    "New Graduate Software Engineer 2026",
]
P1_LOCATIONS = [
    "San Francisco, CA", "New York, NY", "Austin, TX", "Boston, MA", "Seattle, WA",
    "Ann Arbor, MI", "Detroit, MI", "Chicago, IL", "Palo Alto, CA", "Mountain View, CA"
]

def main():
    rows = []

    # 1) GitHub lists
    rows.extend(fetch_tables_from_github())

    # 2) LinkedIn searches (intern + new grad)
    rows.extend(fetch_linkedin_jobs(INTERN_TITLES, P1_LOCATIONS, role_type="Intern"))
    rows.extend(fetch_linkedin_jobs(NEWGRAD_TITLES, P1_LOCATIONS, role_type="New Grad"))

    # 3) New sites
    try:
        rows.extend(fetch_intern_list())
    except Exception:
        pass
    try:
        rows.extend(fetch_newgrad_jobs())
    except Exception:
        pass

    # 4) De-duplicate by URL
    uniq = {}
    for r in rows:
        key = (r.get("url") or "").strip()
        if key and key not in uniq:
            uniq[key] = r
    rows = list(uniq.values())

    # 5) Flag priority companies for datasets (not just display)
    priority_companies_list = _load_priority_companies_list()
    for r in rows:
        r["is_priority_company"] = company_name_match(r.get("company",""), priority_companies_list)

    # 6) Export datasets
    os.makedirs("data", exist_ok=True)
    with open("data/jobs.json","w",encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    with open("data/jobs.csv","w",newline="",encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "source","role_type","job_title","company","location","url",
            "is_priority_company","date_posted","date_seen","notes"
        ])
        writer.writeheader()
        writer.writerows(rows)

    with open("data/last_run.txt","w") as f:
        f.write(datetime.utcnow().isoformat(timespec="seconds"))

    # 7) Build README (strict priority-only, Top 150 per role, last 4 days)
    from build_readme import write_readme
    write_readme(rows)

if __name__ == "__main__":
    main()
