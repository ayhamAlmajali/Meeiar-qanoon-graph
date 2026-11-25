import json
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
LEG_PATH = ROOT / "data" / "legislations.json"

ARABIC_DIACRITICS = re.compile(r"[\u0617-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
PRESENTATION_FORMS = re.compile(r"[\uFB50-\uFDFF\uFE70-\uFEFF]")
TATWEEL_REPEAT = re.compile(r"ـ+")
CHAR_STRETCH = re.compile(r"([\u0600-\u06FF])\1{2,}")
PAGE_TAG = re.compile(r"\[صفحة\s*\d+\]")
MULTI_SPACE = re.compile(r"[ \t]+")
MULTI_NL = re.compile(r"\n{3,}")

CORRUPT_PATTERNS = [
    re.compile(r"\ufffd"),
    re.compile(r"[A-Za-z]{4,}"),
    re.compile(r"[¥£§¶•·■□◆◇●○★☆]+"),
    re.compile(r"[\u0750-\u077F\u08A0-\u08FF]"),
]

TITLE_NORMALIZATION_MAP = {
    "قانون العمل الأردني رقم (8) لسنة 1996 وتعديلاته": "قانون العمل رقم 8 لسنة 1996 وتعديلاته وملحقاته",
}


def assess_and_clean_text(raw_text: str) -> tuple[str, str, list[str]]:
    text = str(raw_text or "").replace("\x00", "")
    text = PAGE_TAG.sub(" ", text)
    text = ARABIC_DIACRITICS.sub("", text)
    text = TATWEEL_REPEAT.sub("", text)
    text = CHAR_STRETCH.sub(r"\1", text)
    text = MULTI_SPACE.sub(" ", text)
    text = MULTI_NL.sub("\n\n", text).strip()

    reasons: list[str] = []
    for pat in CORRUPT_PATTERNS:
        if pat.search(text):
            reasons.append(f"pattern:{pat.pattern}")

    words = [w for w in text.split() if re.search(r"[\u0600-\u06FF]", w)]
    if len(words) >= 8:
        single_or_two = sum(1 for w in words if len(re.sub(r"[^\u0600-\u06FF]", "", w)) <= 2)
        ratio = single_or_two / len(words)
        if ratio > 0.36:
            reasons.append(f"fragmented_ratio:{ratio:.2f}")

    if PRESENTATION_FORMS.search(raw_text):
        reasons.append("arabic_presentation_forms")

    if len(text) < 25:
        reasons.append("too_short")

    status = "corrupted_ocr" if reasons else "clean"
    return text, status, reasons


def main() -> None:
    if not LEG_PATH.exists():
        print("ERROR: data/legislations.json not found.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = LEG_PATH.parent / f"legislations.pre_clean_{stamp}.json"
    shutil.copy2(LEG_PATH, backup_path)

    payload = json.loads(LEG_PATH.read_text(encoding="utf-8"))
    articles = payload.get("articles", payload) if isinstance(payload, dict) else payload

    clean_cnt = 0
    corrupt_cnt = 0
    title_cnt = 0
    updated = []

    for art in articles:
        item = dict(art)
        orig_title = str(item.get("legislation_title") or "").strip()
        if orig_title in TITLE_NORMALIZATION_MAP:
            item["legislation_title"] = TITLE_NORMALIZATION_MAP[orig_title]
            title_cnt += 1

        cleaned_text, q_status, reasons = assess_and_clean_text(item.get("text", ""))
        item["text"] = cleaned_text
        item["quality_status"] = q_status
        item["searchable"] = (q_status == "clean")
        item["quality_reasons"] = reasons
        if q_status == "clean":
            clean_cnt += 1
        else:
            corrupt_cnt += 1
        updated.append(item)

    out_obj = {"articles": updated} if isinstance(payload, dict) else updated
    LEG_PATH.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print("DONE! Data cleaned successfully.")
    print(f"  Backup created : {backup_path.name}")
    print(f"  Total articles : {len(updated)}")
    print(f"  Clean & usable : {clean_cnt}")
    print(f"  Corrupted OCR  : {corrupt_cnt} (marked searchable=False)")
    print(f"  Titles unified : {title_cnt}")


if __name__ == "__main__":
    main()
