import json
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
LEG_PATH = ROOT / "data" / "legislations.json"
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def norm_num(v: str) -> str:
    return str(v or "").translate(ARABIC_DIGITS).strip()


def norm_toks(s: str) -> set[str]:
    t = re.sub(r"[\u0617-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]", "", str(s or ""))
    t = re.sub(r"[إأآا]", "ا", t).replace("ى", "ي").replace("ة", "ه")
    return set(re.findall(r"[\u0600-\u06FF\w]{3,}", t.lower()))


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(LEG_PATH, LEG_PATH.parent / f"legislations.before_strict_dedup_{stamp}.json")

    raw = json.loads(LEG_PATH.read_text(encoding="utf-8"))
    arts = raw.get("articles", raw) if isinstance(raw, dict) else raw

    # نفضل النصوص الأطول والأكثر تفصيلاً ونعطي أولوية للعناوين الرسمية الكاملة على "flex 2024" المختصر
    def rank_key(a: dict) -> tuple[int, int]:
        title = str(a.get("legislation_title") or "")
        is_canonical = 1 if title.lower() != "flex 2024" else 0
        return (is_canonical, len(str(a.get("text") or "")))

    arts_sorted = sorted(arts, key=rank_key, reverse=True)

    seen_title_num: set[tuple[str, str]] = set()
    kept: list[dict] = []
    kept_toks: list[tuple[str, set[str]]] = []
    dropped = 0

    for a in arts_sorted:
        item = dict(a)
        title = str(item.get("legislation_title") or "").strip()
        num = norm_num(str(item.get("article_number") or ""))
        toks = norm_toks(item.get("text") or "")

        if title and num and (title, num) in seen_title_num:
            dropped += 1
            continue

        is_near_dup = False
        if len(toks) >= 8:
            for prev_title, prev_toks in kept_toks:
                if len(prev_toks) >= 8:
                    union = len(toks | prev_toks)
                    if union and (len(toks & prev_toks) / union) >= 0.85:
                        # إذا كان نفس التشريع أو flex 2024 مكرر مع نظام العمل المرن 44 لسنة 2024
                        if title == prev_title or ("flex" in title.lower() and "العمل المرن" in prev_title):
                            is_near_dup = True
                            break

        if is_near_dup:
            dropped += 1
            continue

        if title and num:
            seen_title_num.add((title, num))
        kept.append(item)
        if len(toks) >= 8:
            kept_toks.append((title, toks))

    if isinstance(raw, dict):
        raw["articles"] = kept
        LEG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        LEG_PATH.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Strict dedup finished! Before: {len(arts)} | Dropped: {dropped} | Clean unique: {len(kept)}")


if __name__ == "__main__":
    main()
