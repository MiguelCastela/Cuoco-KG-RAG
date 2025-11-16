"""
entity_extraction.py

Features:
- Portuguese-first fuzzy matching (heuristic prioritization).
- Unicode normalization (accent-preserving & accent-stripped forms).
- Per-collection thresholds tuned for better precision.
- Tag domain filtering (only search tags for tag intents).
- Cooking-time extraction and list_by_time support.
- Backwards-compatible function signatures for pipeline.py usage.

Dependencies:
- spacy
- rdflib
- rapidfuzz

Drop-in replacement: keep your pipeline.py as-is except for the small changes listed later.
"""
from __future__ import annotations
import re, unicodedata
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

import spacy
from spacy.pipeline import EntityRuler

from rdflib import Graph, Namespace, RDF, RDFS
from rapidfuzz import process, fuzz

EX = Namespace("http://example.org/recipes#")


# -----------------------
# Configurable thresholds (tune these)
# scores are 0..100 when passed to rapidfuzz score_cutoff
THRESHOLDS = {
    "recipe_name": 60,   # more strict (want accurate recipe title)
    "ingredient": 50,    # medium
    "tag": 45,           # lower but domain-filtered
}
# If candidate contains explicit Portuguese features, boost preference
PT_PREF_BOOST = 5  # add to score for PT-likely items


# ===========================================================
# 1. COOKING TIME REGEX
# ===========================================================
TIME_PATTERNS = [
    re.compile(r"\b(?P<val>\d{1,3})\s*(minutos|min|mins|minute|minutes)\b", re.I),
    re.compile(r"\b(?P<val>\d{1,2})\s*(h|hora|horas|hour|hours)\b", re.I),
    re.compile(r"\b(?P<h>\d{1,2})\s*h\s*(?P<m>\d{1,2})\s*m?\b", re.I),
    re.compile(r"\b(?P<h>\d{1,2}):(?P<m>\d{1,2})\b"),
]

def cooking_time_to_minutes(text: str) -> Optional[int]:
    if not text or not isinstance(text, str):
        return None
    t = text.lower()

    # Combined H + M first
    for pat in TIME_PATTERNS[2:]:
        m = pat.search(t)
        if m:
            try:
                return int(m.group("h")) * 60 + int(m.group("m"))
            except Exception:
                pass

    # Minutes only
    m = TIME_PATTERNS[0].search(t)
    if m:
        try:
            return int(m.group("val"))
        except Exception:
            pass

    # Hours only
    m = TIME_PATTERNS[1].search(t)
    if m:
        try:
            return int(m.group("val")) * 60
        except Exception:
            pass

    return None


# ===========================================================
# 2. SPACY PIPELINE
# ===========================================================
def build_spacy_pipeline(lang_priority: str = "pt"):
    """
    Load a PT or EN spaCy model. Fall back to blank "xx".
    Adds EntityRuler for simple TIME cues.
    """
    models = ["pt_core_news_sm", "en_core_web_sm"] if lang_priority == "pt" \
             else ["en_core_web_sm", "pt_core_news_sm"]

    nlp = None
    for m in models:
        try:
            nlp = spacy.load(m)
            break
        except Exception:
            pass

    if nlp is None:
        nlp = spacy.blank("xx")

    # EntityRuler for TIME keywords
    if "entity_ruler" not in nlp.pipe_names:
        try:
            ruler = nlp.add_pipe("entity_ruler", config={"overwrite_ents": True})
        except Exception:
            ruler = EntityRuler(nlp)
            nlp.add_pipe(ruler)
    else:
        ruler = nlp.get_pipe("entity_ruler")

    ruler.add_patterns([
        {"label": "TIME", "pattern": [{"LOWER": {"IN": ["min", "mins", "minutos", "minuto"]}}]},
        {"label": "TIME", "pattern": [{"LOWER": {"IN": ["h", "hora", "horas", "hour", "hours"]}}]},
    ])
    return nlp


# ===========================================================
# 3. KG INDEX + FUZZY SEARCH (with normalization)
# ===========================================================
def strip_accents(s: str) -> str:
    """Return accent-stripped lowercased form"""
    if not isinstance(s, str):
        return s
    nk = unicodedata.normalize("NFKD", s)
    return "".join([c for c in nk if not unicodedata.combining(c)]).lower()

