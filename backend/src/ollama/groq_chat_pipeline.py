import os
import sys
import json
import textwrap
from typing import Any, Dict
from contextlib import redirect_stdout, redirect_stderr
import importlib

# -------------------------
# Load groq.env optionally (same folder)
# -------------------------
try:
    from dotenv import load_dotenv
    dotenv_path = os.path.join(os.path.dirname(__file__), "groq.env")
    if os.path.exists(dotenv_path):
        print(f"Loading environment variables from {dotenv_path}")
        load_dotenv(dotenv_path)
except Exception:
    pass

# -------------------------
# Pipeline import (lazy)
# -------------------------
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

mod = importlib.import_module("NLP.pipeline")

_handle_query = None
_extract_slots_only = None

def _load_pipeline():
    global _handle_query, _extract_slots_only
    if _handle_query is None or _extract_slots_only is None:
        print("Loading pipeline components...")
        try:
            mod = importlib.import_module("NLP.pipeline")
            _handle_query = getattr(mod, "handle_query")
            _extract_slots_only = getattr(mod, "extract_slots_only")
            print("Pipeline components loaded successfully")
        except Exception as e:
            print(f"Failed to import pipeline: {e}")
            sys.exit(1)
    return _handle_query, _extract_slots_only

from RAG.description_index import similarity_search


# -------------------------
# Config
# -------------------------
_raw_debug = os.environ.get("GROQ_DEBUG", "0").strip().strip('"').strip("'")
try:
    DEBUG = bool(int(_raw_debug))
except ValueError:
    DEBUG = _raw_debug.lower() in {"true", "yes", "on", "1"}

GROQ_API_KEY = (os.environ.get("groq_key") or os.environ.get("GROQ_KEY") or "").strip().strip('"').strip("'")
DEFAULT_MODEL = (os.environ.get("groq_model") or os.environ.get("GROQ_MODEL") or "openai/gpt-oss-120b").strip().strip('"').strip("'")
_TEMP = os.environ.get("temperature") or os.environ.get("GROQ_TEMPERATURE")
_MAX_TOK = os.environ.get("max_completion_tokens") or os.environ.get("GROQ_MAX_COMPLETION_TOKENS")
_TOP_P = os.environ.get("top_p") or os.environ.get("GROQ_TOP_P")
_REASONING = os.environ.get("reasoning_effort") or os.environ.get("GROQ_REASONING_EFFORT")
_STREAM_FLAG = os.environ.get("stream") or os.environ.get("GROQ_STREAM")
_STOP = os.environ.get("stop") or os.environ.get("GROQ_STOP")

try:
    _TEMP = float(_TEMP) if _TEMP is not None else None
except Exception:
    _TEMP = None
try:
    _MAX_TOK = int(_MAX_TOK) if _MAX_TOK is not None else None
except Exception:
    _MAX_TOK = None
try:
    _TOP_P = float(_TOP_P) if _TOP_P is not None else None
except Exception:
    _TOP_P = None

_STREAM = False
if isinstance(_STREAM_FLAG, str):
    _STREAM = _STREAM_FLAG.lower() in {"true", "1", "yes", "on"}

# -------------------------
# Groq client (lazy)
# -------------------------
_groq_client = None
_current_model = None

def _ensure_client():
    global _groq_client
    if _groq_client is None:
        if not GROQ_API_KEY:
            print("Missing GROQ_API_KEY (groq_key) in environment.")
            return None
        try:
            from groq import Groq
            _groq_client = Groq(api_key=GROQ_API_KEY)
        except ModuleNotFoundError:
            print("Groq package not installed. Run: pip install groq")
            return None
        except Exception as e:
            print(f"Failed to init Groq client: {e}")
            return None
    return _groq_client

def _list_models():
    client = _ensure_client()
    if not client:
        return []
    try:
        data = client.models.list()
        return [m.id for m in getattr(data, "data", [])]
    except Exception as e:
        print(f"[Model list error] {e}")
        return []

