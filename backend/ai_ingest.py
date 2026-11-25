import gc
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any
import unicodedata
import urllib.request

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEGISLATIONS_PATH = PROJECT_ROOT / "data" / "legislations.json"
EMBEDDINGS_PATH = PROJECT_ROOT / "data" / "embeddings_index.json"
INBOX_DIR = PROJECT_ROOT / "data" / "inbox_docs"
INGESTED_LOG_PATH = PROJECT_ROOT / "data" / "ingested_files.json"

OLLAMA_CHAT_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
OLLAMA_EMBED_URL = os.environ.get("OLLAMA_EMBED_URL", "http://127.0.0.1:11434/api/embeddings")
CHAT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")

ARABIC_TO_WESTERN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
TASHKEEL_AND_TATWEEL_RE = re.compile(r"[\u064B-\u065F\u0670\u0640]")

HIERARCHY_RANK = {
    "constitution": 4,
    "law": 3,
    "regulation": 2,
    "instructions": 1,
}


def normalize_arabic_text(text: str, strip_diacritics: bool = False) -> str:
    if not text:
        return ""
    norm = unicodedata.normalize("NFKC", text)
    norm = norm.translate(ARABIC_TO_WESTERN_DIGITS)
    if strip_diacritics:
        norm = TASHKEEL_AND_TATWEEL_RE.sub("", norm)
    return norm


def _atomic_write_text(target_path: Path, content: str) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(target_path.parent),
        prefix=f".{target_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, target_path)


def _atomic_write_json(target_path: Path, payload: Any, indent: int | None = 2) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=indent)
    _atomic_write_text(target_path, serialized)


def _compute_file_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_embedding(text: str) -> list[float]:
    clean = normalize_arabic_text(text, strip_diacritics=True)
    payload = json.dumps({"model": EMBED_MODEL, "prompt": clean}).encode("utf-8")
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
        raw = file_path.read_text(encoding="utf-8")
        return normalize_arabic_text(raw, strip_diacritics=False)

    if suffix == ".pdf":
        pages_text: list[str] = []
        # 1) تفضيل PyMuPDF (fitz) أو pdfplumber إن وُجدا لدقتهما في العربية
        try:
            import fitz  # type: ignore

            with fitz.open(str(file_path)) as doc:
                pages_text = [page.get_text("text") or "" for page in doc]
        except ImportError:
            try:
                import pdfplumber  # type: ignore

                with pdfplumber.open(str(file_path)) as pdf:
                    pages_text = [page.extract_text() or "" for page in pdf.pages]
            except ImportError:
                import pypdf

                reader = pypdf.PdfReader(str(file_path))
                pages_text = [page.extract_text() or "" for page in reader.pages]
                del reader

        combined = normalize_arabic_text("\n".join(pages_text), strip_diacritics=False).strip()
        if len(combined) < 30:
            raise ValueError(
                f"ملف PDF ({file_path.name}) لا يحتوي على طبقة نصية قابلة للقراءة (يبدو ممسوحاً ضوئياً ويحتاج OCR)."
            )
        return combined

    raise ValueError(f"صيغة الملف غير مدعومة حالياً: {suffix}")


def _infer_legislation_type(title: str, explicit_type: str = "") -> str:
    t_norm = normalize_arabic_text(title, strip_diacritics=True)
    exp = str(explicit_type or "").strip().lower()
    if "دستور" in t_norm:
        return "constitution"
    if "نظام" in t_norm:
        return "regulation"
    if "تعليمات" in t_norm or "قرار" in t_norm:
        return "instructions"
    if "قانون" in t_norm:
        return "law"
    if exp in HIERARCHY_RANK:
        return exp
    return "law"


