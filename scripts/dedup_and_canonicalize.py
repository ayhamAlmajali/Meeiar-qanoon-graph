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


def norm_text_key(t: str) -> str:
    s = re.sub(r"[\u0617-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]", "", str(t or ""))
    s = re.sub(r"[إأآا]", "ا", s).replace("ى", "ي").replace("ة", "ه")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:300]


def canonical_title(raw_title: str) -> str:
    t = re.sub(r"\s+", " ", str(raw_title or "").strip())
    low = t.lower()

    if "العمل المرن" in t and ("44" in t or "2024" in t or "flex" in low):
        return "نظام العمل المرن رقم (44) لسنة 2024"
    if "العمل المرن" in t and ("22" in t or "2017" in t):
        return "نظام العمل المرن رقم (22) لسنة 2017 (ملغى)"
    if "قانون العمل" in t or "المواد من (78" in t:
        return "قانون العمل الأردني رقم (8) لسنة 1996 وتعديلاته"
    if "10" in t and "2023" in t and "العمل" in t:
        return "قانون معدل لقانون العمل رقم (10) لسنة 2023"
    if "11" in t and "2019" in t and "العمل المهني" in t:
        return "قانون تنظيم العمل المهني رقم (11) لسنة 2019"
    if "الصحة العامة" in t and "47" in t:
        return "قانون الصحة العامة رقم (47) لسنة 2008"
    if "المواصفات والمقاييس" in t and "22" in t:
        return "قانون المواصفات والمقاييس رقم (22) لسنة 2000"
    if "الوقاية الاشعاعية" in t or "43" in t and "2007" in t:
        return "قانون الوقاية الإشعاعية والأمان والأمن النووي رقم (43) لسنة 2007"
    if "الدستور" in t and "23" in t:
        return "المادة (23) من الدستور الأردني"
    if "عمال الزراعة" in t and "19" in t:
        return "نظام عمال الزراعة رقم (19) لسنة 2021"
    if "العاملين في المنازل" in t and "63" in t:
        return "نظام العاملين في المنازل رقم (63) لسنة 2020"
    if "174" in t and "2016" in t:
        return "نظام التنظيم الإداري لوزارة العمل رقم (174) لسنة 2016"
    if "142" in t and "2019" in t:
        return "نظام رسوم تصاريح العمل لغير الأردنيين رقم (142) لسنة 2019"
    if "112" in t and "2024" in t:
        return "نظام ترخيص شركات تزويد طالبي الخدمة بالعمال الأردنيين رقم (112) لسنة 2024"
    if "33" in t and "2023" in t:
        return "نظام تشكيل لجان ومشرفي السلامة والصحة المهنية رقم (33) لسنة 2023"
    if "شركات الوساطة" in t and "2024" in t:
        return "نظام ترخيص شركات الوساطة لتشغيل الأردنيين رقم (70) لسنة 2024"
    if "العناية الطبية" in t:
        return "نظام العناية الطبية الوقائية والعلاجية للعمال في المؤسسات"
    if "السلامة والصحة المهنية" in t and "نظام" in t:
        return "نظام السلامة والصحة المهنية والوقاية من الأخطار المهنية"
    return t


def main() -> None:
    if not LEG_PATH.exists():
        print("ERROR: data/legislations.json not found.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = LEG_PATH.parent / f"legislations.before_dedup_{stamp}.json"
    shutil.copy2(LEG_PATH, backup_path)

    raw = json.loads(LEG_PATH.read_text(encoding="utf-8"))
    articles = raw.get("articles", raw) if isinstance(raw, dict) else raw

    # ترتيب بحيث نفضّل النصوص الأطول والأكثر اكتمالاً عند وجود تكرار
    articles_sorted = sorted(articles, key=lambda x: len(str(x.get("text") or "")), reverse=True)

    seen_keys: set[tuple[str, str, str]] = set()
    seen_texts: set[str] = set()
    kept: list[dict] = []
    removed_dups = 0
    title_changes = 0

    for a in articles_sorted:
        item = dict(a)
        old_title = str(item.get("legislation_title") or "").strip()
        new_title = canonical_title(old_title)
        if new_title != old_title:
            title_changes += 1
        item["legislation_title"] = new_title
        item["topic_tags"] = [new_title]

        num_key = norm_num(str(item.get("article_number") or ""))
        txt_key = norm_text_key(str(item.get("text") or ""))

        dup_id_key = (new_title, num_key, txt_key)
        if dup_id_key in seen_keys or (len(txt_key) >= 60 and txt_key in seen_texts):
            removed_dups += 1
            continue

        seen_keys.add(dup_id_key)
        if len(txt_key) >= 60:
            seen_texts.add(txt_key)
        kept.append(item)

    if isinstance(raw, dict):
        raw["articles"] = kept
        LEG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        LEG_PATH.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")

    # إعادة استخراج العلاقات على النسخة الموحدة غير المكررة
    print(f"Deduplication done! Backup: {backup_path.name}")
    print(f"  Before          : {len(articles)}")
    print(f"  Duplicates drop : {removed_dups}")
    print(f"  Remaining clean : {len(kept)}")
    print(f"  Titles unified  : {title_changes}")


if __name__ == "__main__":
    main()
