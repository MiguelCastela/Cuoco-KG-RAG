import os
import ast
import pandas as pd
from tqdm import tqdm
import re
import langid

# Ensure curated directory exists
os.makedirs("../data/curated", exist_ok=True)

# Load dataset
df = pd.read_csv("../data/raw/RAW_recipes.csv")

# Safely parse lists from text columns (if exist)
def safe_parse(x):
    if isinstance(x, str) and x.startswith("["):
        return ast.literal_eval(x)
    return []

df["tags"]  = df["tags"].apply(safe_parse)         if "tags"  in df.columns else [[]]*len(df)
df["steps"] = df["steps"].apply(safe_parse)        if "steps" in df.columns else [[]]*len(df)

COUNTRY_KEYWORDS = [
    # General
    "portuguese","portugal","azores","madeira","lisbon","porto",
    "coimbra","algarve","braga","sintra",
    # Foods and ingredients (no codfish or sardine anymore)
    "bacalhau","pastel de nata","nata","chouriço",
    "linguiça","feijoada","caldo verde","piri-piri","alheira",
    "azeite","vinho verde","port wine","bolinho","travesseiro",
    "arroz doce","bifana","francesinha","cataplana",
    # Cultural/holiday references
    "fado","saudade","português","lusitan","carnaval","lisboa",
]

def contains_keyword(text: str) -> bool:
    if not isinstance(text, str):
        return False
    tl = text.lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", tl) for kw in COUNTRY_KEYWORDS)

def is_pt(text: str) -> bool:
    if not isinstance(text, str) or len(text.strip()) < 6:
        return False
    lang, prob = langid.classify(text)
    return lang == "pt" and prob >= 0.7

def score_row(row) -> int:
    score = 0

    # 1) keywords
    if contains_keyword(row.get("name","")): score += 3
    if contains_keyword(row.get("description","")): score += 3
    for t in row.get("tags", []):
        if contains_keyword(t): score += 3
    for s in row.get("steps", []):
        if contains_keyword(s): score += 3

    if score >= 3:
        return score

    # 2) language
    if is_pt(row.get("name","")): score += 2
    if is_pt(row.get("description","")): score += 2

    # steps total +2
    step_hits = sum(is_pt(s) for s in row.get("steps", []))
    score += min(2, step_hits)

    return score

df["score"] = [score_row(row) for _, row in tqdm(df.iterrows(), total=len(df), desc="scoring")]

df["is_portuguese"] = df["score"] >= 3

pt_df = df[df["is_portuguese"]]
pt_df.to_csv("data/curated/recipes.csv", index=False)

print(len(pt_df), "Portuguese recipes detected")
print("saved to data/curated/recipes.csv")
