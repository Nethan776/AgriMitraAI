import os
import json
import pickle
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# ─────────────────────────────────────────────
# Load index at startup (once, not per request)
# ─────────────────────────────────────────────

_chunks = None
_vectorizer = None
_tfidf_matrix = None

def _load_index():
    global _chunks, _vectorizer, _tfidf_matrix

    if _chunks is not None:
        return  # Already loaded

    base = os.path.join(os.path.dirname(__file__), "..", "Data")

    chunks_path     = os.path.join(base, "cotton_chunks.json")
    vectorizer_path = os.path.join(base, "cotton_vectorizer.pkl")
    tfidf_path      = os.path.join(base, "cotton_tfidf.pkl")

    if not all(os.path.exists(p) for p in [chunks_path, vectorizer_path, tfidf_path]):
        print("⚠️  RAG index files not found — RAG disabled")
        return

    with open(chunks_path, "r") as f:
        _chunks = json.load(f)

    with open(vectorizer_path, "rb") as f:
        _vectorizer = pickle.load(f)

    with open(tfidf_path, "rb") as f:
        _tfidf_matrix = pickle.load(f)

    print(f"✅ RAG index loaded: {len(_chunks)} cotton knowledge chunks")


# ─────────────────────────────────────────────
# Search
# ─────────────────────────────────────────────

def search_cotton_knowledge(query: str, top_k: int = 3, min_score: float = 0.05) -> str:
    """
    Search the cotton PDF knowledge base for chunks relevant to the query.
    Returns a formatted string to inject into the AI prompt, or empty string
    if nothing relevant is found or RAG is not available.
    """
    _load_index()

    if _chunks is None or _vectorizer is None:
        return ""

    try:
        query_vec = _vectorizer.transform([query])
        scores    = cosine_similarity(query_vec, _tfidf_matrix).flatten()
        top_idx   = scores.argsort()[-top_k:][::-1]

        relevant = []
        for i in top_idx:
            if scores[i] >= min_score:
                # Clean up chunk — remove repeated headers
                chunk = _chunks[i]
                chunk = chunk.replace("INTEGRATED PEST MANAGEMENT PACKAGE FOR COTTON", "").strip()
                if len(chunk) > 100:
                    relevant.append(chunk[:800])  # Cap each chunk at 800 chars

        if not relevant:
            return ""

        context = "\n\n---\n\n".join(relevant)
        return f"""
━━━ કપાસ IPM જ્ઞાન (સ્ત્રોત: ભારત સરકાર) ━━━
{context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    except Exception as e:
        print(f"⚠️  RAG search error: {e}")
        return ""


# ─────────────────────────────────────────────
# Crop detection helper
# ─────────────────────────────────────────────

COTTON_KEYWORDS = [
    "કપાસ", "cotton", "બોલ", "boll", "ઈયળ", "જીવડ",
    "સફેદ માખી", "whitefly", "મોલો", "aphid", "થ્રીપ્સ",
    "thrips", "ગુલાબી", "pink", "mealybug", "jassid",
    "bollworm", "leafhopper", "kapas"
]

def is_cotton_related(text: str) -> bool:
    """Check if the farmer's message is about cotton."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in COTTON_KEYWORDS)