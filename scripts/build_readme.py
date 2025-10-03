# scripts/build_readme.py
from collections import Counter
from datetime import datetime

def write_readme(rows):
    total = len(rows)
    by_role = Counter(r["role_type"] for r in rows)
    by_source = Counter(r["source"].split(":")[0] for r in rows)
    priorities = sum(1 for r in rows if r.get("is_priority_company"))

    # Simple “top 20” table for the README
    def row_md(r):
        pr = "✅" if r.get("is_priority_company") else ""
        title = r.get("job_title") or "(title)"
        return f"| {r['role_type']} | {r['company']} | {title} | {r['location']} | [Link]({r['url']}) | {pr} |"

    top20 = rows[:20]  # if you want smarter sorting, add it here

    md = []
    md.append("# 🔎 Job Aggregator (Intern + New Grad)")
    md.append("")
    md.append(f"Last updated: **{datetime.utcnow().isoformat(timespec='seconds')}Z**")
    md.append("")
    md.append("## Summary")
    md.append(f"- Total listings: **{total}**")
    md.append(f"- Intern: **{by_role.get('Intern',0)}** | New Grad: **{by_role.get('New Grad',0)}**")
    md.append(f"- Priority-company hits: **{priorities}**")
    md.append(f"- Sources: {', '.join(f'{k} ({v})' for k,v in by_source.items())}")
    md.append("")
    md.append("Download full datasets: **[CSV](data/jobs.csv)** | **[JSON](data/jobs.json)**")
    md.append("")
    md.append("## Quick View (Top 20)")
    md.append("| Role | Company | Title | Location | Link | Priority |")
    md.append("|---|---|---|---|---|---|")
    md.extend(row_md(r) for r in top20)

    with open("README.md","w",encoding="utf-8") as f:
        f.write("\n".join(md))
