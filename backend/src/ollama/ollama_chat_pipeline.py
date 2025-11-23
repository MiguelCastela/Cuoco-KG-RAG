#!/usr/bin/env python3
"""
ollama_chat_pipeline.py - Ollama HTTP-only client (compatible with Ollama 0.6.x)

This version:
- Does NOT rewrite the user query.
- Uses pipeline.py output as context for the LLM summary.
- Removes emojis for cleaner logs.
"""

import os
import sys
import json
import textwrap
import requests
from typing import Any, Dict
from contextlib import redirect_stdout, redirect_stderr
import importlib

# -------------------------
# Load .env optionally
# -------------------------
try:
    from dotenv import load_dotenv
    dotenv_path = os.path.join(os.path.dirname(__file__), "ollama.env")
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

def _load_pipeline_handle_query():
    global _handle_query
    if _handle_query is None:
        # Keep the same messages when components actually load
        print("Loading pipeline components...")
        try:
            mod = importlib.import_module("pipeline")
            _handle_query = getattr(mod, "handle_query")
            print("Pipeline components loaded successfully")
        except Exception as e:
            print(f"Failed to import pipeline: {e}")
            sys.exit(1)
    return _handle_query

# -------------------------
# Config
# -------------------------
_raw_debug = os.environ.get("OLLAMA_DEBUG", "0").strip().strip('"').strip("'")
try:
    DEBUG = bool(int(_raw_debug))
except ValueError:
    DEBUG = _raw_debug.lower() in {"true", "yes", "on", "1"}

OLLAMA_HOST = (os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = (os.environ.get("OLLAMA_MODEL") or os.environ.get("ollama_model") or "llama3:8b-instruct-q4_0").strip().strip('"').strip("'")
_TEMP = os.environ.get("OLLAMA_TEMPERATURE") or os.environ.get("ollama_temperature")
_MAX_TOK = os.environ.get("OLLAMA_MAX_TOKENS") or os.environ.get("ollama_max_tokens")

try:
    _TEMP = float(_TEMP) if _TEMP is not None else None
except Exception:
    _TEMP = None
try:
    _MAX_TOK = int(_MAX_TOK) if _MAX_TOK is not None else None  
except Exception:
    _MAX_TOK = None

# -------------------------
# Ollama helpers
# -------------------------
def list_models() -> list:
    url = f"{OLLAMA_HOST}/api/tags"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict) and "models" in data:
                return [m.get("name") for m in data["models"] if isinstance(m, dict) and "name" in m]
            return []
    except Exception as e:
        print(f"Error listing models: {e}")
    return []

def ensure_model_available(desired_model: str) -> str:
    models = list_models()
    if not models:
        print("No models reported by Ollama server; using requested model anyway")
        return desired_model
    print(f"Ollama server reports models: {models}")
    if desired_model in models:
        return desired_model
    print(f"Requested model '{desired_model}' not available; using '{models[0]}' instead")
    return models[0]

def api_generate(prompt: str, model_name: str) -> str:
    url = f"{OLLAMA_HOST}/api/generate"
    payload: Dict[str, Any] = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
    }
    options = {}
    if _TEMP is not None:
        options["temperature"] = _TEMP
    if _MAX_TOK is not None:
        options["num_predict"] = _MAX_TOK
    if options:
        payload["options"] = options

    # Always show POST line
    print(f"POST {url} model={model_name}")
    if DEBUG:
        print("=== LLM PROMPT (truncated to 800 chars) ===")
        print(prompt[:800] + ("..." if len(prompt) > 800 else ""))
        print("=== END PROMPT ===")

    try:
        r = requests.post(url, json=payload, timeout=45)
        if r.status_code != 200:
            print(f"[LLM ERROR] status={r.status_code} body={r.text[:400]}")
            return ""
        data = r.json()
        txt = data.get("response") or data.get("text") or ""
        if isinstance(txt, list):
            txt = "".join(txt)
        return (txt or "").strip()
    except Exception as e:
        print(f"[LLM EXCEPTION] {e}")
        return ""

