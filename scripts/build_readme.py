# scripts/build_readme.py
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
import yaml

# Storage/display date formats
DATE_FMT_STORAGE = "%Y-%m-%d"   # what adapters store
DATE_FMT_DISPLAY = "%b %d"      # README shows "Oct 03" (no year)

# Display controls
DISPLAY_DAYS = 3
TOP_N = 300
DISPLAY_ONLY_PRIORITY = True  # strict filter: only companies in companies.txt

# Keyword boosts (kept from prior version)
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
    return any(p.lower() in lc for p in priorities)

def _to_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s.split("T")[0], DATE_FMT_STORAGE)
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
    # For README, only use real posted dates (not date_seen)
    return _to_date(row.get("date_posted"))

def _filter_recent(rows, days=DISPLAY_DAYS):
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
    return d.strftime(DATE_FMT_DISPLAY)

def _score_row(row, priority_companies: set[str]) -> tuple:
    # Higher priority first: (priority company, keyword hit, recency, company name)
    pr = 1 if (_is_priority_company(row.get("company",""), priority_companies) or row.get("is_priority_company")) else 0
    kw = 1 if _keyword_hit(row.get("job_title",""), row.get("role_type","")) else 0
    d = _best_posted_date(row) or datetime.min
    return (-pr, -kw, _days_ago(d), (row.get("company") or "").lower())

def _md_link(text: str, url: str) -> str:
    if not url:
        return text or ""
    return f"[{text or 'Link'}]({url})"

def _normalize(s: str) -> str:
    return (s or "").strip().lower()

def _dedup_company_title(rows):
    """Remove duplicates where (company, title) repeated, ignoring location."""
    seen = set()
    out = []
    for r in rows:
        key = (_normalize(r.get("company")), _normalize(r.get("job_title")))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out

def _cap_per_company(rows, limit=3):
    """Keep at most `limit` rows per company (after sorting)."""
    counts = defaultdict(int)
    out = []
    for r in rows:
        key = _normalize(r.get("company"))
        if counts[key] >= limit:
            continue
        counts[key] += 1
        out.append(r)
    return out

def _load_applied_urls() -> set[str]:
    """
    Reads optional data/applied.yaml.
    Format options:
      applied:
        - https://job1
        - https://job2
    or simply:
      - https://job1
      - https://job2
    """
    p = Path("data/applied.yaml")
    if not p.exists():
        return set()
    content = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if isinstance(content, dict) and "applied" in content and isinstance(content["applied"], list):
        return {u.strip() for u in content["applied"] if isinstance(u, str)}
    if isinstance(content, list):
        return {u.strip() for u in content if isinstance(u, str)}
    return set()

def _row_md(r, applied_urls: set[str]):
    pr = "✅" if (r.get("is_priority_company") or r.get("__priority_match")) else ""
    company = r.get("company") or ""
    title   = r.get("job_title") or ""
    loc     = r.get("location") or ""
    posted  = _display_date(r)
    url     = r.get("url","")
    link    = _md_link("Link", url)
    applied = "☑" if url in applied_urls else "☐"   # visual checkmark only (state in data/applied.yaml)
    return f"| {company} | {title} | {loc} | {posted} | {link} | {pr} | {applied} |"

def write_readme(rows):
    priority_companies = _load_priority_companies()
    applied_urls = _load_applied_urls()

    # Mark priority for display (in case pipeline didn't set is_priority_company)
    for r in rows:
        if _is_priority_company(r.get("company",""), priority_companies):
            r["__priority_match"] = True

    total = len(rows)
    by_role = Counter(r["role_type"] for r in rows)
    by_source = Counter((r["source"] or "").split(":")[0] for r in rows)

    # Only rows with a real posted date, and recent
    dated_rows = [r for r in rows if _best_posted_date(r) is not None]
    recent = _filter_recent(dated_rows, days=DISPLAY_DAYS)

    interns = [r for r in recent if r.get("role_type") == "Intern"]
    newgrads = [r for r in recent if r.get("role_type") == "New Grad"]

    # Only show priority companies on README (CSV/JSON still contain all)
    if DISPLAY_ONLY_PRIORITY and priority_companies:
        interns = [r for r in interns if _is_priority_company(r.get("company",""), priority_companies)]
        newgrads = [r for r in newgrads if _is_priority_company(r.get("company",""), priority_companies)]

    # Sort by priority/keywords/recency, then de-dupe by (company, title),
    # then cap to at most 3 per company, finally take Top N.
    interns_sorted = sorted(interns, key=lambda r: _score_row(r, priority_companies))
    newgrads_sorted = sorted(newgrads, key=lambda r: _score_row(r, priority_companies))

    interns_nodup = _dedup_company_title(interns_sorted)
    newgrads_nodup = _dedup_company_title(newgrads_sorted)

    interns_capped = _cap_per_company(interns_nodup, limit=3)[:TOP_N]
    newgrads_capped = _cap_per_company(newgrads_nodup, limit=3)[:TOP_N]

    def section_table(title, subset):
        lines = []
        lines.append(f"### {title}")
        if not subset:
            lines.append("_No recent postings in the last few days that matched your company list._")
            lines.append("")
            return lines
        lines.append("| Company | Title | Location | Posted | Link | Priority | Applied |")
        lines.append("|---|---|---|---|---|---|---|")
        lines.extend(_row_md(r, applied_urls) for r in subset)
        lines.append("")
        return lines

    md = []
    md.append("# 🔎 Job Aggregator (Intern + New Grad)")
    md.append("")
    md.append(f"Last updated: **{datetime.utcnow().isoformat(timespec='seconds')}Z**")
    md.append("")
    md.append("## Summary")
    md.append(f"- Total listings parsed (all sources): **{total}**")
    md.append(f"- Intern: **{by_role.get('Intern',0)}** | New Grad: **{by_role.get('New Grad',0)}**")
    md.append(f"- Sources: {', '.join(f'{k} ({v})' for k,v in by_source.items())}")
    md.append("")
    md.append("Download full datasets: **[CSV](data/jobs.csv)** | **[JSON](data/jobs.json)**")
    md.append("")
    md.extend(section_table(f"Top {TOP_N} Intern postings (last {DISPLAY_DAYS} days, deduped & ≤3/company)", interns_capped))
    md.extend(section_table(f"Top {TOP_N} New Grad postings (last {DISPLAY_DAYS} days, deduped & ≤3/company)", newgrads_capped))

    with open("README.md","w",encoding="utf-8") as f:
        f.write("\n".join(md))
