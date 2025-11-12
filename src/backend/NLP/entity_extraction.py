"""
Rule-assisted entity extraction (ingredient, recipe_name, cooking_time) and KG linking.

Features:
- spaCy pipeline with light-weight patterns; works if spaCy models are missing (falls back to blank pipeline).
- Regex-based cooking time extraction with normalization to minutes.
- KG indexing from Turtle (recipes_graph_cleaned.ttl) via rdflib.
- Fuzzy matching using rapidfuzz to link extracted text to KG labels.

Usage:
    python -m backend.NLP.demo_entities  # see demo script for examples
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
    import spacy
    from spacy.pipeline import EntityRuler
except Exception:  # pragma: no cover - allow import even if spacy isn't installed yet
    spacy = None
    EntityRuler = None

from rdflib import Graph, Namespace, RDF, RDFS

try:
    from rapidfuzz import process, fuzz
except Exception:
    # Minimal fallback if rapidfuzz isn't available
    process = None
    fuzz = None


EX = Namespace("http://example.org/recipes#")


# ---- Cooking time parsing ----
TIME_PATTERNS = [
    # e.g., 30 min, 30 mins, 30 minutos
    re.compile(r"\b(?P<val>\d{1,3})\s*(minutos|min|mins|minute|minutes)\b", re.I),
    # e.g., 1 h, 2 horas, 1 hora
    re.compile(r"\b(?P<val>\d{1,2})\s*(h|hora|horas|hour|hours)\b", re.I),
    # e.g., 1h30, 1h 30m
    re.compile(r"\b(?P<h>\d{1,2})\s*h\s*(?P<m>\d{1,2})\s*m?\b", re.I),
    # e.g., 1:30 (hh:mm)
    re.compile(r"\b(?P<h>\d{1,2}):(?P<m>\d{1,2})\b"),
]


def cooking_time_to_minutes(text: str) -> Optional[int]:
    if not isinstance(text, str):
        return None
    t = text.strip().lower()
    # Try combined hour+minute first
    for pat in TIME_PATTERNS[2:]:
        m = pat.search(t)
        if m:
            try:
                h = int(m.group("h"))
                m_val = int(m.group("m"))
                return h * 60 + m_val
            except Exception:
                continue

    # Try pure minutes
    m = TIME_PATTERNS[0].search(t)
    if m:
        try:
            return int(m.group("val"))
        except Exception:
            pass

    # Try pure hours
    m = TIME_PATTERNS[1].search(t)
    if m:
        try:
            return int(m.group("val")) * 60
        except Exception:
            pass

    return None


# ---- spaCy pipeline ----
def build_spacy_pipeline(lang_priority: str = "pt"):
    """
    Try to load a Portuguese or English model; fallback to blank pipeline with an EntityRuler.
    """
    nlp = None
    model_candidates = []
    if lang_priority == "pt":
        model_candidates = ["pt_core_news_sm", "en_core_web_sm"]
    else:
        model_candidates = ["en_core_web_sm", "pt_core_news_sm"]

    if spacy is None:
        return None

    for m in model_candidates:
        try:
            nlp = spacy.load(m)
            break
        except Exception:
            continue
    if nlp is None:
        nlp = spacy.blank("xx")

    # Add an EntityRuler with light patterns (mainly to help cooking time keywords)
    try:
        ruler = nlp.add_pipe("entity_ruler")
    except Exception:
        # Older spaCy: insert with name
        ruler = EntityRuler(nlp)
        nlp.add_pipe(ruler)

    patterns = [
        {"label": "TIME", "pattern": [{"LOWER": {"IN": ["min", "mins", "minute", "minutes", "minutos"]}}]},
        {"label": "TIME", "pattern": [{"LOWER": {"IN": ["h", "hour", "hours", "hora", "horas"]}}]},
    ]
    ruler.add_patterns(patterns)
    return nlp


@dataclass
class KGIndex:
    recipes: List[str]
    ingredients: List[str]
    tags: List[str]
    # internal: mapping label -> subject and rdflib Graph
    recipe_label_to_subject: Dict[str, object] = None
    graph: Optional[Graph] = None

    @classmethod
    def from_ttl(cls, ttl_path: str) -> "KGIndex":
        g = Graph()
        g.parse(ttl_path, format="turtle")

        def labels_of(rdf_type) -> List[str]:
            vals: List[str] = []
            for s in g.subjects(RDF.type, rdf_type):
                lab = g.value(s, RDFS.label)
                if lab is not None:
                    vals.append(str(lab))
            return vals

        # Build label -> subject map for recipes (use rdfs:label)
        recipes = []
        recipe_label_to_subject: Dict[str, object] = {}
        for s in g.subjects(RDF.type, EX.Recipe):
            lab = g.value(s, RDFS.label)
            if lab is not None:
                label_str = str(lab)
                recipes.append(label_str)
                recipe_label_to_subject[label_str] = s

        ingredients = labels_of(EX.Ingredient)
        tags = labels_of(EX.Tag)
        return cls(recipes=recipes, ingredients=ingredients, tags=tags,
                   recipe_label_to_subject=recipe_label_to_subject, graph=g)

    def get_recipe_meta(self, label: str) -> Optional[Dict]:
        """Return metadata for a recipe label: id, minutes, n_ingredients, n_steps, nutrition, steps, tags.
        If label not found, return None.
        """
        if not self.graph or not self.recipe_label_to_subject:
            return None
        subj = self.recipe_label_to_subject.get(label)
        if subj is None:
            return None
        g = self.graph

        def lit_to_number(v):
            if v is None:
                return None
            try:
                return int(v)
            except Exception:
                try:
                    return float(v)
                except Exception:
                    return str(v)

        meta: Dict = {}
        meta["id"] = lit_to_number(g.value(subj, EX.id))
        meta["minutes"] = lit_to_number(g.value(subj, EX.minutes))
        meta["n_ingredients"] = lit_to_number(g.value(subj, EX.n_ingredients))
        meta["n_steps"] = lit_to_number(g.value(subj, EX.n_steps))

        # Tags
        tags_list: List[str] = []
        for tag_node in g.objects(subj, EX.hasTag):
            lab = g.value(tag_node, RDFS.label)
            if lab is not None:
                tags_list.append(str(lab))
        meta["tags"] = tags_list

        # Nutrition
        nutrition_node = g.value(subj, EX.hasNutrition)
        nutrition: Dict[str, float] = {}
        if nutrition_node is not None:
            for p, o in g.predicate_objects(nutrition_node):
                # skip rdf:type
                if p == RDF.type:
                    continue
                key = p.split("#")[-1] if "#" in p else str(p)
                nutrition[key] = lit_to_number(o)
        meta["nutrition"] = nutrition

        # Steps: follow ex:hasStep -> rdf:Seq and iterate rdf:_1...rdf:_n
        steps_node = g.value(subj, EX.hasStep)
        steps_list: List[str] = []
        if steps_node is not None:
            # If it's an rdf:Seq, collect ordered members
            members = []
            for p, o in g.predicate_objects(steps_node):
                pname = p.split("#")[-1] if "#" in p else str(p)
                if pname.startswith("_"):
                    try:
                        idx = int(pname.lstrip("_"))
                        members.append((idx, o))
                    except Exception:
                        continue
            members.sort(key=lambda x: x[0])
            for _i, member in members:
                # member is a Step node; get rdfs:comment
                comment = g.value(member, RDFS.comment)
                if comment is not None:
                    steps_list.append(str(comment))
        meta["steps"] = steps_list

        return meta

    def search(self, collection: str, query: str, limit: int = 5, score_cutoff: int = 75) -> List[Tuple[str, float]]:
        """Fuzzy search within one of the indexed lists. Returns (match, score)."""
        items = getattr(self, collection, None)
        if not items or not query:
            return []
        q = query.strip()
        if process and fuzz:
            results = process.extract(q, items, scorer=fuzz.WRatio, limit=limit, score_cutoff=score_cutoff)
            # results: list of (match, score, idx)
            return [(m, float(s)) for (m, s, _i) in results]
        # Fallback exact/substring match if rapidfuzz is missing
        ql = q.lower()
        scored = []
        for it in items:
            itl = it.lower()
            if ql == itl:
                scored.append((it, 100.0))
            elif ql in itl or itl in ql:
                scored.append((it, 85.0))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]


def extract_entities(text: str, nlp=None) -> Dict[str, List[str] | Optional[int]]:
    """Return a slots dict: {ingredient: [..], recipe_name: [..], cooking_time: minutes or None}"""
    slots: Dict[str, List[str] | Optional[int]] = {
        "ingredient": [],
        "recipe_name": [],
        "cooking_time": None,
    }
    if not text:
        return slots

    # Cooking time via regex, independent of spaCy
    minutes = cooking_time_to_minutes(text)
    slots["cooking_time"] = minutes

    # Try spaCy to get candidate noun chunks for ingredients / recipe names
    if nlp is not None:
        doc = nlp(text)
        noun_chunks = [nc.text.strip() for nc in getattr(doc, "noun_chunks", [])]
        # Heuristics: take noun chunks longer than 2 chars as candidates
        cand = [c for c in noun_chunks if len(c) >= 3]
        # Also add quoted spans as candidates (often recipe names)
        cand += re.findall(r"\"([^\"]{3,})\"|'([^']{3,})'", text)
        # flatten quotes tuples
        flat_cand = []
        for t in cand:
            if isinstance(t, tuple):
                flat_cand.extend([x for x in t if x])
            else:
                flat_cand.append(t)
        # Deduplicate while preserving order
        seen = set()
        ordered = []
        for c in flat_cand:
            cl = c.lower()
            if cl not in seen:
                seen.add(cl)
                ordered.append(c)
        # Filter out generic candidates (like the word 'ingredients') that confuse KG matching
        generic_stop = {"ingredients", "ingredientes", "ingredient", "ingrediente", "ingredientes da", "ingredients for", "for"}
        filtered = [o for o in ordered if o.lower().strip() not in generic_stop]
        # Tentatively assign to ingredient or recipe_name later via KG matching
        slots["ingredient"] = ordered  # keep original for ingredient fuzzy matching
        slots["recipe_name"] = filtered.copy()
    else:
        # Fallback: extract words following "com"/"with" as ingredient hints
        m = re.search(r"\b(com|with)\s+([^,.!?]{3,})", text, re.I)
        if m:
            slots["ingredient"] = [m.group(2).strip()]

    return slots


def link_slots_to_kg(slots: Dict[str, List[str] | Optional[int]], kg: KGIndex,
                     ing_limit: int = 3, recipe_limit: int = 2,
                     score_cutoff_ing: int = 75, score_cutoff_recipe: int = 70) -> Dict[str, List[Tuple[str, float]] | Optional[int]]:
    """Link candidate text to KG labels using fuzzy matching. Returns matched items with scores.
    slots keys preserved; cooking_time passed through unchanged.
    """
    out: Dict[str, List[Tuple[str, float]] | Optional[int]] = {
        "ingredient": [],
        "recipe_name": [],
        "cooking_time": slots.get("cooking_time"),
        "recipe_meta": None,
    }

    # Ingredients
    for cand in slots.get("ingredient", []) or []:
        matches = kg.search("ingredients", cand, limit=1, score_cutoff=score_cutoff_ing)
        if matches:
            out["ingredient"].extend(matches)
            if len(out["ingredient"]) >= ing_limit:
                break

    # Recipe names – prefer longer candidates first
    recipe_cands = sorted((slots.get("recipe_name", []) or []), key=lambda s: -len(s))
    for cand in recipe_cands:
        matches = kg.search("recipes", cand, limit=1, score_cutoff=score_cutoff_recipe)
        if matches:
            out["recipe_name"].extend(matches)
            if len(out["recipe_name"]) >= recipe_limit:
                break

    # If we have recipe matches, pick the highest-scoring match (avoid relying on insertion order)
    if out.get("recipe_name"):
        try:
            top_match = max(out["recipe_name"], key=lambda x: x[1])
            top_label = top_match[0]
            meta = kg.get_recipe_meta(top_label)
            out["recipe_meta"] = meta
        except Exception:
            out["recipe_meta"] = None

    return out


def extract_and_link(text: str, ttl_path: str, lang_priority: str = "pt"):
    nlp = build_spacy_pipeline(lang_priority=lang_priority)
    slots = extract_entities(text, nlp)
    kg = KGIndex.from_ttl(ttl_path)
    linked = link_slots_to_kg(slots, kg)
    return linked
