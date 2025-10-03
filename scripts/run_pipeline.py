# scripts/run_pipeline.py
import json, csv, os
from datetime import datetime
from adapters.github_markdown import fetch_tables_from_github
from adapters.linkedin import fetch_linkedin_jobs
from adapters.common import company_name_match

PRIORITY_COMPANIES = [
    # put your top companies list here (or import from a config file)
    "Apple","Google","NVIDIA","Tesla","DE Shaw","Citadel","Balyasny", # ...
]

INTERN_TITLES = ["AI Engineering Intern","Software Engineering Intern","Data Science Intern"]
NEWGRAD_TITLES = ["AI Engineer", "Software Engineer", "Data Scientist", "ML Engineer"]

P1_LOCATIONS = ["San Francisco, CA", "New York, NY", "Austin, TX", "Boston, MA", "Seattle, WA"]  # example

def main():
    rows = []

    # 1) GitHub lists
    rows.extend(fetch_tables_from_github())

    # 2) LinkedIn searches (intern + new grad)
    rows.extend(fetch_linkedin_jobs(INTERN_TITLES, P1_LOCATIONS, role_type="Intern"))
    rows.extend(fetch_linkedin_jobs(NEWGRAD_TITLES, P1_LOCATIONS, role_type="New Grad"))

    # 3) Deduplicate by URL
    uniq = {}
    for r in rows:
        key = r["url"].strip()
        if key and key not in uniq:
            uniq[key] = r
    rows = list(uniq.values())

    # 4) Flag priority companies
    for r in rows:
        r["is_priority_company"] = company_name_match(r.get("company",""), PRIORITY_COMPANIES)

    # 5) Export
    os.makedirs("data", exist_ok=True)
    with open("data/jobs.json","w",encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    with open("data/jobs.csv","w",newline="",encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "source","role_type","job_title","company","location","url","is_priority_company","date_posted","date_seen","notes"
        ])
        writer.writeheader()
        writer.writerows(rows)

    with open("data/last_run.txt","w") as f:
        f.write(datetime.utcnow().isoformat(timespec="seconds"))

    # 6) Build README
    from build_readme import write_readme
    write_readme(rows)

if __name__ == "__main__":
    main()