def extract_canonical_law_identity(title: str, explicit_type: str = "", fallback_source: str = "") -> dict[str, Any]:
    clean_title = re.sub(r"\s+", " ", normalize_arabic_text(title or fallback_source, strip_diacritics=True)).strip()
    leg_type = _infer_legislation_type(clean_title, explicit_type)

    num_match = re.search(r"رقم\s*[\(\[]?\s*(\d+)\s*[\)\]]?", clean_title)
    year_match = re.search(r"لسنة\s*[\(\[]?\s*(\d{4})\s*[\)\]]?", clean_title)

    law_num = num_match.group(1) if num_match else ""
    law_year = int(year_match.group(1)) if year_match else None

    if law_num and law_year:
        canonical_id = f"{leg_type}_{law_num}_{law_year}"
    elif law_year:
        slug = _slugify_source(clean_title)[:28]
        canonical_id = f"{leg_type}_{slug}_{law_year}"
    else:
        slug = _slugify_source(clean_title or fallback_source)[:36]
        canonical_id = f"{leg_type}_{slug}"

    is_amending = bool(re.search(r"(?:^|\s)(?:قانون|نظام|تعليمات)\s+معدل\b", clean_title))
    return {
        "canonical_law_id": canonical_id,
        "legislation_type": leg_type,
        "law_number": law_num or None,
        "law_year": law_year,
        "is_amending_legislation": is_amending,
    }


def _normalize_article_number(raw_num: Any) -> str:
    s = re.sub(r"\s+", " ", normalize_arabic_text(str(raw_num or ""), strip_diacritics=True)).strip()
    s = re.sub(r"^(?:المادة|مادة)\s*", "", s).strip()
    s = s.strip("()[]")
    return s


def _article_num_to_id_slug(article_number: str) -> str:
    clean = _normalize_article_number(article_number)
    if not clean:
        return ""
    m = re.match(r"^(\d+)\s*(.*)$", clean)
    if m:
        digits = m.group(1)
        suffix = m.group(2).strip()
        if not suffix:
            return digits
        if "مكرر" in suffix:
            extra = re.sub(r"[^0-9]+", "", suffix)
            return f"{digits}_mukarrar_{extra}" if extra else f"{digits}_mukarrar"
        slug_suf = re.sub(r"[^a-z0-9]+", "_", suffix.lower()).strip("_")
        return f"{digits}_{slug_suf}" if slug_suf else digits
    return re.sub(r"[^a-z0-9]+", "_", clean.lower()).strip("_")


def split_legal_text_into_chunks(raw_text: str, chunk_size: int = 6500, overlap: int = 500) -> list[str]:
    clean_text = normalize_arabic_text(raw_text, strip_diacritics=False).strip()
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


def _slice_verbatim_article(chunk_text: str, article_number: Any, model_text: str) -> str:
    clean_model_text = str(model_text or "").strip()
    if clean_model_text and clean_model_text in chunk_text:
        return clean_model_text

    num_str = _normalize_article_number(article_number)
    if num_str:
        pattern = (
            rf"(?:^|\n)\s*(?:المادة|مادة)\s*[\(\[]?{re.escape(num_str)}[\)\]]?\b"
            rf"[\s\S]*?(?=(?:\n\s*(?:المادة|مادة)\s*[\(\[]?\d+)|$)"
        )
        m = re.search(pattern, chunk_text)
        if m:
            sliced = m.group(0).strip()
            if len(sliced) >= 15:
                return sliced

    return clean_model_text


def _parse_articles_payload(parsed: Any) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        for key in ("articles", "items", "data", "provisions"):
            val = parsed.get(key)
            if isinstance(val, list):
                return [item for item in val if isinstance(item, dict)]
        if any(k in parsed for k in ("article_number", "text", "legislation_title", "id")):
            return [parsed]
    return []


