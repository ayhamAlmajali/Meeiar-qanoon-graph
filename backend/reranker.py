from typing import Any
import math

_RERANKER_MODEL = None
_LOAD_FAILED = False
MODEL_NAME = "BAAI/bge-reranker-v2-m3"


def get_reranker():
    global _RERANKER_MODEL, _LOAD_FAILED
    if _LOAD_FAILED:
        return None
    if _RERANKER_MODEL is None:
        try:
            from sentence_transformers import CrossEncoder
            # تشغيله على المعالج المركزي لإبقاء الـ GPU متاحاً بالكامل لنموذج Ollama
            _RERANKER_MODEL = CrossEncoder(MODEL_NAME, device="cpu", max_length=512)
        except Exception as exc:
            print(f"[Reranker Warning] Fallback to base retrieval: {exc}")
            _LOAD_FAILED = True
            return None
    return _RERANKER_MODEL


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def rerank_articles(
    query: str,
    articles: list[dict[str, Any]],
    top_k: int = 5,
) -> list[tuple[dict[str, Any], float]]:
    """
    يعيد ترتيب المواد المسترجعة باستخدام Cross-Encoder ويرجع قائمة من (المادة، درجة_التطابق_المعيارية).
    """
    if not articles:
        return []

    model = get_reranker()
    if model is None:
        fallback_scored = []
        for idx, art in enumerate(articles[:top_k]):
            rank_score = round(max(0.20, 0.70 - idx * 0.08), 4)
            fallback_scored.append((art, rank_score))
        return fallback_scored

    pairs = []
    for art in articles:
        doc_text = f"{art.get('legislation_title', '')} - مادة {art.get('article_number', '')}: {art.get('text', '')}"
        pairs.append((query, doc_text))

    raw_scores = model.predict(pairs)
    scored = []
    for art, score in zip(articles, raw_scores):
        prob = round(float(_sigmoid(float(score))), 4)
        scored.append((art, prob))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]