# -------------------------
# LLM API wrapper
# -------------------------
def api_chat(prompt: str, model_name: str) -> str:
    client = _ensure_client()
    if client is None:
        return ""
    params: Dict[str, Any] = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    if _TEMP is not None:
        params["temperature"] = _TEMP
    if _MAX_TOK is not None:
        # map to correct field name
        params["max_tokens"] = _MAX_TOK
    if _TOP_P is not None:
        params["top_p"] = _TOP_P
    if _STOP and _STOP.lower() != "none":
        params["stop"] = _STOP

    try:
        completion = client.chat.completions.create(**params)
        choices = getattr(completion, "choices", [])
        if not choices:
            return ""
        return (choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[LLM EXCEPTION] {e}")
        return ""

_current_model = None

def run_groq(prompt: str) -> str:
    global _current_model
    if _current_model is None:
        _current_model = DEFAULT_MODEL
    resp = api_chat(prompt, _current_model)
    if resp:
        return resp
    # Fallback: list models once
    models = _list_models()
    if models and _current_model not in models:
        print(f"Requested model '{_current_model}' not available; using '{models[0]}' instead")
        _current_model = models[0]
        resp = api_chat(prompt, _current_model)
    return resp

# -------------------------
# Brief construction (same)
# -------------------------
def _brief_result_for_llm(result: Dict[str, Any], user_query: str) -> str:
    """
    Build a concise structured block for the LLM that now includes:
    - original query
    - detected language
    - translated query
    - intent + confidence
    - slot summaries
    - recipe structured data
    """
    lines = []
    # Core query info
    orig = result.get("original_query") or user_query
    detected_lang = (result.get("detected_language")
                     or (result.get("slots") or {}).get("detected_language"))
    translated = (result.get("translated_query")
                  or (result.get("slots") or {}).get("translated_query"))
    intent = result.get("intent")
    intent_conf = result.get("intent_confidence") or result.get("intent_score") \
                  or (result.get("intent_scores") or [None])[0]

    lines.append(f"original_query={orig}")
    if detected_lang:
        lines.append(f"detected_language={detected_lang}")
    if translated and translated != orig:
        lines.append(f"translated_query={translated}")
    if intent:
        if isinstance(intent_conf, (int, float)):
            lines.append(f"intent={intent} confidence={intent_conf:.2f}")
        else:
            lines.append(f"intent={intent}")

    # Slots
    slots = result.get("slots") or {}
    for k, v in slots.items():
        if k in {"original_query","translated_query","detected_language"}:
            continue
        if k == "cooking_time" and isinstance(v, int):
            lines.append(f"slot_cooking_time={v}m")
            continue
        if isinstance(v, list):
            # show top 3 items if score pairs
            rendered = []
            for item in v[:3]:
                if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[1], (int,float)):
                    rendered.append(f"{item[0]}({item[1]:.2f})")
                else:
                    rendered.append(str(item))
            lines.append(f"slot_{k}=" + ", ".join(rendered))
        else:
            lines.append(f"slot_{k}={v}")

    # Recipes
    recipes = result.get("kg_results") or []
    for r in recipes:
        name = r.get("recipe_name") or r.get("recipe_uri")
        minutes = r.get("minutes")
        tags = r.get("tags") or []
        ing = r.get("ingredients") or []
        lines.append(f"Recipe: {name}")
        if minutes is not None:
            lines.append(f"Minutes: {minutes}")
        if tags:
            lines.append(f"Tags: {', '.join(tags[:12])}")
        if ing:
            lines.append("Ingredients: " + ", ".join(ing[:15]))
        steps = r.get("steps") or []
        if steps:
            lines.append("Steps:")
            for i, s in enumerate(steps[:8], start=1):
                lines.append(f"{i:02d}. {s}")

    return "\n".join(lines)


def _summarize_with_llm(user_query: str, result: Dict[str, Any]) -> tuple[str, str]:
    """
    Returns (llm_response, prompt_used) with heuristic filtering of description snippets.
    """
    brief = _brief_result_for_llm(result, user_query)

    # Heuristic filtering of description chunks
    raw_chunks = result.get("similar_description_chunks") or []
    import re
    user_tokens = set(re.findall(r"\w+", user_query.lower()))
    filtered = []
    for c in raw_chunks:
        text = (c.get("text") or "").strip()
        score = float(c.get("score") or 0.0)
        if not text:
            continue
        # basic length / token criteria
        tokens = re.findall(r"\w+", text.lower())
        if len(tokens) < 4:
            continue
        overlap = len(user_tokens & set(tokens))
        # keep if score is reasonably high OR lexical overlap OR contains domain words (recipe, dish, ingredient)
        domain_ok = any(w in text.lower() for w in ("recipe","dish","ingred","tradicional","portuguese","peanut","bacalhau","cod"))
        if score >= 0.32 or overlap >= 1 or domain_ok:
            filtered.append({"text": text, "score": score})
        if len(filtered) >= 5:
            break

    desc_lines = ""
    if filtered:
        lines = []
        for i, c in enumerate(filtered, start=1):
            t = c["text"]
            if len(t) > 240:
                t = t[:237].rstrip() + "..."
            lines.append(f"{i}. {t}")
        desc_lines = "Description snippets (semantic matches):\n" + "\n".join(lines) + "\n\n"

    prompt = (
        "You are a bilingual PT/EN assistant.\n"
        "Use ONLY: (a) the user query, (b) the description snippets, (c) the structured recipe data.\n"
        "Tasks:\n"
        "1. Begin with 1–2 fluent sentences (PT first then EN) integrating relevant description snippets (do NOT invent).\n"
        "2. Provide a concise bilingual table summarizing the retrieved recipes (PT first then EN for columns or entries).\n"
        "3. End with a short closing line.\n"
        "Rules: Do NOT add URLs, external sources, or steps not present. Do NOT fabricate ingredients or times.\n\n"
        f"User query: {user_query}\n\n"
        f"{desc_lines}"
        "Structured recipe data:\n"
        f"{brief}\n\n"
        "Answer:"
    )

    response = run_groq(prompt)
    return response, prompt