def _extract_deterministic_relations(
    article: dict[str, Any],
    existing_articles: list[dict[str, Any]],
) -> list[dict[str, str]]:
    text_norm = normalize_arabic_text(article.get("text", ""), strip_diacritics=True)
    title_norm = normalize_arabic_text(article.get("legislation_title", ""), strip_diacritics=True)
    relations: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add_rel(rel_type: str, target_ref: str, note: str) -> None:
        key = (rel_type, target_ref)
        if target_ref and key not in seen:
            seen.add(key)
            relations.append({"relation_type": rel_type, "target_ref": target_ref, "note": note})

    def _find_target_article(target_art_num: str, target_law_hint: str = "") -> str | None:
        clean_num = _normalize_article_number(target_art_num)
        hint_clean = normalize_arabic_text(target_law_hint, strip_diacritics=True).strip()
        for ex in existing_articles:
            if ex.get("canonical_law_id") == article.get("canonical_law_id"):
                continue
            if _normalize_article_number(ex.get("article_number")) != clean_num:
                continue
            ex_title = normalize_arabic_text(ex.get("legislation_title", ""), strip_diacritics=True)
            if not hint_clean or hint_clean in ex_title or ex_title in hint_clean:
                return ex["id"]
        return None

    # 1) كشف بند الإلغاء العام دون تحويله إلى إلغاء محدد لمادة بعينها
    if re.search(r"يلغى\s+كل\s+(?:نص|حكم|تشريع)\s+يتعارض", text_norm):
        _add_rel(
            "possible_implicit_repeal",
            "general_conflicting_provisions",
            "بند إلغاء عام لكل ما يتعارض مع أحكام هذا التشريع (يستوجب مراجعة التعارض الموضوعي).",
        )

    # 2) كشف التعديل الصريح: تُعدّل المادة (X) من ...
    for m in re.finditer(
        r"(?:تعدل|تُعدّل)\s+المادة\s*[\(\[]?\s*(\d+(?:\s*مكرر)?)\s*[\)\]]?(?:\s+من\s+([^\n،\.]{4,90}))?",
        text_norm,
    ):
        t_num = m.group(1)
        t_law = (m.group(2) or "").replace("القانون الاصلي", "").replace("القانون الأصلي", "").strip()
        target_id = _find_target_article(t_num, t_law)
        if target_id:
            _add_rel("amends", target_id, f"تعديل صريح للمادة ({t_num}) بموجب {article.get('legislation_title', '')}.")

    # 3) كشف الإلغاء الصريح لمادة محددة: يلغى نص المادة (X) ...
    for m in re.finditer(
        r"(?:يلغى|يُلغى)\s+(?:نص\s+)?المادة\s*[\(\[]?\s*(\d+(?:\s*مكرر)?)\s*[\)\]]?(?:\s+من\s+([^\n،\.]{4,90}))?",
        text_norm,
    ):
        t_num = m.group(1)
        t_law = (m.group(2) or "").replace("القانون الاصلي", "").replace("القانون الأصلي", "").strip()
        target_id = _find_target_article(t_num, t_law)
        if target_id:
            _add_rel("repeals", target_id, f"إلغاء صريح للمادة ({t_num}) بموجب {article.get('legislation_title', '')}.")

    # 4) كشف التبعية الهرمية: صادر بمقتضى المادة (X) من القانون ...
    for m in re.finditer(
        r"صادر(?:ة)?\s+بمقتضى\s+(?:احكام\s+)?المادة\s*[\(\[]?\s*(\d+)\s*[\)\]]?\s+من\s+([^\n،\.]{4,100})",
        f"{title_norm}\n{text_norm}",
    ):
        t_num = m.group(1)
        t_law = m.group(2).strip()
        target_id = _find_target_article(t_num, t_law)
        if target_id:
            _add_rel(
                "issued_under",
                target_id,
                f"تشريع فرعي صادر بمقتضى المادة ({t_num}) من {t_law}.",
            )

    return relations