# Defer model resolution; use .env directly, fallback later
_current_model = None

def run_ollama(prompt: str) -> str:
    global _current_model
    # First try the model from .env directly (no /api/tags)
    if _current_model is None:
        _current_model = DEFAULT_MODEL

    resp = api_generate(prompt, _current_model)
    if resp:
        return resp

    # Fallback: resolve against server models once if the direct try returned empty
    resolved = ensure_model_available(DEFAULT_MODEL)
    if resolved != _current_model:
        # ensure_model_available prints the same lines as before (models list and fallback notice)
        _current_model = resolved
        resp = api_generate(prompt, _current_model)
    return resp

# -------------------------
# Prepare brief for LLM summary
# -------------------------
def _brief_result_for_llm(result: Dict[str, Any]) -> str:
    """
    Produce a fully explicit structured summary of the pipeline output.
    This will be used as context for the LLM, avoiding hallucinations.
    """
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
        "Produce a concise summary in 2-5 lines, in natural language.\n\n"
        f"User query: {user_query}\n\n"
        f"{brief}\n\n"
        "Answer:"
    )
    return run_ollama(prompt)

# -------------------------
# Remove unused imports from previous subprocess approach
# (keep requests, etc.)
# Delete: import subprocess, re
# Add helper to format output like pipeline.py

def _format_and_print(user_query: str, result: Dict[str, Any]):
    intent = result.get("intent")
    conf = result.get("confidence")
    slots = result.get("slots") or {}
    original = slots.get("original_query") or user_query
    detected_lang = slots.get("detected_language")
    translated = slots.get("translated_query")
    ingredients_slot = slots.get("ingredient") or []
    recipe_name_slot = slots.get("recipe_name") or []
    tag_slot = slots.get("tag") or []
    cooking_time = slots.get("cooking_time")
    result_basis = result.get("result_basis")

    print("\n========== QUERY INFO ==========")
    if intent:
        if conf is not None:
            print(f"Intent: {intent} (confidence={conf:.2f})")
        else:
            print(f"Intent: {intent}")
    print(f"Query: {original}")

    print("\n=== Normalization & Translation ===")
    print(f"Original: {original}")
    if detected_lang:
        print(f"Detected language: {detected_lang}")
    if translated:
        print(f"Translated (for intent/NER): {translated}")

    print("\nDetected slots:")
    if ingredients_slot:
        ing_line = ", ".join(
            f"{i[0]} ({i[1]:.1f})" if isinstance(i, (list, tuple)) and len(i) >= 2 else str(i)
            for i in ingredients_slot
        )
        print(f"  - ingredient: {ing_line}")
    else:
        print("  - ingredient:")
    if recipe_name_slot:
        rn_line = ", ".join(
            f"{r[0]} ({r[1]:.1f})" if isinstance(r, (list, tuple)) and len(r) >= 2 else str(r)
            for r in recipe_name_slot
        )
        print(f"  - recipe_name: {rn_line}")
    else:
        print("  - recipe_name:")
    if tag_slot:
        tag_line = ", ".join(
            f"{t[0]} ({t[1]:.1f})" if isinstance(t, (list, tuple)) and len(t) >= 2 else str(t)
            for t in tag_slot
        )
        print(f"  - tag: {tag_line}")
    else:
        print("  - tag:")
    if cooking_time is not None:
        print(f"  - cooking_time: {cooking_time} minutes")
    else:
        print("  - cooking_time:")

    if result_basis:
        print(f"\n[Result basis] {result_basis}")

    print("\n========== RESULTS ==========\n")
    recipes = result.get("kg_results") or []

    if not ingredients_slot:
        # No ingredient grouping → list all recipes (pipeline.py style)
        if not recipes:
            print("✘ Found 0 recipes.")
            return
        print(f"✔ Found {len(recipes)} recipes:")
        for r in recipes:
            name = r.get("recipe_name", "UNKNOWN")
            uri = r.get("recipe_uri", "")
            minutes = r.get("minutes")
            steps = r.get("steps") or []
            tags = r.get("tags") or []
            ings = r.get("ingredients") or []
            nutrition = r.get("nutrition") or {}
            print(f" • {name}")
            if uri:
                print(f"   URI: {uri}")
            if minutes is not None:
                print(f"   Minutes: {minutes}")
            print(f"   #Steps: {len(steps)}")
            if tags:
                print(f"   Tags: {', '.join(tags)}")
            if ings:
                print(f"   Ingredients ({len(ings)}): {', '.join(ings)}")
            if nutrition:
                nut_line = ", ".join(f"{k}={v}" for k, v in nutrition.items())
                print(f"   Nutrition: {nut_line}")
            if steps:
                print("   Steps:")
                for i, s in enumerate(steps, start=1):
                    print(f"   {i:02d}. {s}")
        return

    # Original grouping by ingredient candidates
    for cand in ingredients_slot:
        cand_name = cand[0] if isinstance(cand, (list, tuple)) else str(cand)
        print(f"---- Searching recipes with ingredient: {cand_name} ----")
        matched = [
            r for r in recipes
            if any(cand_name.lower() == ing.lower() for ing in (r.get("ingredients") or []))
        ]
        if not matched:
            print("   ✘ Found 0 recipes.\n")
            continue
        print(f"   ✔ Found {len(matched)} recipes:")
        for r in matched:
            name = r.get("recipe_name", "UNKNOWN")
            uri = r.get("recipe_uri", "")
            minutes = r.get("minutes")
            steps = r.get("steps") or []
            tags = r.get("tags") or []
            ings = r.get("ingredients") or []
            nutrition = r.get("nutrition") or {}
            print(f"    • {name}")
            if uri:
                print(f"      URI: {uri}")
            if minutes is not None:
                print(f"      Minutes: {minutes}")
            print(f"      #Steps: {len(steps)}")
            if tags:
                print(f"      Tags: {', '.join(tags)}")
            if ings:
                print(f"      Ingredients ({len(ings)}): {', '.join(ings)}")
            if nutrition:
                nut_line = ", ".join(f"{k}={v}" for k, v in nutrition.items())
                print(f"      Nutrition: {nut_line}")
            if steps:
                print("      Steps:")
                for i, s in enumerate(steps, start=1):
                    print(f"      {i:02d}. {s}")
        print()

