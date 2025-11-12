# infer_intent.py
import torch, json
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import os
import torch.nn.functional as F

# Prefer local fine-tuned model directory; allow override via ENV
MODEL_DIR = os.environ.get("INTENT_MODEL_DIR", "../../models/intent-bert")

if not os.path.isdir(MODEL_DIR):
    raise FileNotFoundError(
        f"Intent model directory not found: {MODEL_DIR}.\n"
        "Set INTENT_MODEL_DIR to your local fine-tuned model path, or run the training script to create it."
    )

tok = AutoTokenizer.from_pretrained(MODEL_DIR)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
with open(f"{MODEL_DIR}/label_map.json") as f:
    maps = json.load(f)
id2label = {int(k):v for k,v in maps["id2label"].items()}

def predict_intent(text: str, top_k: int = 2):
    inputs = tok(text, return_tensors="pt", truncation=True)
    with torch.no_grad():
        logits = model(**inputs).logits
        probs = F.softmax(logits, dim=-1).squeeze(0)
    topk = torch.topk(probs, k=min(top_k, probs.shape[0]))
    results = [(id2label[int(i)], float(p)) for p, i in zip(topk.values, topk.indices)]
    return results  # list of (label, confidence)

if __name__ == "__main__":
    q = "ingredientes da francesinha"
    print(predict_intent(q))