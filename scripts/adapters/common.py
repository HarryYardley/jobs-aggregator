# scripts/adapters/common.py
import re

STOPWORDS = {"the","and","inc","llc","ltd","corp","corporation","co","of","for","a"}

def tokenize(name: str):
    tokens = re.findall(r'\w+', (name or "").lower())
    return {t for t in tokens if len(t) >= 3 and t not in STOPWORDS}

def company_name_match(company_name, priority_companies):
    company_tokens = tokenize(company_name)
    for pc in priority_companies:
        if company_tokens & tokenize(pc):
            return True
    return False
