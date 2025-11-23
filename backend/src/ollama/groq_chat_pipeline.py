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
PIPELINE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "../NLP"))
if PIPELINE_DIR not in sys.path:
    sys.path.append(PIPELINE_DIR)

_handle_query = None
_extract_slots_only = None

def _load_pipeline():
    global _handle_query, _extract_slots_only
    if _handle_query is None or _extract_slots_only is None:
        print("Loading pipeline components...")
        try:
            mod = importlib.import_module("pipeline")
            _handle_query = getattr(mod, "handle_query")
            _extract_slots_only = getattr(mod, "extract_slots_only")
            print("Pipeline components loaded successfully")
        except Exception as e:
            print(f"Failed to import pipeline: {e}")
            sys.exit(1)
    return _handle_query, _extract_slots_only

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
    url_display = "https://api.groq.com/v1/chat/completions"
    print(f"POST {url_display} model={model_name}")
    print("=== LLM PROMPT (truncated to 800 chars) ===")
    print(prompt[:800] + ("..." if len(prompt) > 800 else ""))
    print("=== END PROMPT ===")

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
def _brief_result_for_llm(result: Dict[str, Any]) -> str:
    lines = []
    intent = result.get("intent")
    if intent:
        lines.append(f"intent={intent}")
    slots = result.get("slots") or {}
    recipe_names = slots.get("recipe_name") or []
    if recipe_names and isinstance(recipe_names[0], (list, tuple)):
        lines.append(f"slot_recipe_name={recipe_names[0][0]}")
    cooking_time = slots.get("cooking_time")
    if isinstance(cooking_time, int):
        lines.append(f"slot_cooking_time={cooking_time}m")
    recipes = result.get("kg_results") or []
    if recipes:
        for r in recipes:
            name = r.get("recipe_name") or r.get("recipe_uri")
            minutes = r.get("minutes")
            ingredients = r.get("ingredients") or []
            steps = r.get("steps") or []
            tags = r.get("tags") or []
            lines.append(f"Recipe: {name}")
            if minutes:
                lines.append(f"Minutes: {minutes}")
            if tags:
                lines.append(f"Tags: {', '.join(tags)}")
            if ingredients:
                lines.append("Ingredients: " + ", ".join(ingredients))
            if steps:
                lines.append("Steps:")
                for i, s in enumerate(steps, start=1):
                    lines.append(f"{i:02d}. {s}")
    return "\n".join(lines)

def _summarize_with_llm(user_query: str, result: Dict[str, Any]) -> str:
    brief = _brief_result_for_llm(result)
    prompt = (
        "You are a bilingual PT/EN assistant.\n"
        "ONLY use the following structured recipe output and the user query. "
        "Do NOT invent anything. Do NOT add URLs, extra steps, or external references. "
        "Produce a concise summary in natural language.\n\n"
        f"User query: {user_query}\n\n"
        f"{brief}\n\n"
        "Answer:"
    )
    return run_groq(prompt)

# -------------------------
# Pipeline-style printing (exactly like pipeline.py before running handle_query)
# -------------------------
def _print_query_info_and_slots(text: str, intent: str, conf: float, slots: Dict[str, Any]):
    print("\n========== QUERY INFO ==========")
    print(f"Intent: {intent} (confidence={conf:.2f})")
    print(f"Query: {text}")

    if slots:
        if any(k in slots for k in ("original_query", "translated_query", "detected_language")):
            print("\n=== Normalization & Translation ===")
            if "original_query" in slots:
                print(f"Original: {slots['original_query']}")
            else:
                print(f"Original: {text}")
            if "detected_language" in slots:
                print(f"Detected language: {slots['detected_language']}")
            if "translated_query" in slots:
                print(f"Translated (for intent/NER): {slots['translated_query']}")

        print("\nDetected slots:")
        for k, v in slots.items():
            if k in {"detected_language", "original_query", "translated_query"}:
                continue
            if k == "cooking_time" and isinstance(v, int):
                print(f"  - cooking_time: {v} minutes")
                continue
            if isinstance(v, list):
                rendered = []
                for item in v:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        rendered.append(f"{item[0]} ({item[1]:.1f})")
                    elif isinstance(item, (list, tuple)) and len(item) == 1:
                        rendered.append(str(item[0]))
                    else:
                        rendered.append(str(item))
                print(f"  - {k}: {', '.join(rendered)}")
            else:
                print(f"  - {k}: {v}")

    print("\n========== RESULTS (Sequential Execution) ==========\n")
    print("(Below, each SPARQL query is executed and printed one by one.)\n")

# -------------------------
# Query processing (pipeline.py style + LLM append)
# -------------------------
def _process_query(user_query: str):
    user_query = user_query.strip()
    if not user_query:
        return
    if user_query.startswith("/model"):
        print(f"Current model: {_current_model or DEFAULT_MODEL}")
        return
    if user_query.startswith("/env"):
        keys = [
            "groq_key","GROQ_KEY","groq_model","GROQ_MODEL","temperature",
            "max_completion_tokens","top_p","reasoning_effort","stream","stop","GROQ_DEBUG"
        ]
        for k in keys:
            print(f"{k}={os.environ.get(k,'<unset>')}")
        print(f"Resolved DEFAULT_MODEL={DEFAULT_MODEL}")
        print(f"DEBUG={DEBUG} TEMP={_TEMP} MAX_TOK={_MAX_TOK} TOP_P={_TOP_P} STREAM={_STREAM} REASONING={_REASONING}")
        return

    handle_query_fn, extract_slots_fn = _load_pipeline()

    # 1) Extract intent & slots (no SPARQL yet)
    intent, conf, slots = extract_slots_fn(user_query, top_k=1)

    # 2) Print identical preamble
    _print_query_info_and_slots(user_query, intent, conf, slots)

    # 3) Run full pipeline (prints SPARQL sections & recipes)
    result = handle_query_fn(user_query, intent_top_k=1, sparql_top_k=5)

    # 4) Build brief + call Groq (append after KG output)
    summary = _summarize_with_llm(user_query, result)
    print("POST https://api.groq.com/v1/chat/completions model=" + (_current_model or DEFAULT_MODEL))
    # Reconstruct prompt exactly like Ollama style (already truncated logic inside api_chat)
    brief = _brief_result_for_llm(result)
    prompt_display = (
        "You are a bilingual PT/EN assistant.\n"
        "ONLY use the following structured recipe output and the user query. Do NOT invent anything. "
        "Do NOT add URLs, extra steps, or external references. Produce a concise summary in natural language.\n\n"
        f"User query: {user_query}\n\n{brief}\n\nAnswer:"
    )
    print("=== LLM PROMPT (truncated to 800 chars) ===")
    print(prompt_display[:800] + ("..." if len(prompt_display) > 800 else ""))
    print("=== END PROMPT ===")
    # We already executed the request inside _summarize_with_llm (run_groq).
    if summary:
        print("\n=== LLM SUMMARY ===")
        print(summary)
    else:
        print("\n=== LLM SUMMARY ===")
        print("(LLM empty response)")
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