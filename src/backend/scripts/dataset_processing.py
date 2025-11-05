import os
import ast
import pandas as pd
from tqdm import tqdm
import re
import langid

os.makedirs("data/curated", exist_ok=True)

df = pd.read_csv("data/raw/RAW_recipes.csv")

def safe_parse(x):
    if isinstance(x, str) and x.startswith("["):
        return ast.literal_eval(x)
    return []

df["tags"]  = df["tags"].apply(safe_parse)         if "tags"  in df.columns else [[]]*len(df)
df["steps"] = df["steps"].apply(safe_parse)        if "steps" in df.columns else [[]]*len(df)

COUNTRY_KEYWORDS = [
    "portuguese","portugal","azores","madeira","lisbon","porto",
    "coimbra","algarve","braga","sintra","bacalhau","pastel de nata",
    "nata","chouriço","linguiça","feijoada","caldo verde","piri-piri",
    "alheira","azeite","vinho verde","port wine","bolinho","travesseiro",
    "arroz doce","bifana","francesinha","cataplana","fado","saudade",
    "português","lusitan","carnaval","lisboa",
]

KW_REGEX = re.compile("|".join(re.escape(k) for k in COUNTRY_KEYWORDS))

def contains_kw(text: str) -> bool:
    return isinstance(text, str) and KW_REGEX.search(text.lower()) is not None

def is_pt(text: str) -> bool:
    if not isinstance(text, str) or len(text) < 8: return False
    lang, prob = langid.classify(text)
    return lang == "pt" and prob >= 0.8

def classify_row(row):
    # keyword pass
    if contains_kw(row.get("name","")): return True
    if contains_kw(row.get("description","")): return True
    if any(contains_kw(t) for t in row.get("tags", [])): return True
    
    # fallback: lang only on name + desc
    if is_pt(row.get("name","")): return True
    if is_pt(row.get("description","")): return True
    return False

df["is_pt"] = [classify_row(row) for _, row in tqdm(df.iterrows(), total=len(df))]

pt_df = df[df["is_pt"]]
pt_df.to_csv("data/curated/recipes.csv", index=False)

print("Portuguese recipes:", len(pt_df))