def has_portuguese_chars(s: str) -> bool:
    """Heuristic: accents or 'ç' or typical Portuguese words"""
    if not isinstance(s, str):
        return False
    if re.search(r"[áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚ]", s):
        return True
    # also check common PT words
    if re.search(r"\b(para|com|sem|receita|rápido|fácil|fáceis|cozinhar|açorda|bacalhau)\b", s, re.I):
        return True
    return False

@dataclass
class KGIndex:
    recipes: List[str]
    ingredients: List[str]
    tags: List[str]
    recipe_label_to_subject: Dict[str, Any]
    graph: Graph
    # precomputed normalized maps
    recipes_norm: List[str]
    ingredients_norm: List[str]
    tags_norm: List[str]

    @classmethod
    def from_ttl(cls, ttl_path: str):
        g = Graph()
        g.parse(ttl_path, format="turtle")

        def labels_of(rdf_type) -> List[str]:
            vals = []
            for s in g.subjects(RDF.type, rdf_type):
                lab = g.value(s, RDFS.label)
                if lab is not None:
                    vals.append(str(lab))
            return vals

        recipes = []
        recipe_label_to_subject = {}
        for s in g.subjects(RDF.type, EX.Recipe):
            lab = g.value(s, RDFS.label)
            if lab is not None:
                label_str = str(lab)
                recipes.append(label_str)
                recipe_label_to_subject[label_str] = s

        ingredients = labels_of(EX.Ingredient)
        tags = labels_of(EX.Tag)

        # Precompute normalized lists (accent stripped & lower)
        recipes_norm = [strip_accents(x) for x in recipes]
        ingredients_norm = [strip_accents(x) for x in ingredients]
        tags_norm = [strip_accents(x) for x in tags]

        return cls(
            recipes=recipes,
            ingredients=ingredients,
            tags=tags,
            recipe_label_to_subject=recipe_label_to_subject,
            graph=g,
            recipes_norm=recipes_norm,
            ingredients_norm=ingredients_norm,
            tags_norm=tags_norm
        )

    def _choose_collection(self, collection: str):
        if collection == "recipes":
            return self.recipes, self.recipes_norm
        if collection == "ingredients":
            return self.ingredients, self.ingredients_norm
        if collection == "tags":
            return self.tags, self.tags_norm
        raise ValueError("Unknown collection: " + collection)

    def search(self, collection: str, query: str, limit=5, score_cutoff=50, prefer_pt=False):
        """
        Query: original user candidate string.
        prefer_pt: boolean hint to prefer pt-labeled items when candidate looks portuguese.
        Returns list of (match_label, score_float).
        """
        items, items_norm = self._choose_collection(collection)
        if not query:
            return []

        # Build search pool as (orig_label, norm_label)
        query_norm = strip_accents(query)
        # 1) Use rapidfuzz on the normalized lists (faster and more robust across diacritics)
        raw_results = process.extract(query_norm, items_norm, scorer=fuzz.WRatio, limit=limit, score_cutoff=score_cutoff)
        # raw_results: list of (matched_norm_label, score, idx)
        results = []
        for matched_norm, score, idx in raw_results:
            orig_label = items[idx]
            adj_score = float(score)
            # boost Portuguese-labelled items if requested and heuristic indicates PT
            if prefer_pt and has_portuguese_chars(orig_label):
                adj_score = min(100.0, adj_score + PT_PREF_BOOST)
            results.append((orig_label, adj_score))
        return results


