import os, csv, json
from typing import List, Dict, Any
from functools import lru_cache

DATA_CSV = os.path.normpath(os.path.join(os.path.dirname(__file__), "../../data/curated/filtered_pt_en.csv"))
INDEX_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "../../data/vector_index"))
os.makedirs(INDEX_DIR, exist_ok=True)

META_PATH = os.path.join(INDEX_DIR, "desc_meta.json")
EMB_PATH = os.path.join(INDEX_DIR, "embeddings.npy")
FAISS_PATH = os.path.join(INDEX_DIR, "faiss.index")

MODEL_NAME = os.environ.get("DESC_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

def _read_rows(csv_path: str) -> List[Dict[str, str]]:
    out = []
    if not os.path.exists(csv_path):
        return out
    with open(csv_path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rid = (row.get("id") or "").strip()
            name = (row.get("name") or "").strip()
            desc = (row.get("description") or "").strip()
            if rid and name and desc:
                out.append({"id": rid, "name": name, "description": desc})
    return out

def _chunk(desc: str, max_len: int = 240) -> List[str]:
    parts = []
    cur = []
    for seg in desc.replace("\n", " ").split("."):
        seg = seg.strip()
        if not seg:
            continue
        if sum(len(x) for x in cur) + len(seg) + 1 <= max_len:
            cur.append(seg)
        else:
            if cur:
                parts.append(". ".join(cur) + ".")
            cur = [seg]
    if cur:
        parts.append(". ".join(cur) + ".")
    return parts or [desc]

def build_index(csv_path: str = DATA_CSV):
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
        import faiss
    except Exception:
        print("Install: pip install sentence-transformers faiss-cpu")
        return
    rows = _read_rows(csv_path)
    if not rows:
        print("No rows; abort.")
        return
    chunks = []
    for r in rows:
        for i, ch in enumerate(_chunk(r["description"])):
            chunks.append({"id": r["id"], "name": r["name"], "chunk_id": f"{r['id']}::c{i}", "text": ch})
    texts = [c["text"] for c in chunks]
    model = SentenceTransformer(MODEL_NAME)
    emb = model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)
    import numpy as np
    np.save(EMB_PATH, emb.astype("float32"))
    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb.astype("float32"))
    faiss.write_index(index, FAISS_PATH)
    meta = {"model": MODEL_NAME, "source_csv": os.path.abspath(csv_path), "n_chunks": len(chunks)}
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump({"records": chunks, "meta": meta}, f, ensure_ascii=False)
    print("Index built:", meta)

@lru_cache(maxsize=1)
def _load_meta():
    if not os.path.exists(META_PATH):
        return {}
    with open(META_PATH, encoding="utf-8") as f:
        return json.load(f)

@lru_cache(maxsize=1)
def _load_index():
    meta = _load_meta()
    if not meta:
        return None
    try:
        import numpy as np, faiss, SentenceTransformer  # type: ignore
    except Exception:
        from sentence_transformers import SentenceTransformer  # noqa
        import numpy as np, faiss  # noqa
    emb = np.load(EMB_PATH)
    if not os.path.exists(FAISS_PATH):
        return None
    index = faiss.read_index(FAISS_PATH)
    return emb, index

def similarity_search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    meta = _load_meta()
    li = _load_index()
    if not meta or not li:
        return []
    records = meta["records"]
    emb, index = li
    from sentence_transformers import SentenceTransformer
    import numpy as np
    model = SentenceTransformer(MODEL_NAME)
    qv = model.encode([query], normalize_embeddings=True).astype("float32")
    D, I = index.search(qv, min(top_k, emb.shape[0]))
    out = []
    for score, idx in zip(D[0], I[0]):
        rec = records[int(idx)]
        out.append({"id": rec["id"], "name": rec["name"], "chunk_id": rec["chunk_id"], "text": rec["text"], "score": float(score)})
    return out

def best_description_for_names(names: List[str], top_per_name: int = 1) -> Dict[str, List[str]]:
    meta = _load_meta()
    if not meta:
        return {}
    records = meta["records"]
    by = {}
    for r in records:
        by.setdefault(r["name"].lower(), []).append(r["text"])
    out = {}
    for n in names:
        out[n] = by.get(n.lower(), [])[:top_per_name]
    return out

def _augment_with_descriptions(result: Dict[str, Any], user_query: str):
    if not similarity_search:
        return
    slots = result.get("slots") or {}
    recipe_names = slots.get("recipe_name") or []
    flat = []
    for item in recipe_names:
        if isinstance(item, (list, tuple)):
            flat.append(str(item[0]))
        else:
            flat.append(str(item))
    flat = [x for x in flat if x]
    result["descriptions_by_name"] = best_description_for_names(flat, 1) if best_description_for_names else {}
    result["similar_description_chunks"] = similarity_search(user_query, top_k=5)

if __name__ == "__main__":
    build_index()