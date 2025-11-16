import os
import sys
from typing import Dict, Any

# Robust imports: module or script
try:
    from infer_intent import predict_intent
    from entity_extraction import build_spacy_pipeline, KGIndex, extract_and_link
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


def handle_query(text: str, top_k: int = 1) -> Dict[str, Any]:
    preds = predict_intent(text, top_k=top_k)
    top_intent, conf = preds[0] if preds else (None, 0.0)

    result: Dict[str, Any] = {"intent": top_intent, "confidence": conf, "text": text}

    if top_intent in INTENTS_NEEDING_EXTRACTION:
        slots = extract_and_link(
            text,
            intent=top_intent,
            nlp=NLP,
            kg=KG
        )
        result["slots"] = slots

    return result


if __name__ == "__main__":
    # Use CLI arg if provided, else default example
    text = "Quais são os ingredientes da francesinha?"
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    print(handle_query(text))