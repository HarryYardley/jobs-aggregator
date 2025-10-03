# scripts/build_readme.py
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

DATE_FMT = "%Y-%m-%d"  # for date_posted parsing

INTERN_TERMS = [
    "intern", "summer intern", "summer 2026", "2026 intern", "internship"
]
NEWGRAD_TERMS = [
    "new grad", "new graduate", "new graduate 2026", "2026", "entry level"
]
ROLE_TERMS = [
    "software engineer", "software developer", "data science", "data scientist",
    "machine learning engineer", "ml engineer", "ai engineer",
    "quantitative developer", "quant developer"
]

def _load_priority_companies() -> set[str]:
    p = Path("companies.txt")
    if not p.exists():
        return set()
    lines = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()]
    return {ln for ln in lines if ln}

def _is_priority_company(company: str, priorities: set[str]) -> bool:
    if not company:
        return False
    lc = company.lower()
    return any(p.lower() in lc for p in priorities)  # simple contains; you already dedupe tokens earlier if desired

def _to_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # expected YYYY-MM-DD
        return datetime.strptime(s.split("T")[0], DATE_FMT)
    except Exception:
        return None

def _days_ago(d: datetime) -> int:
    return (datetime.utcnow() - d).days

def _keyword_hit(title: str, role_type: str) -> bool:
    t = (title or "").lower()
    has_role_term = any(term in t for term in ROLE_TERMS)
    if role_type == "Intern":
        return any(term in t for term in INTERN_TERMS) and has_role_term
    if role_type == "New Grad":
        return any(term in t for term in NEWGRAD_TERMS) and has_role_term
    return False

def _best_posted_date(row) -> datetime | None:
    # Prefer date_posted; fallback to date_seen
    d1 = _to_date(row.get("date_posted"))
    if d1:
        return d1
    d2 = _to_date(row.get("date_seen"))
    return d2

def _filter_recent(rows, days=4):
    cutoff = datetime.utcnow() - timedelta(days=days)
    kept = []
    for r in rows:
        d = _best_posted_date(r)
        if d and d >= cutoff:
            kept.append(r)
    return kept

def _display_date(row) -> str:
    d = _best_posted_date(row)
    if not d:
        return ""
    return d.strftime(DATE_FMT)

def _score_row(row, priority_companies: set[str]) -> tuple:
    # Sort key (higher priority first): priority_company desc, keyword_hit desc, recency asc (fewer days), company asc
    pr = 1 if _is_priority_company(row.get("company",""), priority_companies) or row.get("is_priority_company") else 0
    kw = 1 if _keyword_hit(row.get("job_title",""), row.get("role_type","")) else 0
    d = _best_posted_date(row) or datetime.min
    return (-pr, -kw, _days_ago(d), (row.get("company") or "").lower())

def _md_link(text: str, url: str) -> str:
    if not url:
        return text or ""
    return f"[{text or 'Link'}]({url})"

def _row_md(r):
    pr = "✅" if r.get("is_priority_company") else ("✅" if r.get("__priority_match") else "")
    company = r.get("company") or ""
    title   = r.get("job_title") or ""
    loc     = r.get("location") or ""
    posted  = _display_date(r)
    link    = _md_link("Link", r.get("url",""))
    return f"| {company} | {title} | {loc} | {posted} | {link} | {pr} |"

def write_readme(rows):
    priority_companies = _load_priority_companies()

    # ensure is_priority_company set if companies.txt exists
    for r in rows:
        if _is_priority_company(r.get("company",""), priority_companies):
            r["__priority_match"] = True

    total = len(rows)
    by_role = Counter(r["role_type"] for r in rows)
    by_source = Counter((r["source"] or "").split(":")[0] for r in rows)

    # Recent subset (past 4 days)
    recent = _filter_recent(rows, days=4)

    interns = [r for r in recent if r.get("role_type") == "Intern"]
    newgrads = [r for r in recent if r.get("role_type") == "New Grad"]

    interns_sorted = sorted(interns, key=lambda r: _score_row(r, priority_companies))
    newgrads_sorted = sorted(newgrads, key=lambda r: _score_row(r, priority_companies))

    interns_top = interns_sorted[:50]
    newgrads_top = newgrads_sorted[:50]

    def section_table(title, subset):
        lines = []
        lines.append(f"### {title}")
        if not subset:
            lines.append("_No recent postings in the last 4 days._")
            lines.append("")
            return lines
        lines.append("| Company | Title | Location | Posted | Link | Priority |")
        lines.append("|---|---|---|---|---|---|")
        lines.extend(_row_md(r) for r in subset)
        lines.append("")
        return lines

    md = []
    md.append("# 🔎 Job Aggregator (Intern + New Grad)")
    md.append("")
    md.append(f"Last updated: **{datetime.utcnow().isoformat(timespec='seconds')}Z**")
    md.append("")
    md.append("## Summary")
    md.append(f"- Total listings parsed (all time in repo): **{total}**")
    md.append(f"- Intern: **{by_role.get('Intern',0)}** | New Grad: **{by_role.get('New Grad',0)}**")
    md.append(f"- Sources: {', '.join(f'{k} ({v})' for k,v in by_source.items())}")
    md.append("")
    md.append("Download full datasets: **[CSV](data/jobs.csv)** | **[JSON](data/jobs.json)**")
    md.append("")
    md.extend(section_table("Top 50 Intern postings (last 4 days, priority & keywords first)", interns_top))
    md.extend(section_table("Top 50 New Grad postings (last 4 days, priority & keywords first)", newgrads_top))

    with open("README.md","w",encoding="utf-8") as f:
        f.write("\n".join(md))