def extract_articles_from_chunk(chunk_text: str, source_name: str, chunk_idx: int, total_chunks: int) -> list[dict[str, Any]]:
    prompt = f"""
أنت محلل تشريعي خبير. استخرج البيانات الوصفية للمواد القانونية الواضحة من الجزء ({chunk_idx}/{total_chunks}) للنص التشريعي التالي.
مهم جداً: لا تعِد صياغة نص المادة أو تلخيصه؛ اترك حقل "text" فارغاً لأن النظام سيأخذ النص الحرفي مباشرة من النص الأصلي.
أرجع JSON صالح فقط بالشكل {{"articles": [...]}} بدون أي نص خارج JSON.
اسم المصدر: {source_name}

كل عنصر داخل "articles" يكون بهذا الشكل:
{{
  "id": "معرف_فريد_بالانجليزية_مثل_law_2025_art_1",
  "legislation_title": "اسم التشريع الكامل بالعربية",
  "legislation_type": "law أو regulation أو instructions",
  "article_number": "رقم المادة",
  "effective_date": "تاريخ النفاذ YYYY-MM-DD إن وجد أو غير محدد",
  "status": "ساري أو ملغى أو معدل",
  "topic_tags": ["وسم1", "وسم2"],
  "text": "",
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
        "options": {"temperature": 0.1, "num_ctx": 8192},
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
            raw_items = _parse_articles_payload(parsed)
            normalized: list[dict[str, Any]] = []
            for item in raw_items:
                art_copy = dict(item)
                art_copy["text"] = _slice_verbatim_article(
                    chunk_text=chunk_text,
                    article_number=art_copy.get("article_number"),
                    model_text=art_copy.get("text", ""),
                )
                normalized.append(art_copy)
            return normalized
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
            identity = extract_canonical_law_identity(
                title=str(art.get("legislation_title", "")),
                explicit_type=str(art.get("legislation_type", "")),
                fallback_source=source_name,
            )
            num_norm = _normalize_article_number(art.get("article_number", ""))
            sig = (identity["canonical_law_id"], num_norm)
            if num_norm and sig in seen_signatures:
                continue
            if num_norm:
                seen_signatures.add(sig)
            art.update(identity)
            art["article_number"] = num_norm or str(art.get("article_number", "")).strip()
            all_articles.append(art)

    del chunks
    gc.collect()
    return all_articles


def _resolve_directional_relation(
    raw_rtype: str,
    new_art: dict[str, Any],
    existing_art: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    """
    يحدد اتجاه علاقة التعديل/الإلغاء وفق التسلسل الزمني والتدرج الهرمي بدلاً من ترتيب الإدخال.
    يرجع (relation_type, source_art, target_art) أو None إذا تعارض الاتجاه مع الهرمية التشريعية.
    """
    new_year = new_art.get("law_year")
    ex_year = existing_art.get("law_year")
    new_rank = HIERARCHY_RANK.get(str(new_art.get("legislation_type", "law")), 3)
    ex_rank = HIERARCHY_RANK.get(str(existing_art.get("legislation_type", "law")), 3)

    if raw_rtype in {"amends", "repeals"}:
        # التشريع الأدنى مرتبة (مثل تعليمات أو نظام) لا يلغي أو يعدّل قانوناً أعلى منه
        if new_rank < ex_rank and ex_rank >= new_rank:
            if ex_rank > new_rank:
                return ("details_or_links", new_art, existing_art)
        # إذا أُدخل القانون الأقدم بعد القانون المعدّل الأحدث، نعكس الاتجاه
        if isinstance(new_year, int) and isinstance(ex_year, int) and new_year < ex_year:
            if ex_rank >= new_rank:
                return (raw_rtype, existing_art, new_art)
            return None
        return (raw_rtype, new_art, existing_art)

    return (raw_rtype, new_art, existing_art)


def infer_semantic_relation(new_art: dict[str, Any], existing_art: dict[str, Any]) -> dict[str, str] | None:
    # تجنب الضوضاء بين مواد نفس التشريع
    if new_art.get("canonical_law_id") and new_art.get("canonical_law_id") == existing_art.get("canonical_law_id"):
        return None

    prompt = f"""
قارن بين المادتين القانونيتين التاليتين وحدد هل بينهما علاقة تشريعية مباشرة:
- repeals: إلغاء صريح أو ضمني لنص المادة الأخرى.
- amends: تعديل حكم وارد في المادة الأخرى.
- contradicts: تعارض مباشر في الحكم أو الالتزام أو المدة أو النسبة.
- overlaps_with: تداخل موضوعي دون تعارض إلغائي.
- details_or_links: تفصيل تنفيذي أو إحالة تنظيمية.
- none: لا توجد علاقة تشريعية حقيقية.

المادة (أ):
[{new_art.get('legislation_title', '')} | النوع: {new_art.get('legislation_type', '')} | السنة: {new_art.get('law_year', 'غير محدد')} | مادة {new_art.get('article_number', '')}]:
{new_art.get('text', '')}

المادة (ب):
[{existing_art.get('legislation_title', '')} | النوع: {existing_art.get('legislation_type', '')} | السنة: {existing_art.get('law_year', 'غير محدد')} | مادة {existing_art.get('article_number', '')}]:
{existing_art.get('text', '')}