# ===========================================================
# 4. NLP CANDIDATES
# ===========================================================
def extract_candidates(text: str, nlp):
    """
    Returns:
        {
            "candidate_chunks": [str,...],
            "cooking_time": int|None,
            "raw_doc": doc
        }
    """
    doc = nlp(text)
    # gather noun_chunks (avoid duplicates)
    noun_chunks = []
    try:
        for nc in doc.noun_chunks:
            chunk = nc.text.strip()
            if len(chunk) >= 2:
                noun_chunks.append(chunk)
    except Exception:
        # fallback simple token-based grouping for blank models
        noun_chunks = [t.text for t in doc if len(t.text) > 2]

    # Also include quoted strings and direct objects found as PROPN/NOUN tokens
    quoted = re.findall(r'["\']([^"\']{2,})["\']', text)
    noun_chunks.extend([q for q in quoted])

    # Filter generic words
    blacklist = {"ingredientes", "ingredients", "recipe", "receita", "receitas", "com", "para", "a"}
    noun_chunks = [c for c in noun_chunks if c.lower() not in blacklist]

    # Deduplicate preserving order
    seen = set()
    final_chunks = []
    for c in noun_chunks:
        ck = c.lower().strip()
        if ck not in seen:
            seen.add(ck)
            final_chunks.append(c)

    return {"candidate_chunks": final_chunks, "cooking_time": cooking_time_to_minutes(text), "doc": doc}


# ===========================================================
# 5. LINKING (intent-aware, PT-first)
# ===========================================================
def link_candidates_to_kg(candidates: Dict[str, Any], kg: KGIndex, intent: str) -> Dict[str, Any]:
    chunks: List[str] = candidates["candidate_chunks"]
    cooking_time = candidates["cooking_time"]
    out = {"ingredient": [], "recipe_name": [], "tag": [], "cooking_time": cooking_time}

    # Heuristic: detect whether the user text is Portuguese (presence of pt chars or PT tokens)
    text_join = " ".join(chunks).lower() if chunks else ""
    prefer_pt = has_portuguese_chars(text_join)

    # If intent is time-related explicitly, prefer recipe matching + cooking_time use
    if intent == "list_by_time":
        # We'll return cooking_time (already present) and possibly matched recipes
        if cooking_time:
            out["cooking_time"] = cooking_time
        for c in sorted(chunks, key=len, reverse=True):
            matches = kg.search("recipes", c, limit=1, score_cutoff=THRESHOLDS["recipe_name"], prefer_pt=prefer_pt)
            if matches:
                out["recipe_name"].append(matches[0])
                break
        return out

    if intent == "list_by_ingredient":
        for c in chunks:
            matches = kg.search("ingredients", c, limit=3, score_cutoff=THRESHOLDS["ingredient"], prefer_pt=prefer_pt)
            out["ingredient"].extend(matches)
        return out

    if intent == "list_by_tag":
        # Tag domain filtering: only search tags
        for c in chunks:
            matches = kg.search("tags", c, limit=3, score_cutoff=THRESHOLDS["tag"], prefer_pt=prefer_pt)
            out["tag"].extend(matches)
        return out

    if intent in {"find_recipe", "retrieve_ingredients", "get_prep_time"}:
        # Try to match best recipe name from longest chunks
        for c in sorted(chunks, key=len, reverse=True):
            matches = kg.search("recipes", c, limit=1, score_cutoff=THRESHOLDS["recipe_name"], prefer_pt=prefer_pt)
            if matches:
                out["recipe_name"].append(matches[0])
                break
        return out

    # fallback: attempt recipe matching
    for c in sorted(chunks, key=len, reverse=True):
        matches = kg.search("recipes", c, limit=1, score_cutoff=THRESHOLDS["recipe_name"], prefer_pt=prefer_pt)
        if matches:
            out["recipe_name"].append(matches[0])
            break
    return out


# ===========================================================
# 6. MASTER FUNCTION (compatible with your pipeline)
# ===========================================================
def extract_and_link(text: str, kg: KGIndex, nlp, intent: str):
    """
    Keep signature: extract_and_link(text, intent=..., nlp=NLP, kg=KG)
    """
    candidates = extract_candidates(text, nlp)
    # safety rule: if text explicitly mentions time but intent is not time, override to list_by_time
    if candidates.get("cooking_time") is not None and intent not in {"list_by_time", "get_prep_time"}:
        # override only when user explicitly mentions time tokens
        # e.g. "em 30 minutos", "que demorem 30", "30 mins"
        # keep a conservative override to avoid false positives
        if re.search(r"\b(\d{1,3})\s*(minutos|min|mins|h|hora|horas)\b", text, re.I):
            intent = "list_by_time"

    linked = link_candidates_to_kg(candidates, kg, intent=intent)
    return linked
