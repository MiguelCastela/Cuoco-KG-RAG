import os
import sys
from typing import Dict, Any, Optional

# Robust imports: module or script
try:
    from infer_intent import predict_intent
    from entity_extraction import build_spacy_pipeline, KGIndex, extract_and_link
    import sparql_queries  # <- novo: nosso script com queries SPARQL
except Exception:
    THIS_DIR = os.path.dirname(__file__)
    SRC_ROOT = os.path.normpath(os.path.join(THIS_DIR, "..", ".."))

# Resolve TTL relative to this file
BASE_DIR = os.path.dirname(__file__)
DEFAULT_TTL = os.path.normpath(os.path.join(BASE_DIR, "../../data/curated/recipes_graph_cleaned.ttl"))
TTL_PATH = os.environ.get("RECIPES_TTL_PATH", DEFAULT_TTL)

# Preload resources once
NLP = build_spacy_pipeline(lang_priority="pt")
KG = KGIndex.from_ttl(TTL_PATH)

# Intents that need downstream entity extraction
INTENTS_NEEDING_EXTRACTION = {
    "find_recipe",
    "get_prep_time",
    "retrieve_ingredients",
    "list_by_ingredient",
    "list_by_tag",
    "list_by_time",
}


def _slot_top_label(slots: Dict[str, Any], key: str) -> Optional[str]:
    v = slots.get(key)
    if not v:
        return None
    # List of (label, score)
    if isinstance(v, list) and v:
        head = v[0]
        if isinstance(head, (list, tuple)) and head:
            return str(head[0])  # take label
        return str(head)        # already a str
    # Single (label, score)
    if isinstance(v, (list, tuple)) and v and isinstance(v[0], str):
        return v[0]
    # Already a string
    if isinstance(v, str):
        return v
    return None


def handle_query(text: str, top_k: int = 1) -> Dict[str, Any]:
    # Predict intent
    preds = predict_intent(text, top_k=top_k)
    top_intent, conf = preds[0] if preds else (None, 0.0)

    result: Dict[str, Any] = {"intent": top_intent, "confidence": conf, "text": text}

    slots = {}
    if top_intent in INTENTS_NEEDING_EXTRACTION:
        # Extract entities
        slots = extract_and_link(
            text,
            intent=top_intent,
            nlp=NLP,
            kg=KG
        )
        result["slots"] = slots

        # SPARQL queries based on intent
        if top_intent == "list_by_ingredient":
            ingredient = _slot_top_label(slots, "ingredient")
            if ingredient:
                result["kg_results"] = sparql_queries.query_list_by_ingredient(KG.graph, ingredient, top_k=2)

        elif top_intent == "list_by_tag":
            tag = _slot_top_label(slots, "tag")
            if tag:
                result["kg_results"] = sparql_queries.query_list_by_tag(KG.graph, tag)

        elif top_intent == "find_recipe":
            recipe_name = _slot_top_label(slots, "recipe_name")
            if recipe_name:
                result["kg_results"] = sparql_queries.query_find_recipe(KG.graph, recipe_name)

        elif top_intent == "retrieve_ingredients":
            recipe_name = _slot_top_label(slots, "recipe_name")
            if recipe_name:
                result["kg_results"] = sparql_queries.query_retrieve_ingredients(KG.graph, recipe_name)

        elif top_intent == "get_prep_time":
            recipe_name = _slot_top_label(slots, "recipe_name")
            if recipe_name:
                result["kg_results"] = sparql_queries.query_get_prep_time(KG.graph, recipe_name, top_k=3)

        elif top_intent == "list_by_time" and slots.get("cooking_time"):
            minutes = slots["cooking_time"]
            result["kg_results"] = sparql_queries.query_by_cooking_time(KG.graph, minutes, top_k=2)

    return result


if __name__ == "__main__":
    # Use CLI arg if provided, else default example
    text = "Quais são os ingredientes da francesinha?"
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    output = handle_query(text)
    print(output)