أرجع JSON فقط بهذا الشكل:
{{"relation_type": "repeals أو amends أو contradicts أو overlaps_with أو details_or_links أو none", "note": "شرح موجز بالعربية لسبب الارتباط أو التعارض"}}
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
            rtype = str(res.get("relation_type", "none")).strip()
            if rtype in {"repeals", "amends", "contradicts", "overlaps_with", "details_or_links"}:
                resolved = _resolve_directional_relation(rtype, new_art, existing_art)
                if not resolved:
                    return None
                final_rtype, src_art, tgt_art = resolved
                return {
                    "relation_type": final_rtype,
                    "source_ref": src_art["id"],
                    "target_ref": tgt_art["id"],
                    "note": str(res.get("note") or "ارتباط دلالي مكتشف تلقائياً").strip(),
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
    _atomic_write_json(EMBEDDINGS_PATH, index, indent=None)
    return len(index)


def _slugify_source(source_name: str) -> str:
    stem = Path(source_name).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    return slug or "leg"


def _apply_computed_statuses(articles: list[dict[str, Any]]) -> None:
    """
    يشتق حالة المادة (ساري / معدل / ملغى) حتمياً من أحداث التعديل والإلغاء المسجلة في العلاقات.
    """
    by_id = {a["id"]: a for a in articles if a.get("id")}
    for art in articles:
        for rel in art.get("relations", []):
            rtype = rel.get("relation_type")
            target_id = rel.get("target_ref")
            target = by_id.get(target_id) if target_id else None
            if not target:
                continue
            if rtype == "repeals":
                target["status"] = "ملغى"
                target["superseded_by"] = art["id"]
            elif rtype == "amends" and target.get("status") != "ملغى":
                target["status"] = "معدل"
                target["amended_by"] = art["id"]


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
    existing_by_id: dict[str, dict[str, Any]] = {a["id"]: a for a in existing_articles if a.get("id")}

    # فهرس منع التكرار حسب (canonical_law_id, article_number)
    existing_by_canonical_key: dict[tuple[str, str], dict[str, Any]] = {}
    for ex in existing_articles:
        ident = extract_canonical_law_identity(
            title=str(ex.get("legislation_title", "")),
            explicit_type=str(ex.get("legislation_type", "")),
            fallback_source=str(ex.get("official_source", "")),
        )
        ex.setdefault("canonical_law_id", ident["canonical_law_id"])
        ex.setdefault("law_year", ident["law_year"])
        ex.setdefault("law_number", ident["law_number"])
        num_k = _normalize_article_number(ex.get("article_number", ""))
        if num_k:
            existing_by_canonical_key[(ex["canonical_law_id"], num_k)] = ex

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
    updated_count = 0
    discovered_relations = 0
    prefix = _slugify_source(source_name)

    for art in extracted_articles:
        if not art.get("text"):
            continue

        canonical_law_id = art.get("canonical_law_id") or prefix
        art_num_norm = _normalize_article_number(art.get("article_number", ""))
        art_num_slug = _article_num_to_id_slug(art_num_norm)

        # التحقق من وجود المادة مسبقاً لمنع التكرار عند إعادة الإدخال
        existing_match = (
            existing_by_canonical_key.get((canonical_law_id, art_num_norm))
            if art_num_norm
            else None
        )

        if existing_match is not None:
            candidate_id = existing_match["id"]
            art["id"] = candidate_id
            art["relations"] = existing_match.get("relations", [])
        else:
            base_id = (
                f"{canonical_law_id}_art_{art_num_slug}"
                if art_num_slug
                else f"{canonical_law_id}_item_{len(existing_articles) + added_count + 1}"
            )
            candidate_id = base_id
            counter = 2
            while candidate_id in existing_by_id:
                candidate_id = f"{base_id}_{counter}"
                counter += 1
            art["id"] = candidate_id

        combined_text = f"{art.get('legislation_title', '')} مادة {art.get('article_number', '')}: {art.get('text', '')}"
        try:
            new_vec = get_embedding(combined_text)
        except Exception:
            new_vec = []
        if new_vec:
            embeddings_index[art["id"]] = new_vec

        # 1) استخراج العلاقات التشريعية الحتمية أولاً
        det_rels = _extract_deterministic_relations(art, existing_articles)
        for rel in det_rels:
            if not any(
                r.get("relation_type") == rel["relation_type"] and r.get("target_ref") == rel["target_ref"]
                for r in art.setdefault("relations", [])
            ):
                art["relations"].append(rel)
                discovered_relations += 1

        # 2) استخراج العلاقات الدلالية عبر قوانين مختلفة فقط
        candidates: list[tuple[float, dict[str, Any]]] = []
        if new_vec:
            for ex in existing_articles:
                if ex.get("canonical_law_id") == canonical_law_id:
                    continue
                ex_vec = embeddings_index.get(ex["id"], [])
                sim = cosine_similarity(new_vec, ex_vec)
                if sim >= similarity_threshold:
                    candidates.append((sim, ex))

        candidates.sort(key=lambda x: x[0], reverse=True)
        for _, candidate_art in candidates[:max_relation_checks_per_article]:
            rel = infer_semantic_relation(art, candidate_art)
            if rel:
                src_id = rel.pop("source_ref", art["id"])
                target_holder = art if src_id == art["id"] else existing_by_id.get(src_id, art)
                if not any(
                    r.get("relation_type") == rel["relation_type"] and r.get("target_ref") == rel["target_ref"]
                    for r in target_holder.setdefault("relations", [])
                ):
                    target_holder["relations"].append(rel)
                    discovered_relations += 1

        if existing_match is not None:
            existing_match.update(art)
            updated_count += 1
        else:
            existing_articles.append(art)
            existing_by_id[art["id"]] = art
            if art_num_norm:
                existing_by_canonical_key[(canonical_law_id, art_num_norm)] = art
            added_count += 1

        if (added_count + updated_count) % 25 == 0:
            _apply_computed_statuses(existing_articles)
            _atomic_write_json(LEGISLATIONS_PATH, {"articles": existing_articles}, indent=2)
            _atomic_write_json(EMBEDDINGS_PATH, embeddings_index, indent=None)

    _apply_computed_statuses(existing_articles)
    _atomic_write_json(LEGISLATIONS_PATH, {"articles": existing_articles}, indent=2)
    _atomic_write_json(EMBEDDINGS_PATH, embeddings_index, indent=None)

    del extracted_articles
    gc.collect()

    return {
        "status": "success",
        "source": source_name,
        "articles_added": added_count,
        "articles_updated": updated_count,
        "relations_discovered": discovered_relations,
        "total_articles_now": len(existing_articles),
    }


def _load_ingested_registry() -> dict[str, dict[str, Any]]:
    if not INGESTED_LOG_PATH.exists():
        return {}
    raw = json.loads(INGESTED_LOG_PATH.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        # ترقية السجل القديم القائم على الأسماء إلى قاموس متوافق
        return {f"legacy:{name}": {"filename": name} for name in raw}
    if isinstance(raw, dict):
        return raw
    return {}


def ingest_inbox_folder() -> dict[str, Any]:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    registry = _load_ingested_registry()
    known_hashes = {meta.get("sha256") for meta in registry.values() if meta.get("sha256")}
    known_legacy_names = {meta.get("filename") for k, meta in registry.items() if k.startswith("legacy:")}

    results = []
    for file_path in sorted(INBOX_DIR.iterdir()):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {".pdf", ".txt", ".md"}:
            continue

        file_hash = _compute_file_sha256(file_path)
        if file_hash in known_hashes or file_path.name in known_legacy_names:
            continue

        raw_text = extract_text_from_file(file_path)
        res = ingest_document(raw_text, file_path.name)
        results.append(res)
        if res.get("articles_added", 0) > 0 or res.get("articles_updated", 0) > 0:
            registry[file_hash] = {
                "sha256": file_hash,
                "filename": file_path.name,
                "articles_added": res.get("articles_added", 0),
                "articles_updated": res.get("articles_updated", 0),
            }
            known_hashes.add(file_hash)
        del raw_text
        gc.collect()

    _atomic_write_json(INGESTED_LOG_PATH, registry, indent=2)
    return {"processed_files": len(results), "details": results}


if __name__ == "__main__":
    inbox_summary = ingest_inbox_folder()
    total_emb = rebuild_all_embeddings(force=False)
    print(f"Embeddings available for {total_emb} articles.", flush=True)
    print(f"Inbox ingestion summary: {inbox_summary}", flush=True)