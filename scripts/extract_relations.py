import json
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
LEG_PATH = ROOT / "data" / "legislations.json"
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

ARTICLE_REF_RE = re.compile(r"(?:المادة|المواد)\s*[\(\[]?(\d+|[٠-٩]+)[\)\]]?")
LAW_REF_RE = re.compile(
    r"(?:قانون|نظام|تعليمات|قرار|دستور)\s+(?:رقم\s*)?[\(\[]?[\d٠-٩]+[\)\]]?\s*لسنة\s*[\d٠-٩]{4}"
)


def norm_num(val: str) -> str:
    return str(val or "").translate(ARABIC_DIGITS).strip()


def classify_edge(src_title: str, dst_title: str, text: str, is_same_law: bool) -> str:
    s_low = f"{src_title} {text}".lower()

    # 1) إلغاء صريح أو تنظيم لاحق يحل محل سابق
    if any(k in text for k in ("يلغى", "يلغي", "يُلغى", "يُلغي", "ملغى")):
        return "repeals"
    if "العمل المرن" in src_title and "2024" in src_title and "2017" in dst_title:
        return "repeals"

    # 2) تعديل صريح أو تشريع معدِّل
    if "معدل" in src_title or any(k in text for k in ("يعدل", "يُعدّل", "تعديل احكام", "تعديل أحكام", "يستبدل")):
        return "amends"

    # 3) نظام/تعليمات/قرار صادر بموجب قانون أو تشريع أصل
    if not is_same_law and any(k in text for k in ("استنادا", "استناداً", "بمقتضى", "بموجب احكام", "بموجب أحكام", "تنفيذا")):
        return "implements"

    # 4) تداخل تشريعي حقيقي فقط عند وجود نص صريح على تعارض/تداخل أو ارتباط تشريعين بنفس الموضوع (العمل/العمل المرن/السلامة)
    if not is_same_law and any(k in text for k in ("يتعارض", "تعارض", "تداخل")):
        return "overlaps_with"

    # إحالة عادية افتراضياً
    return "references"


def main() -> None:
    if not LEG_PATH.exists():
        print("ERROR: data/legislations.json not found.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(LEG_PATH, LEG_PATH.parent / f"legislations.before_logical_rel_{stamp}.json")

    raw = json.loads(LEG_PATH.read_text(encoding="utf-8"))
    articles = raw.get("articles", raw) if isinstance(raw, dict) else raw

    by_title_num: dict[tuple[str, str], str] = {}
    by_title_first: dict[str, str] = {}
    title_by_id: dict[str, str] = {}

    for a in articles:
        aid = str(a.get("id") or "")
        title = str(a.get("legislation_title") or "").strip()
        num = norm_num(str(a.get("article_number") or ""))
        if not aid:
            continue
        title_by_id[aid] = title
        if title and num:
            by_title_num[(title, num)] = aid
        if title and title not in by_title_first:
            by_title_first[title] = aid

    flex_2024_ids = [
        str(a["id"]) for a in articles
        if "العمل المرن" in str(a.get("legislation_title") or "") and "2024" in str(a.get("legislation_title") or "")
    ]
    flex_2017_ids = [
        str(a["id"]) for a in articles
        if "العمل المرن" in str(a.get("legislation_title") or "") and "2017" in str(a.get("legislation_title") or "")
    ]

    total_edges = 0
    counts: dict[str, int] = {}
    updated = []

    for a in articles:
        item = dict(a)
        src_id = str(item.get("id") or "")
        title = str(item.get("legislation_title") or "").strip()
        text = str(item.get("text") or "")

        seen: set[tuple[str, str]] = set()
        rels: list[dict] = []

        def push_edge(tgt_id: str, note: str, force_type: str | None = None) -> None:
            nonlocal total_edges, counts
            if not tgt_id or tgt_id == src_id:
                return
            dst_title = title_by_id.get(tgt_id, "")
            rtype = force_type or classify_edge(title, dst_title, text, title == dst_title)
            key = (tgt_id, rtype)
            if key in seen:
                return
            seen.add(key)
            rels.append({
                "relation_type": rtype,
                "target_ref": tgt_id,
                "note": note,
                "verification_status": "verified",
                "provenance": "logical_rule_extraction",
            })
            total_edges += 1
            counts[rtype] = counts.get(rtype, 0) + 1

        for m in ARTICLE_REF_RE.finditer(text):
            tnum = norm_num(m.group(1))
            tgt = by_title_num.get((title, tnum))
            if tgt:
                push_edge(tgt, f"إحالة إلى المادة ({tnum}) ضمن {title}")

        for m in LAW_REF_RE.finditer(text):
            phrase = m.group(0).strip()
            for other_title, other_id in by_title_first.items():
                if other_title != title and any(tok in other_title for tok in phrase.split() if len(tok) >= 4):
                    push_edge(other_id, f"إشارة تشريعية إلى: {phrase}")
                    break

        if src_id in flex_2024_ids and flex_2017_ids:
            push_edge(flex_2017_ids[0], "نظام العمل المرن (2024) يحل محل النظام السابق (2017)", force_type="repeals")

        item["relations"] = rels
        updated.append(item)

    if isinstance(raw, dict):
        raw["articles"] = updated
        LEG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        LEG_PATH.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Logical relations updated! Articles: {len(updated)} | Total edges: {total_edges} | By type: {counts}")


if __name__ == "__main__":
    main()
