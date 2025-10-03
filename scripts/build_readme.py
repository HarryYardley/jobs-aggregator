# scripts/build_readme.py
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
import re
import yaml

# Use your robust tokenizer-based matcher
from adapters.common import company_name_match

# Storage/display date formats
DATE_FMT_STORAGE = "%Y-%m-%d"   # adapters store this
DATE_FMT_DISPLAY = "%b %d"      # show "Oct 03" (no year)

# Display controls per your request
DISPLAY_DAYS = 3
TOP_N = 300
MAX_PER_COMPANY = 3

# ----- Title filters -----
# Positive role signals
ROLE_TERMS = [
    # SWE & variants
    "software engineer", "software developer", "sde", "swe",
    "full stack", "full-stack", "frontend", "front end", "backend", "back end",
    # Data/ML/AI
    "data scientist", "data science", "data engineer", "analytics engineer",
    "machine learning", "ml engineer", "ai engineer", "ml scientist", "ai scientist",
    # Quant
    "quant", "quantitative developer", "quant developer", "quant researcher", "quantitative research",
]

# Intern must-haves (at least one)
INTERN_REQUIRE = [
    "intern", "internship", "summer 2026", "2026 intern"
]

# New-grad must-haves (at least one)
NEWGRAD_REQUIRE = [
    "new grad", "new graduate", "2026"
]

# Exclusion tokens (any presence rejects)
EXCLUDE_TOKENS = [
    "senior", "sr", "staff", "principal", "lead", "director", "manager", "architect",
    "phd", "ph.d", "masters", "master", "ms ", "m.s", "msc", "mba"
]

# ---------- helpers ----------
def _load_company_list() -> list[str]:
    p = Path("companies.txt")
    if not p.exists():
        return []
    return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]

def _to_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s.split("T")[0], DATE_FMT_STORAGE)
    except Exception:
        return None

def _best_posted_date(row) -> datetime | None:
    # Only true posted date; do not fall back to date_seen for README
    return _to_date(row.get("date_posted"))

def _filter_recent(rows, days=DISPLAY_DAYS):
    cutoff = datetime.utcnow() - timedelta(days=days)
    return [r for r in rows if (d := _best_posted_date(r)) and d >= cutoff]

def _display_date(row) -> str:
    d = _best_posted_date(row)
    if not d:
        return ""
    return d.strftime(DATE_FMT_DISPLAY)

def _norm(s: str) -> str:
    return (s or "").strip().lower()

def _contains_any(text: str, terms: list[str]) -> bool:
    t = _norm(text)
    for term in terms:
        # For short tokens (e.g., "ai", "sr", "ml"), use word boundaries to reduce false positives.
        if len(term) <= 3 or term in ("sr", "ai", "ml"):
            if re.search(rf"\b{re.escape(term)}\b", t):
                return True
        else:
            if term in t:
                return True
    return False

def _excluded_title(title: str) -> bool:
    return _contains_any(title, EXCLUDE_TOKENS)

def _title_matches_intern(title: str) -> bool:
    if _excluded_title(title):
        return False
    return _contains_any(title, INTERN_REQUIRE) and _contains_any(title, ROLE_TERMS)

def _title_matches_newgrad(title: str) -> bool:
    if _excluded_title(title):
        return False
    # Should NOT be an internship
    if _contains_any(title, ["intern", "internship"]):
        return False
    return _contains_any(title, NEWGRAD_REQUIRE) and _contains_any(title, ROLE_TERMS)

def _dedup_company_title(rows):
    """Remove duplicates where (company, title) repeats, ignoring location."""
    seen = set()
    out = []
    for r in rows:
        key = (_norm(r.get("company")), _norm(r.get("job_title")))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out

def _cap_per_company(rows, limit=MAX_PER_COMPANY):
    counts = defaultdict(int)
    out = []
    for r in rows:
        key = _norm(r.get("company"))
        if counts[key] >= limit:
            continue
        counts[key] += 1
        out.append(r)
    return out

def _load_applied_urls() -> set[str]:
    """Read optional data/applied.yaml."""
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
    company = r.get("company") or ""
    title   = r.get("job_title") or ""
    loc     = r.get("location") or ""
    posted  = _display_date(r)
    url     = r.get("url","")
    link    = f"[Link]({url})" if url else "Link"
    applied = "☑" if url in applied_urls else "☐"
    return f"| {company} | {title} | {loc} | {posted} | {link} | {applied} |"

# ---------- main renderer ----------
def write_readme(rows):
    company_whitelist = _load_company_list()
    applied_urls = _load_applied_urls()

    total = len(rows)
    by_role = Counter(r["role_type"] for r in rows)
    by_source = Counter((r["source"] or "").split(":")[0] for r in rows)

    # Only rows with real posted date and within N days
    recent = _filter_recent([r for r in rows if _best_posted_date(r) is not None], days=DISPLAY_DAYS)

    # Strict company filter using tokenized matching
    def company_allowed(name: str) -> bool:
        return company_name_match(name or "", company_whitelist)

    # Apply role-specific title + company filters
    interns = [
        r for r in recent
        if r.get("role_type") == "Intern"
        and company_allowed(r.get("company",""))
        and _title_matches_intern(r.get("job_title",""))
    ]

    newgrads = [
        r for r in recent
        if r.get("role_type") == "New Grad"
        and company_allowed(r.get("company",""))
        and _title_matches_newgrad(r.get("job_title",""))
    ]

    # Sort by recency (newest first), then company name
    def recency_key(r):
        d = _best_posted_date(r) or datetime.min
        # negative ordinal = newest first
        return (-d.toordinal(), _norm(r.get("company")))

    interns_sorted  = sorted(interns,  key=recency_key)
    newgrads_sorted = sorted(newgrads, key=recency_key)

    # De-dup by (company,title), cap to ≤3/company, then take Top N
    interns_final  = _cap_per_company(_dedup_company_title(interns_sorted),  limit=MAX_PER_COMPANY)[:TOP_N]
    newgrads_final = _cap_per_company(_dedup_company_title(newgrads_sorted), limit=MAX_PER_COMPANY)[:TOP_N]

    def section_table(title, subset):
        lines = []
        lines.append(f"### {title}")
        if not subset:
            lines.append("_No results matching your constraints in the last few days._")
            lines.append("")
            return lines
        lines.append("| Company | Title | Location | Posted | Link | Applied |")
        lines.append("|---|---|---|---|---|---|")
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
    md.append(f"- Intern (before filtering): **{by_role.get('Intern',0)}** | New Grad (before filtering): **{by_role.get('New Grad',0)}**")
    md.append(f"- Sources: {', '.join(f'{k} ({v})' for k,v in by_source.items())}")
    md.append("")
    md.append("Download full datasets: **[CSV](data/jobs.csv)** | **[JSON](data/jobs.json)**")
    md.append("")
    md.extend(section_table(f"Top {TOP_N} Intern postings (last {DISPLAY_DAYS} days, deduped, ≤{MAX_PER_COMPANY}/company, strict title+company filters)", interns_final))
    md.extend(section_table(f"Top {TOP_N} New Grad postings (last {DISPLAY_DAYS} days, deduped, ≤{MAX_PER_COMPANY}/company, strict title+company filters)", newgrads_final))

    with open("README.md","w",encoding="utf-8") as f:
        f.write("\n".join(md))