def _process_query(user_query: str):
    user_query = user_query.strip()
    if not user_query:
        return
    if user_query.startswith("/model"):
        print(f"Current model: {_current_model}")
        return
    # Silence pipeline internals and lazy-load on first use
    try:
        with open(os.devnull, "w") as devnull, redirect_stdout(devnull), redirect_stderr(devnull):
            handle_query_fn = _load_pipeline_handle_query()
            result = handle_query_fn(user_query, intent_top_k=1, sparql_top_k=5)
    except Exception as e:
        print(f"Pipeline error: {e}")
        return

    _format_and_print(user_query, result)

    summary = _summarize_with_llm(user_query, result)
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
    print("Interactive Recipe Chatbot (Pipeline + Ollama)")
    print("Type a recipe-related query in PT or EN.")
    print("Examples: receitas com manteiga de amendoim | quick vegan pasta")
    print("Commands: /exit to quit")
    print("==============================================")
    # If launched with CLI args, treat as single turn then exit.
    if len(sys.argv) > 1:
        _process_query(" ".join(sys.argv[1:]))
        return
    if not sys.stdin.isatty():
        print("No interactive TTY. Provide a query as CLI argument.")
        sys.exit(1)
    # Chat loop
    try:
        while True:
            q = input("you> ").strip()
            if not q or q.lower() in {"/exit", "exit", "quit"}:
                break
            _process_query(q)
    except (KeyboardInterrupt, EOFError):
        pass
    print("Goodbye!")

if __name__ == "__main__":
    main()
