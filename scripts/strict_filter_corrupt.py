import json
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
LEG_PATH = ROOT / "data" / "legislations.json"

GARBAGE_MARKERS = [
    "ندرالا",
    "نايرسلا",
    "خيرات",
    "hgsjksho",
]

GARBAGE_REGEXES = [
    re.compile(r"\ufffd"),
    re.compile(r"[¥£§¶•·■□◆◇●○★☆]+"),
    re.compile(r"[A-Za-z]{3,}"),
    re.compile(r"[\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"),
    # أرقام مقلوبة أو رموز مختلطة مثل 17/11/2-51-21 أو 0901-909
    re.compile(r"(?:\d+[-/]){2,}\d+"),
]


def is_corrupted(text: str) -> tuple[bool, list[str]]:
    t = str(text or "")
    reasons: list[str] = []
    for m in GARBAGE_MARKERS:
        if m in t:
            reasons.append(f"marker:{m}")
    for rx in GARBAGE_REGEXES:
        if rx.search(t):
            reasons.append(f"regex:{rx.pattern}")

    # فحص الحروف العربية غير المتصلة بشكل طبيعي (كثرة كلمات قصيرة جداً أو مقطوعة)
    ar_words = [re.sub(r"[^\u0600-\u06FF]", "", w) for w in t.split()]
    ar_words = [w for w in ar_words if w]
    if len(ar_words) >= 6:
        short_cnt = sum(1 for w in ar_words if len(w) <= 2)
        if (short_cnt / len(ar_words)) > 0.32:
            reasons.append(f"short_words_ratio:{short_cnt}/{len(ar_words)}")

    if len(t.strip()) < 25:
        reasons.append("too_short")

    return (len(reasons) > 0), reasons


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(LEG_PATH, LEG_PATH.parent / f"legislations.bak_{stamp}.json")

    raw = json.loads(LEG_PATH.read_text(encoding="utf-8"))
    arts = raw.get("articles", raw) if isinstance(raw, dict) else raw

    clean_n = 0
    corrupt_n = 0
    out = []

    for a in arts:
        item = dict(a)
        corrupt, reasons = is_corrupted(item.get("text", ""))
        item["quality_status"] = "corrupted_ocr" if corrupt else "clean"
        item["searchable"] = not corrupt
        item["quality_reasons"] = reasons
        if corrupt:
            corrupt_n += 1
        else:
            clean_n += 1
        out.append(item)

    if isinstance(raw, dict):
        raw["articles"] = out
        LEG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        LEG_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Total: {len(out)} | Clean: {clean_n} | Corrupted (hidden from search/timeline): {corrupt_n}")


if __name__ == "__main__":
    main()