def api_chat(prompt: str, model_name: str) -> str:
    """
    Modified: remove internal prompt printing to avoid duplication.
    Outer layer (_process_query) handles printing.
    """
    client = _ensure_client()
    if client is None:
        return ""
    params: Dict[str, Any] = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    if _TEMP is not None:
        params["temperature"] = _TEMP
    if _MAX_TOK is not None:
        params["max_tokens"] = _MAX_TOK
    if _TOP_P is not None:
        params["top_p"] = _TOP_P
    if _STOP and _STOP.lower() != "none":
        params["stop"] = _STOP
    try:
        completion = client.chat.completions.create(**params)
        choices = getattr(completion, "choices", [])
        if not choices:
            return ""
        return (choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[LLM EXCEPTION] {e}")
        return ""


def _process_query(user_query: str):
    user_query = user_query.strip()
    if not user_query:
        return
    handle_query_fn, _ = _load_pipeline()
    result = handle_query_fn(user_query, intent_top_k=1, sparql_top_k=5)

    # Print query info (restored)
    intent = result.get("intent") or "(unknown)"
    intent_conf = result.get("intent_confidence") or result.get("intent_score") \
                  or (result.get("intent_scores") or [None])[0]
    slots = result.get("slots") or {}
    print("\n========== QUERY INFO ==========")
    if isinstance(intent_conf, (int,float)):
        print(f"Intent: {intent} (confidence={intent_conf:.2f})")
    else:
        print(f"Intent: {intent}")
    print(f"Query: {user_query}")

    if slots:
        print("\n=== Normalization & Translation ===")
        orig = slots.get("original_query") or user_query
        print(f"Original: {orig}")
        if "detected_language" in slots:
            print(f"Detected language: {slots['detected_language']}")
        if "translated_query" in slots and slots["translated_query"] != orig:
            print(f"Translated (for intent/NER): {slots['translated_query']}")

        print("\nDetected slots:")
        for k, v in slots.items():
            if k in {"original_query","translated_query","detected_language"}:
                continue
            if k == "cooking_time" and isinstance(v, int):
                print(f"  - cooking_time: {v} minutes")
                continue
            if isinstance(v, list):
                rendered = []
                for item in v:
                    if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[1], (int,float)):
                        rendered.append(f"{item[0]} ({item[1]:.2f})")
                    else:
                        rendered.append(str(item))
                print(f"  - {k}: {', '.join(rendered)}")
            else:
                print(f"  - {k}: {v}")

    print("\n========== RESULTS (Sequential Execution) ==========\n(Below, each SPARQL query is executed and printed one by one.)\n")

    # Similarity
    try:
        from RAG.description_index import similarity_search
        result["similar_description_chunks"] = similarity_search(user_query, top_k=5) or []
    except Exception as e:
        result["similar_description_chunks"] = []
        print(f"(similarity_search failed: {e})")

    sim_snips = result["similar_description_chunks"]
    print(f"=== SIMILARITY SNIPPETS (count={len(sim_snips)}) ===")
    if sim_snips:
        for i, c in enumerate(sim_snips, start=1):
            txt = (c.get("text","") or "").strip()
            if len(txt) > 220:
                txt = txt[:217].rstrip() + "..."
            score = c.get("score")
            if isinstance(score,(int,float)):
                print(f"{i}. ({score:.3f}) {txt}")
            else:
                print(f"{i}. {txt}")
    else:
        print("(none)")
    print("=== END SIMILARITY SNIPPETS ===\n")

    summary, used_prompt = _summarize_with_llm(user_query, result)

    # Single prompt print
    print(f"POST https://api.groq.com/v1/chat/completions model=" + (_current_model or DEFAULT_MODEL))
    print("=== LLM PROMPT (truncated to 800 chars) ===")
    print(used_prompt[:800] + ("..." if len(used_prompt) > 800 else ""))
    print("=== END PROMPT ===")

    print("\n=== LLM SUMMARY ===")
    print(summary if summary else "(LLM empty response)")
    print("\nTurn complete.\n")

# -------------------------
# CLI / interactive
# -------------------------
def main():
    print("==============================================")
    print("Interactive Recipe Chatbot (Pipeline + Groq)")
    print("Type a recipe-related query in PT or EN.")
    print("Examples: receitas com manteiga de amendoim | quick vegan pasta")
    print("Commands: /exit to quit")
    print("==============================================")
    if len(sys.argv) > 1:
        _process_query(" ".join(sys.argv[1:]))
        return
    if not sys.stdin.isatty():
        print("No interactive TTY. Provide a query as CLI argument.")
        sys.exit(1)
    try:
        while True:
            q = input("you> ").strip()
            if not q or q.lower() in {"/exit","exit","quit"}:
                break
            _process_query(q)
    except (KeyboardInterrupt, EOFError):
        pass
    print("Goodbye!")

if __name__ == "__main__":
    main()