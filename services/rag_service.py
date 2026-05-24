import os
import json
import pickle
from sklearn.metrics.pairwise import cosine_similarity

# ─────────────────────────────────────────────
# Index registry — add new PDFs here
# ─────────────────────────────────────────────

INDEXES = {
    "cotton": {
        "chunks":     "cotton_chunks.json",
        "vectorizer": "cotton_vectorizer.pkl",
        "tfidf":      "cotton_tfidf.pkl",
    },
    "nutrient": {
        "chunks":     "nutrient_chunks.json",
        "vectorizer": "nutrient_vectorizer.pkl",
        "tfidf":      "nutrient_tfidf.pkl",
    },
    "pest_disease": {
        "chunks":     "pest_disease_chunks.json",
        "vectorizer": "pest_disease_vectorizer.pkl",
        "tfidf":      "pest_disease_tfidf.pkl",
    },
    "sugarcane": {
        "chunks":     "sugarcane_chunks.json",
        "vectorizer": "sugarcane_vectorizer.pkl",
        "tfidf":      "sugarcane_tfidf.pkl",
    },
}

_loaded = {}   # cache: { "cotton": {chunks, vectorizer, tfidf}, ... }


def _data_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "..", "Data", filename)


def _load(name: str) -> bool:
    """Load a single index into memory. Returns True if successful."""
    if name in _loaded:
        return True

    cfg = INDEXES.get(name)
    if not cfg:
        return False

    paths = {k: _data_path(v) for k, v in cfg.items()}
    if not all(os.path.exists(p) for p in paths.values()):
        print(f"⚠️  RAG index '{name}' files missing — skipped")
        return False

    with open(paths["chunks"], "r") as f:
        chunks = json.load(f)
    with open(paths["vectorizer"], "rb") as f:
        vectorizer = pickle.load(f)
    with open(paths["tfidf"], "rb") as f:
        tfidf = pickle.load(f)

    _loaded[name] = {"chunks": chunks, "vectorizer": vectorizer, "tfidf": tfidf}
    print(f"✅ RAG '{name}' loaded: {len(chunks)} chunks")
    return True


def _search(name: str, query: str, top_k: int = 3, min_score: float = 0.05) -> list[str]:
    """Search one index. Returns list of relevant text chunks."""
    if not _load(name):
        return []

    idx = _loaded[name]
    try:
        q_vec  = idx["vectorizer"].transform([query])
        scores = cosine_similarity(q_vec, idx["tfidf"]).flatten()
        top_i  = scores.argsort()[-top_k:][::-1]

        results = []
        for i in top_i:
            if scores[i] >= min_score:
                chunk = idx["chunks"][i]
                # Clean repeated PDF headers
                for header in ["INTEGRATED PEST MANAGEMENT PACKAGE FOR COTTON",
                                "INTEGRATED PLANT NUTRITION MANAGEMENT PRACTICES"]:
                    chunk = chunk.replace(header, "")
                chunk = chunk.strip()
                if len(chunk) > 100:
                    results.append(chunk[:800])
        return results

    except Exception as e:
        print(f"⚠️  RAG search error ({name}): {e}")
        return []


# ─────────────────────────────────────────────
# Keyword routing
# ─────────────────────────────────────────────

COTTON_KEYWORDS = [
    "કપાસ", "cotton", "બોલ", "boll", "ઈયળ", "જીવડ",
    "સફેદ માખી", "whitefly", "મોલો", "aphid", "થ્રીપ્સ",
    "thrips", "ગુલાબી", "pink", "mealybug", "jassid",
    "bollworm", "leafhopper", "kapas", "કપાશ"
]

NUTRIENT_KEYWORDS = [
    "ખાતર", "fertilizer", "nutrient", "પોષણ", "નાઇટ્રોજન",
    "nitrogen", "phosphorus", "potassium", "ફોસ્ફરસ", "પોટાશ",
    "zinc", "જસત", "organic", "જૈવિક", "deficiency", "ઉણપ",
    "soil", "જમીન", "manure", "છાણ", "compost", "urea",
    "DAP", "NPK", "micronutrient", "biofertilizer", "પાંદડા પીળા",
    "yellowing", "પોષક", "ઉર્વરક"
]



PEST_DISEASE_KEYWORDS = [
    "જીવાત", "રોગ", "disease", "pest", "ફૂગ", "fungus", "બેક્ટેરિયા",
    "bacteria", "virus", "વાઈરસ", "blight", "wilt", "leaf curl",
    "necrosis", "alternaria", "myrothecium", "spray", "દવા", "છંટકાવ",
    "pheromone", "trap", "ETL", "scouting", "monitoring", "ICAR",
    "insecticide", "fungicide", "કીટ", "ઈયળ", "larvae", "nymph"
]

SUGARCANE_KEYWORDS = [
    "શેરडी", "शेरड़ी", "sugarcane", "ganna", "શેરડ", "ઉસ", "us",
    "borer", "ઈયળ", "red rot", "smut", "wilt", "grub", "whitefly",
    "shoot borer", "top borer", "stem borer", "pyrilla", "mealybug",
    "ratoon", "trash", "seed cane", "settlings", "jaggery", "gur",
    "sugar", "ખાંડ", "ગોળ", "sugarcane mosaic", "pokkah boeng"
]

def get_rag_context(user_message: str, history: list = None) -> str:
    """
    Detect which knowledge base(s) are relevant and return
    combined context to inject into the AI prompt.
    """
    # Build a combined text from current + recent messages for better matching
    recent_text = user_message
    if history:
        for msg in history[-3:]:
            recent_text += " " + msg.get("content", "")
    recent_lower = recent_text.lower()

    results = []

    # Check cotton index
    if any(kw.lower() in recent_lower for kw in COTTON_KEYWORDS):
        chunks = _search("cotton", user_message, top_k=3)
        if chunks:
            results.append(("🌾 કપાસ IPM જ્ઞાન (સ્ત્રોત: ભારત સરકાર)", chunks))

    # Check nutrient index
    if any(kw.lower() in recent_lower for kw in NUTRIENT_KEYWORDS):
        chunks = _search("nutrient", user_message, top_k=2)
        if chunks:
            results.append(("🧪 પોષણ વ્યવસ્થાપન જ્ઞાન (સ્ત્રોત: INM)", chunks))

    # Check sugarcane index
    if any(kw.lower() in recent_lower for kw in SUGARCANE_KEYWORDS):
        chunks = _search("sugarcane", user_message, top_k=3)
        if chunks:
            results.append(("🌿 શેરડી IPM જ્ઞાન (સ્ત્રોત: NIPHM)", chunks))

    # Check pest_disease index
    if any(kw.lower() in recent_lower for kw in PEST_DISEASE_KEYWORDS):
        chunks = _search("pest_disease", user_message, top_k=3)
        if chunks:
            results.append(("🔬 કીટ-રોગ વ્યવસ્થાપન સલાહ (સ્ત્રોત: ICAR 2024-25)", chunks))

    if not results:
        return ""

    # Format for injection into system prompt
    sections = []
    for title, chunks in results:
        body = "\n\n---\n\n".join(chunks)
        sections.append(f"━━━ {title} ━━━\n{body}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    context = "\n\n".join(sections)
    print(f"📚 RAG: injected {len(results)} knowledge source(s)")
    return f"\n{context}\n"