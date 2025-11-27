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

from langdetect import detect_langs
from langdetect.lang_detect_exception import LangDetectException

# ADD: Argos Translate (offline, fast)
import argostranslate.translate as _argos_translate

import logging, warnings
logging.getLogger("stanza").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message="Language pt package default expects mwt*")

EX = Namespace("http://example.org/recipes#")


THRESHOLDS = {
    "recipe_name": 75,   
    "ingredient": 70,    
    "tag": 90,           
}
# If candidate contains explicit Portuguese features, boost preference
PT_PREF_BOOST = 5 


# 1. COOKING TIME REGEX
TIME_PATTERNS = [
    re.compile(r"\b(?P<val>\d{1,3})\s*(minutos|min|mins|minute|minutes)\b", re.I),
    re.compile(r"\b(?P<val>\d{1,2})\s*(h|hora|horas|hour|hours)\b", re.I),
    re.compile(r"\b(?P<h>\d{1,2})\s*h\s*(?P<m>\d{1,2})\s*m?\b", re.I),
    re.compile(r"\b(?P<h>\d{1,2}):(?P<m>\d{1,2})\b"),
]

def detect_language(text: str) -> str:
    """
    Detects the language of the input text using langdetect.
    Returns ISO-639-1 codes (e.g., 'pt', 'en', 'es'), or 'unknown'.
    """
    if not text or not isinstance(text, str):
        return "unknown"

    try:
        langs = detect_langs(text)
        best = langs[0]

        # optional threshold: filter out weak predictions
        if best.prob < 0.60:
            return "unknown"

        return best.lang
    except LangDetectException:
        return "unknown"

def cooking_time_to_minutes(text: str) -> Optional[int]:
    if not text or not isinstance(text, str):
        return None
    t = text.lower()

    # Require an explicit digit somewhere to consider time extraction
    if not re.search(r"\d", t):
        return None

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


# 2. SPACY PIPELINE
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



# 3. KG INDEX + FUZZY SEARCH (with normalization)
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
    
import os, pickle

def load_kg_cached(ttl_path: str, cache_path: str = None):
    if cache_path is None:
        cache_path = ttl_path + ".pkl"

    ttl_mtime = os.path.getmtime(ttl_path)

    # Try to load cache
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                data = pickle.load(f)

            if data.get("_ttl_mtime") == ttl_mtime:
                print("✅ Loaded KG from cache")
                return data["kg"]

        except Exception as e:
            print("⚠️ Cache invalid, rebuilding:", e)

    # Rebuild KG
    print("♻️ Rebuilding KG from TTL...")
    kg = KGIndex.from_ttl(ttl_path)

    # Save cache
    with open(cache_path, "wb") as f:
        pickle.dump({
            "kg": kg,
            "_ttl_mtime": ttl_mtime
        }, f)

    print("✅ KG rebuilt and cached")
    return kg



# 4. NLP CANDIDATES
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


# 5. LINKING (intent-aware, PT-first)
def link_candidates_to_kg(candidates: Dict[str, Any], kg: KGIndex, intent: str) -> Dict[str, Any]:
    chunks: List[str] = candidates["candidate_chunks"]
    # Only keep cooking_time if intent is list_by_time
    cooking_time_raw = candidates["cooking_time"] if intent == "list_by_time" else None
    out = {"ingredient": [], "recipe_name": [], "tag": [], "cooking_time": cooking_time_raw}

    # Heuristic: detect whether the user text is Portuguese (presence of pt chars or PT tokens)
    text_join = " ".join(chunks).lower() if chunks else ""
    prefer_pt = has_portuguese_chars(text_join)

    # If intent is time-related explicitly, only extract cooking time using regex patterns
    if intent == "list_by_time":
        # Only use explicitly parsed time from the user's text.
        # Do NOT infer minutes from KG labels/tags to avoid accidental defaults (e.g., 30).
        if cooking_time_raw is not None:
            out["cooking_time"] = cooking_time_raw
        else:
            out["cooking_time"] = None
        return out

    if intent == "list_by_ingredient":
        for c in chunks:
            matches = kg.search("ingredients", c, limit=3, score_cutoff=THRESHOLDS["ingredient"], prefer_pt=prefer_pt)
            out["ingredient"].extend(matches)
        return out

    if intent == "list_by_tag":
        # Tag domain filtering: only search tags
        # Dynamic lowering of threshold for time-related generic phrases to allow fuzzy match to time tags.
        lowered = any(strip_accents(c).startswith(x) or x in strip_accents(c) for x in ["tempo", "rapido", "rapida", "rapidas", "pouco tempo"] for c in chunks)
        tag_cutoff = 70 if lowered else THRESHOLDS["tag"]
        for c in chunks:
            matches = kg.search("tags", c, limit=3, score_cutoff=tag_cutoff, prefer_pt=prefer_pt)
            out["tag"].extend(matches)
        # Add synonym expansions (synthetic high-score tags) for time expressions
        out["tag"].extend(_expand_time_tag_synonyms(chunks))
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


# 6. MASTER FUNCTION (compatible with your pipeline)
# Minimal accent/spelling normalization (fast) for frequent Portuguese misspellings
_PT_FIX = {
    "acorda": "açorda",
    "faceis": "fáceis",
    "facil": "fácil",
    "facilmente": "facilmente",
    "quejo": "queijo",
    "bras": "brás",
    "braz": "brás",
}

