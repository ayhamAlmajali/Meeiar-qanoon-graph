import gc
import json
import math
from pathlib import Path
import re
from typing import Any
import urllib.request

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEGISLATIONS_PATH = PROJECT_ROOT / "data" / "legislations.json"
EMBEDDINGS_PATH = PROJECT_ROOT / "data" / "embeddings_index.json"
INBOX_DIR = PROJECT_ROOT / "data" / "inbox_docs"
INGESTED_LOG_PATH = PROJECT_ROOT / "data" / "ingested_files.json"

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_EMBED_URL = "http://127.0.0.1:11434/api/embeddings"
CHAT_MODEL = "qwen2.5:7b"
EMBED_MODEL = "bge-m3"


def get_embedding(text: str) -> list[float]:
    payload = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("embedding", [])


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def extract_text_from_file(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return file_path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        import pypdf

        reader = pypdf.PdfReader(str(file_path))
        pages_text = [page.extract_text() or "" for page in reader.pages]
        del reader
        return "\n".join(pages_text)
    raise ValueError(f"صيغة الملف غير مدعومة حالياً: {suffix}")


def split_legal_text_into_chunks(raw_text: str, chunk_size: int = 6500, overlap: int = 500) -> list[str]:
    clean_text = raw_text.strip()
    if len(clean_text) <= chunk_size:
        return [clean_text] if clean_text else []

    chunks: list[str] = []
    start = 0
    text_len = len(clean_text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        if end < text_len:
            newline_pos = clean_text.rfind("\n", start + chunk_size // 2, end)
            if newline_pos != -1:
                end = newline_pos
        part = clean_text[start:end].strip()
        if part:
            chunks.append(part)
        if end >= text_len:
            break
        start = max(0, end - overlap)

    return chunks


def extract_articles_from_chunk(chunk_text: str, source_name: str, chunk_idx: int, total_chunks: int) -> list[dict[str, Any]]:
    prompt = f"""
أنت محلل تشريعي خبير. استخرج المواد القانونية الواضحة من الجزء ({chunk_idx}/{total_chunks}) للنص التشريعي التالي وحولها إلى مصفوفة JSON صالحة فقط بدون أي نص إضافي خارج JSON.
اسم المصدر: {source_name}

يجب أن يلتزم كل عنصر في المصفوفة بالهيكل التالي:
{{
  "id": "معرف_فريد_بالانجليزية_مثل_law_2025_art_1",
  "legislation_title": "اسم التشريع الكامل بالعربية",
  "legislation_type": "law أو regulation أو instructions",
  "article_number": "رقم المادة",
  "effective_date": "تاريخ النفاذ YYYY-MM-DD إن وجد أو غير محدد",
  "status": "ساري أو ملغى أو معدل",
  "topic_tags": ["وسم1", "وسم2"],
  "text": "النص الكامل للمادة بالعربية",
  "relations": [],
  "official_source": "{source_name}"
}}

النص التشريعي:
{chunk_text}
"""
    payload = json.dumps({
        "model": CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_ctx": 4096},
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_CHAT_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("message", {}).get("content", "{}")
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
            if isinstance(parsed, dict):
                for val in parsed.values():
                    if isinstance(val, list):
                        return [item for item in val if isinstance(item, dict)]
    except Exception as exc:
        print(f"[AI Structure Warning] {source_name} (chunk {chunk_idx}): {exc}", flush=True)
    return []


def structure_document_with_ai(raw_text: str, source_name: str) -> list[dict[str, Any]]:
    chunks = split_legal_text_into_chunks(raw_text)
    all_articles: list[dict[str, Any]] = []
    seen_signatures: set[tuple[str, str]] = set()

    for idx, chunk in enumerate(chunks, start=1):
        print(f"[Ingest] Chunk {idx}/{len(chunks)} for {source_name}...", flush=True)
        items = extract_articles_from_chunk(chunk, source_name, idx, len(chunks))
        for art in items:
            title_norm = re.sub(r"\s+", " ", str(art.get("legislation_title", "")).strip())
            num_norm = re.sub(r"\s+", " ", str(art.get("article_number", "")).strip())
            sig = (title_norm, num_norm)
            if title_norm and num_norm and sig in seen_signatures:
                continue
            if title_norm and num_norm:
                seen_signatures.add(sig)
            all_articles.append(art)

    del chunks
    gc.collect()
    return all_articles


def infer_semantic_relation(new_art: dict[str, Any], existing_art: dict[str, Any]) -> dict[str, str] | None:
    prompt = f"""
قارن بين المادتين القانونيتين التاليتين وحدد هل بينهما علاقة تشريعية مباشرة (إلغاء repeals، تعديل amends، تداخل/تعارض overlaps_with، أو ارتباط details_or_links).
إذا لم توجد علاقة حقيقية أرجع {{"relation_type": "none"}}.

المادة الجديدة:
[{new_art.get('legislation_title', '')} - مادة {new_art.get('article_number', '')}]: {new_art.get('text', '')}

المادة الموجودة:
[{existing_art.get('legislation_title', '')} - مادة {existing_art.get('article_number', '')}]: {existing_art.get('text', '')}

أرجع JSON فقط بهذا الشكل:
{{"relation_type": "repeals أو amends أو overlaps_with أو details_or_links أو none", "note": "شرح موجز بالعربية لسبب الارتباط أو التعارض"}}
"""
    payload = json.dumps({
        "model": CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_ctx": 2048},
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_CHAT_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res = json.loads(data.get("message", {}).get("content", "{}"))
            rtype = res.get("relation_type", "none")
            if rtype in {"repeals", "amends", "overlaps_with", "details_or_links"}:
                return {
                    "relation_type": rtype,
                    "target_ref": existing_art["id"],
                    "note": res.get("note", "ارتباط دلالي مكتشف تلقائياً"),
                }
    except Exception:
        pass
    return None


def rebuild_all_embeddings(force: bool = True) -> int:
    if not LEGISLATIONS_PATH.exists():
        return 0
    data = json.loads(LEGISLATIONS_PATH.read_text(encoding="utf-8"))
    articles = data.get("articles", [])
    index: dict[str, list[float]] = (
        {} if force or not EMBEDDINGS_PATH.exists()
        else json.loads(EMBEDDINGS_PATH.read_text(encoding="utf-8"))
    )
    total = len(articles)
    for idx, art in enumerate(articles, start=1):
        art_id = art["id"]
        if not force and art_id in index and index[art_id]:
            continue
        combined = f"{art.get('legislation_title', '')} مادة {art.get('article_number', '')}: {art.get('text', '')}"
        try:
            index[art_id] = get_embedding(combined)
        except Exception as exc:
            print(f"[Embed Warning] {art_id}: {exc}", flush=True)
        if idx % 10 == 0 or idx == total:
            print(f"[Embeddings] {idx}/{total} processed.", flush=True)
    EMBEDDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    EMBEDDINGS_PATH.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return len(index)


def _slugify_source(source_name: str) -> str:
    stem = Path(source_name).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    return slug or "leg"


def ingest_document(
    raw_text: str,
    source_name: str,
    similarity_threshold: float = 0.80,
    max_relation_checks_per_article: int = 2,
) -> dict[str, Any]:
    existing_data = (
        json.loads(LEGISLATIONS_PATH.read_text(encoding="utf-8"))
        if LEGISLATIONS_PATH.exists()
        else {"articles": []}
    )
    existing_articles: list[dict[str, Any]] = existing_data.get("articles", [])
    existing_ids = {a["id"] for a in existing_articles}

    embeddings_index: dict[str, list[float]] = (
        json.loads(EMBEDDINGS_PATH.read_text(encoding="utf-8")) if EMBEDDINGS_PATH.exists() else {}
    )
    if existing_articles:
        missing_embs = [a for a in existing_articles if a["id"] not in embeddings_index or not embeddings_index[a["id"]]]
        if missing_embs:
            rebuild_all_embeddings(force=False)
            embeddings_index = json.loads(EMBEDDINGS_PATH.read_text(encoding="utf-8"))

    print(f"[Ingest] Structuring {source_name} via {CHAT_MODEL}...", flush=True)
    extracted_articles = structure_document_with_ai(raw_text, source_name)
    added_count = 0
    discovered_relations = 0
    prefix = _slugify_source(source_name)

    for art in extracted_articles:
        if not art.get("text"):
            continue
        art_num_clean = re.sub(r"[^a-z0-9]+", "_", str(art.get("article_number", "")).lower()).strip("_")
        candidate_id = str(art.get("id") or "").strip()
        if not candidate_id or candidate_id in existing_ids:
            base = f"{prefix}_art_{art_num_clean}" if art_num_clean else f"{prefix}_item_{len(existing_articles) + added_count + 1}"
            candidate_id = base
            counter = 2
            while candidate_id in existing_ids:
                candidate_id = f"{base}_{counter}"
                counter += 1
        art["id"] = candidate_id

        combined_text = f"{art.get('legislation_title', '')} مادة {art.get('article_number', '')}: {art.get('text', '')}"
        try:
            new_vec = get_embedding(combined_text)
        except Exception:
            new_vec = []
        if new_vec:
            embeddings_index[art["id"]] = new_vec

        candidates: list[tuple[float, dict[str, Any]]] = []
        if new_vec:
            for ex in existing_articles:
                ex_vec = embeddings_index.get(ex["id"], [])
                sim = cosine_similarity(new_vec, ex_vec)
                if sim >= similarity_threshold:
                    candidates.append((sim, ex))

        candidates.sort(key=lambda x: x[0], reverse=True)
        for _, candidate_art in candidates[:max_relation_checks_per_article]:
            rel = infer_semantic_relation(art, candidate_art)
            if rel:
                art.setdefault("relations", []).append(rel)
                discovered_relations += 1

        existing_articles.append(art)
        existing_ids.add(art["id"])
        added_count += 1

        if added_count % 25 == 0:
            LEGISLATIONS_PATH.write_text(
                json.dumps({"articles": existing_articles}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            EMBEDDINGS_PATH.write_text(json.dumps(embeddings_index, ensure_ascii=False), encoding="utf-8")

    LEGISLATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEGISLATIONS_PATH.write_text(
        json.dumps({"articles": existing_articles}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    EMBEDDINGS_PATH.write_text(json.dumps(embeddings_index, ensure_ascii=False), encoding="utf-8")

    del extracted_articles
    gc.collect()

    return {
        "status": "success",
        "source": source_name,
        "articles_added": added_count,
        "relations_discovered": discovered_relations,
        "total_articles_now": len(existing_articles),
    }


def ingest_inbox_folder() -> dict[str, Any]:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    processed: set[str] = set()
    if INGESTED_LOG_PATH.exists():
        processed = set(json.loads(INGESTED_LOG_PATH.read_text(encoding="utf-8")))

    results = []
    for file_path in sorted(INBOX_DIR.iterdir()):
        if not file_path.is_file() or file_path.name in processed:
            continue
        if file_path.suffix.lower() not in {".pdf", ".txt", ".md"}:
            continue

        raw_text = extract_text_from_file(file_path)
        res = ingest_document(raw_text, file_path.name)
        results.append(res)
        if res.get("articles_added", 0) > 0:
            processed.add(file_path.name)
        del raw_text
        gc.collect()

    INGESTED_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    INGESTED_LOG_PATH.write_text(
        json.dumps(sorted(processed), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"processed_files": len(results), "details": results}


if __name__ == "__main__":
    inbox_summary = ingest_inbox_folder()
    total_emb = rebuild_all_embeddings(force=False)
    print(f"Embeddings available for {total_emb} articles.", flush=True)
    print(f"Inbox ingestion summary: {inbox_summary}", flush=True)