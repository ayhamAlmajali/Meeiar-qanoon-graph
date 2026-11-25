import math
import os
from typing import Any
import unicodedata

_RERANKER_MODEL = None
_LOAD_FAILED = False
MODEL_NAME = os.environ.get("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3").strip()
ARABIC_TO_WESTERN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _norm(text: str) -> str:
    if not text:
        return ""
    return unicodedata.normalize("NFKC", text).translate(ARABIC_TO_WESTERN_DIGITS).strip()


def get_reranker():
    global _RERANKER_MODEL, _LOAD_FAILED
    if _LOAD_FAILED:
        return None
    if _RERANKER_MODEL is None:
        try:
            from sentence_transformers import CrossEncoder

            device = os.environ.get("RERANKER_DEVICE", "cpu").strip() or "cpu"
            max_len = int(os.environ.get("RERANKER_MAX_LENGTH", "512"))
            # تشغيله على المعالج المركزي افتراضياً لإبقاء الـ GPU متاحاً لنموذج Ollama
            _RERANKER_MODEL = CrossEncoder(MODEL_NAME, device=device, max_length=max_len)
        except Exception as exc:
            print(f"[Reranker Warning] Fallback to base retrieval (unranked): {exc}", flush=True)
            _LOAD_FAILED = True
            return None
    return _RERANKER_MODEL


def _sigmoid(x: float) -> float:
    clamped = max(-60.0, min(60.0, float(x)))
    return 1.0 / (1.0 + math.exp(-clamped))


def rerank_articles(
    query: str,
    articles: list[dict[str, Any]],
    top_k: int = 5,
) -> list[tuple[dict[str, Any], float | None]]:
    """
    يعيد ترتيب المواد المسترجعة باستخدام Cross-Encoder ويرجع قائمة من (المادة، درجة_التطابق_المعيارية).
    عند تعذر تحميل النموذج يرجع (المادة، None) دون اختلاق درجات رقمية.
    """
    if not articles:
        return []

    clean_query = _norm(query)
    if not clean_query:
        return [(art, None) for art in articles[:top_k]]

    model = get_reranker()
    if model is None:
        return [(art, None) for art in articles[:top_k]]

    pairs: list[tuple[str, str]] = []
    for art in articles:
        title = _norm(str(art.get("legislation_title", "")))
        art_num = _norm(str(art.get("article_number", "")))
        body = _norm(str(art.get("text", "")))
        doc_text = f"{title} - مادة {art_num}: {body}"
        pairs.append((clean_query, doc_text))

    try:
        raw_scores = model.predict(pairs)
    except Exception as exc:
        print(f"[Reranker Warning] Predict failed, returning unranked results: {exc}", flush=True)
        return [(art, None) for art in articles[:top_k]]

    scored: list[tuple[dict[str, Any], float]] = []
    for art, score in zip(articles, raw_scores):
        prob = round(_sigmoid(float(score)), 4)
        scored.append((art, prob))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]