# Protected culinary terms we prefer not to be mistranslated
_PROTECTED_PT_TERMS = {"açorda", "bacalhau", "brás", "braz"}

def _restore_accents_pt(text: str) -> str:
    def repl(m):
        w = m.group(0)
        lw = w.lower()
        fixed = _PT_FIX.get(lw)
        if not fixed:
            return w
        return fixed if w.islower() else fixed.capitalize()
    return re.sub(r"\b\w+\b", repl, text)

def _protect_terms(original: str, translated: str) -> str:
    """
    Ensure protected terms remain (or are re-injected) if Argos mangles them.
    Strategy: if a protected term appears in original (accent-insensitive) but
    not in translated (any form), append the original term at end or replace suspicious token.
    """
    out = translated
    orig_tokens = set(re.findall(r"\b\w+\b", original.lower()))
    for term in _PROTECTED_PT_TERMS:
        # term match accent-insensitive
        norm_term = strip_accents(term)
        if any(strip_accents(t) == norm_term for t in orig_tokens):
            # If missing in translation, reinsert
            if norm_term not in strip_accents(out):
                out = out.strip() + f" {term}"
    return out

def translate_between(text: str, src_lang: str, tgt_lang: str) -> str:
    """
    Offline Argos translation with PT accent restoration + protected term preservation.
    """
    if not text or src_lang == tgt_lang:
        return text
    if src_lang not in {"pt", "en"} or tgt_lang not in {"pt", "en"}:
        return text
    prep = text
    if src_lang == "pt":
        prep = _restore_accents_pt(prep)
    translated = _argos_translate.translate(prep, src_lang, tgt_lang)
    if src_lang == "pt":
        translated = _protect_terms(prep, translated)
    return translated


def _merge_scored_lists(a, b):
    """
    Deduplicate by label; keep the highest score. Return sorted descending.
    """
    a = a or []
    b = b or []
    best = {}
    for label, score in a + b:
        s = float(score)
        if label not in best or s > best[label]:
            best[label] = s
    return sorted(best.items(), key=lambda x: x[1], reverse=True)

#pipeline-compatible function
def extract_and_link(text: str, kg: KGIndex, nlp, intent: str):
    """
    Detect language (PT/EN), run the pipeline on original and translated queries,
    and return the highest-confidence matches across both.
    """
    # 1) Detect language (PT/EN only)
    lang = detect_language(text)
    if lang not in {"pt", "en"}:
        lang = "pt" if has_portuguese_chars(text) else "en"
    other = "en" if lang == "pt" else "pt"

    # 2) Ensure spaCy pipelines for both languages
    nlp_primary = nlp if getattr(nlp, "lang", None) == lang else build_spacy_pipeline(lang)
    nlp_secondary = build_spacy_pipeline(other)

    # 3) Extract candidates on original
    candidates_primary = extract_candidates(text, nlp_primary)

    # Removed automatic intent override; intent remains as predicted.
    linked_primary = link_candidates_to_kg(candidates_primary, kg, intent=intent)

    # 4) Translate and run second pass
    translated_text = translate_between(text, lang, other)
    candidates_secondary = extract_candidates(translated_text, nlp_secondary)
    linked_secondary = link_candidates_to_kg(candidates_secondary, kg, intent=intent)

    # 5) Merge results by highest confidence
    merged = {
        "ingredient": _merge_scored_lists(
            linked_primary.get("ingredient", []),
            linked_secondary.get("ingredient", []),
        ),
        "recipe_name": _merge_scored_lists(
            linked_primary.get("recipe_name", []),
            linked_secondary.get("recipe_name", []),
        ),
        "tag": _merge_scored_lists(
            linked_primary.get("tag", []),
            linked_secondary.get("tag", []),
        ),
        "cooking_time": linked_primary.get("cooking_time") or linked_secondary.get("cooking_time") if intent == "list_by_time" else None,
        # Optional extras (safe to ignore downstream)
        "detected_language": lang,
        "original_query": text,
        "translated_query": translated_text,
    }
    return merged

# Time / speed related PT expressions mapped to KG tags
_TIME_TAG_SYNONYMS = {
    "pouco tempo": ["30-minutes-or-less", "15-minutes-or-less", "time-to-make"],
    "rapido": ["30-minutes-or-less", "15-minutes-or-less", "time-to-make", "quick"],
    "rápido": ["30-minutes-or-less", "15-minutes-or-less", "time-to-make", "quick"],
    "rápidas": ["30-minutes-or-less", "15-minutes-or-less", "time-to-make", "quick"],
    "rapidas": ["30-minutes-or-less", "15-minutes-or-less", "time-to-make", "quick"],
    "rápida": ["30-minutes-or-less", "15-minutes-or-less", "time-to-make", "quick"],
    "rapida": ["30-minutes-or-less", "15-minutes-or-less", "time-to-make", "quick"],
    "fácil": ["easy"],
    "facil": ["easy"],
    "faceis": ["easy"],
    "fáceis": ["easy"],
}

def _expand_time_tag_synonyms(chunks: List[str]) -> List[tuple[str, float]]:
    out = []
    for c in chunks:
        key = strip_accents(c.lower())
        if key in _TIME_TAG_SYNONYMS:
            for tag in _TIME_TAG_SYNONYMS[key]:
                out.append((tag, 96.0))  # high confidence synthetic match
    return out
