import argparse
import hashlib
import json
import re
import shutil
import urllib.request
from datetime import datetime
from pathlib import Path
import pymupdf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LEG_PATH = DATA_DIR / "legislations.json"
EMB_PATH = DATA_DIR / "embeddings_index.json"
INGESTED_PATH = DATA_DIR / "ingested_files.json"
OLLAMA_URL = "http://127.0.0.1:11434/api/embeddings"
EMBED_MODEL = "bge-m3"


def extract_pdf_text(pdf_path: Path) -> str:
    doc = pymupdf.open(pdf_path)
    parts = []
    for idx, page in enumerate(doc, 1):
        t = page.get_text("text") or ""
        t = t.replace("\x00", "").strip()
        if t:
            parts.append(f"[صفحة {idx}]\n{t}")
    doc.close()
    return "\n\n".join(parts)


def split_into_articles(text: str, title: str, source_file: str) -> list[dict]:
    # محاولة التقسيم حسب "المادة (X)" أو "المادة X"
    pattern = re.compile(r"(?m)^(?:\s*)(?:المادة\s*\(?(\d+|[٠-٩]+)\)?)\s*[:\-–—.]?")
    matches = list(pattern.finditer(text))

    chunks: list[tuple[str, str]] = []
    if len(matches) >= 2:
        for i, m in enumerate(matches):
            art_num = m.group(1)
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if len(body) >= 25:
                chunks.append((art_num, body))
    else:
        # تقسيم متدرج إلى مقاطع متماسكة إذا لم يكن النص مقسماً بكلمة "المادة"
        clean = re.sub(r"\s+", " ", text).strip()
        chunk_size = 1100
        overlap = 150
        step = max(1, chunk_size - overlap)
        idx = 1
        for start in range(0, len(clean), step):
            seg = clean[start : start + chunk_size].strip()
            if len(seg) >= 80:
                chunks.append((f"SEC-{idx}", seg))
                idx += 1
            if start + chunk_size >= len(clean):
                break

    slug = hashlib.md5(f"{source_file}".encode("utf-8")).hexdigest()[:8]
    articles = []
    for i, (art_num, body) in enumerate(chunks, 1):
        art_id = f"pdf_{slug}_art_{art_num}_{i}"
        articles.append({
            "id": art_id,
            "legislation_title": title,
            "legislation_type": "imported_pdf",
            "article_number": str(art_num),
            "effective_date": "",
            "status": "ساري",
            "topic_tags": [title],
            "text": body,
            "relations": [],
            "official_source": f"ملف PDF: {source_file}",
        })
    return articles


def get_bge_embedding(prompt: str) -> list[float]:
    payload = json.dumps({"model": EMBED_MODEL, "prompt": prompt}).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    vec = res.get("embedding", [])
    if not isinstance(vec, list) or len(vec) != 1024:
        raise ValueError(f"Unexpected embedding vector length: {len(vec) if isinstance(vec, list) else type(vec)}")
    return vec


def main():
    parser = argparse.ArgumentParser(description="Convert new PDFs into articles and 1024-d bge-m3 vectors.")
    parser.add_argument("--input-dir", default="data/new_data", help="Directory containing new PDFs")
    parser.add_argument("--apply", action="store_true", help="Write articles, embeddings, and ingested log")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit on number of PDFs to process")
    args = parser.parse_args()

    in_dir = Path(args.input_dir)
    if not in_dir.is_absolute():
        in_dir = PROJECT_ROOT / in_dir

    pdfs = sorted(in_dir.rglob("*.pdf"))
    if args.limit > 0:
        pdfs = pdfs[: args.limit]

    leg_data = json.loads(LEG_PATH.read_text(encoding="utf-8")) if LEG_PATH.exists() else {"articles": []}
    existing_articles = leg_data.get("articles", [])
    existing_ids = {a.get("id") for a in existing_articles}

    emb_index = json.loads(EMB_PATH.read_text(encoding="utf-8")) if EMB_PATH.exists() else {}
    ingested_log = json.loads(INGESTED_PATH.read_text(encoding="utf-8")) if INGESTED_PATH.exists() else []
    if not isinstance(ingested_log, list):
        ingested_log = []
    ingested_set = set(ingested_log)

    new_articles = []
    skipped_files = []
    empty_files = []
    processed_names = []

    for p in pdfs:
        if p.name in ingested_set:
            skipped_files.append(p.name)
            continue
        txt = extract_pdf_text(p)
        if len(txt.strip()) < 50:
            empty_files.append(p.name)
            continue
        title = p.stem.replace("_", " ").strip()
        arts = split_into_articles(txt, title, p.name)
        unique_arts = [a for a in arts if a["id"] not in existing_ids]
        for a in unique_arts:
            existing_ids.add(a["id"])
        new_articles.extend(unique_arts)
        processed_names.append(p.name)

    print(f"PDFs scanned: {len(pdfs)}")
    print(f"Already ingested (skipped): {len(skipped_files)}")
    print(f"Empty / non-selectable text PDFs: {len(empty_files)}")
    print(f"New PDFs ready: {len(processed_names)} -> New article chunks: {len(new_articles)}")

    if not args.apply:
        print("Dry-run mode only. Pass --apply to write articles and generate bge-m3 vectors.")
        return

    if LEG_PATH.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(LEG_PATH, DATA_DIR / f"legislations.backup_{stamp}.json")

    embedded_count = 0
    failed_embeds = 0
    for idx, art in enumerate(new_articles, 1):
        prompt = f"{art['legislation_title']} | المادة {art['article_number']}\n{art['text']}"
        try:
            vec = get_bge_embedding(prompt)
            emb_index[art["id"]] = vec
            embedded_count += 1
        except Exception as exc:
            failed_embeds += 1
            print(f"[Embed Error] {art['id']}: {exc}")
        if idx % 25 == 0 or idx == len(new_articles):
            print(f"Embedded {idx}/{len(new_articles)} new chunks...")

    leg_data["articles"] = existing_articles + new_articles
    LEG_PATH.write_text(json.dumps(leg_data, ensure_ascii=False, indent=2), encoding="utf-8")
    EMB_PATH.write_text(json.dumps(emb_index, ensure_ascii=False), encoding="utf-8")

    for name in processed_names:
        if name not in ingested_set:
            ingested_log.append(name)
    INGESTED_PATH.write_text(json.dumps(ingested_log, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Done. Total articles: {len(leg_data['articles'])} | Vectors embedded: {embedded_count} | Failed: {failed_embeds}")


if __name__ == "__main__":
    main()
