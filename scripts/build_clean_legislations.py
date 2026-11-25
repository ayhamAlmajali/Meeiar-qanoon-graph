import hashlib
import json
import re
from pathlib import Path
import pymupdf

ROOT = Path.cwd()
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "legislations_clean.json"

FOLDERS = [
    DATA_DIR / "extracted_md",
    DATA_DIR / "inbox_docs",
    DATA_DIR / "new_data",
]

ARABIC_DIACRITICS = re.compile(r"[\u0617-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
PAGE_TAG = re.compile(r"\[صفحة\s*\d+\]")
MULTI_SP = re.compile(r"[ \t]+")
MULTI_NL = re.compile(r"\n{3,}")
ARTICLE_HEAD = re.compile(r"(?m)^(?:\s*)(?:المادة\s*[\(\[]?(\d+|[٠-٩]+)[\)\]]?)\s*[:\-–—.]?")

CORRUPT_RE = re.compile(r"ندرالا|نايرسلا|خيرات|hgsjksho|\ufffd|[¥£§¶•·■□◆◇●○★☆]|[\u0750-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")


def clean_str(s: str) -> str:
    t = str(s or "").replace("\x00", "")
    t = PAGE_TAG.sub(" ", t)
    t = ARABIC_DIACRITICS.sub("", t)
    t = t.replace("ـ", "")
    t = MULTI_SP.sub(" ", t)
    t = MULTI_NL.sub("\n\n", t).strip()
    return t


def human_title_from_filename(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"^\d{14}", "", stem)
    stem = stem.replace("_", " ").replace("-", " ")
    stem = MULTI_SP.sub(" ", stem).strip(" _-")
    return stem or Path(name).stem


def extract_text(p: Path) -> str:
    ext = p.suffix.lower()
    if ext == ".pdf":
        doc = pymupdf.open(p)
        pages = [page.get_text("text") or "" for page in doc]
        doc.close()
        return "\n\n".join(pages)
    return p.read_text(encoding="utf-8", errors="ignore")


def split_clean_units(text: str, title: str, source_name: str, file_hash: str) -> list[dict]:
    matches = list(ARTICLE_HEAD.finditer(text))
    units: list[tuple[str, str]] = []

    if len(matches) >= 2:
        for i, m in enumerate(matches):
            art_num = m.group(1)
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = clean_str(text[start:end])
            if len(body) >= 35 and not CORRUPT_RE.search(body):
                units.append((str(art_num), body))
    else:
        paras = [clean_str(p) for p in re.split(r"\n{2,}", text) if len(clean_str(p)) >= 80]
        idx = 1
        buf = ""
        for p in paras:
            if CORRUPT_RE.search(p):
                continue
            if len(buf) + len(p) <= 1300:
                buf = f"{buf}\n\n{p}".strip()
            else:
                if buf:
                    units.append((f"بند-{idx}", buf))
                    idx += 1
                buf = p
        if buf:
            units.append((f"بند-{idx}", buf))

    out = []
    short_hash = file_hash[:10]
    for idx, (num, body) in enumerate(units, 1):
        out.append({
            "id": f"{short_hash}_a{idx}",
            "legislation_title": title,
            "legislation_type": "law_or_regulation",
            "article_number": num,
            "effective_date": "",
            "status": "ساري",
            "topic_tags": [title],
            "text": body,
            "relations": [],
            "official_source": source_name,
            "quality_status": "clean",
            "searchable": True,
        })
    return out


def main() -> None:
    seen_hashes: set[str] = set()
    all_articles: list[dict] = []
    used_files = 0
    skipped_files = 0

    for folder in FOLDERS:
        if not folder.exists():
            continue
        for p in sorted(folder.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in {".pdf", ".txt", ".md"}:
                continue
            raw_txt = extract_text(p)
            norm_txt = clean_str(raw_txt)
            ar_count = len(re.findall(r"[\u0600-\u06FF]", norm_txt))
            corrupt_count = len(CORRUPT_RE.findall(norm_txt))

            if ar_count < 120 or corrupt_count >= 5:
                skipped_files += 1
                continue

            content_hash = hashlib.sha256(norm_txt.encode("utf-8")).hexdigest()
            if content_hash in seen_hashes:
                skipped_files += 1
                continue
            seen_hashes.add(content_hash)

            title = human_title_from_filename(p.name)
            units = split_clean_units(norm_txt, title, p.name, content_hash)
            if not units:
                skipped_files += 1
                continue

            all_articles.extend(units)
            used_files += 1

    OUT_PATH.write_text(json.dumps({"articles": all_articles}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Clean corpus built -> {OUT_PATH}")
    print(f"  Sources used (deduplicated & clean): {used_files}")
    print(f"  Sources skipped (scan/corrupt/dup) : {skipped_files}")
    print(f"  Total clean articles/units         : {len(all_articles)}")


if __name__ == "__main__":
    main()
