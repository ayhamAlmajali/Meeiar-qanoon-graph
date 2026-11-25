import json
import time
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8000"

ASK_BENCHMARK = [
    {
        "question": "كيف يُنظَّم عقد العمل ومدته وما هي ساعات العمل العادية والسلامة المهنية؟",
        "expected_ids": {
            "labor_1996_a15",
            "labor_1996_a56",
            "labor_1996_a78",
            "flex_2024_a5",
            "law_2019_art_2",
            "law_2019_art_39",
            "regulation_44_2024_art_2",
        },
    },
    {
        "question": "متى لا يجوز إنهاء خدمة العامل وما أحكام الإجازة السنوية والعمل الإضافي؟",
        "expected_ids": {
            "law_8_1996_art_27",
            "law_8_1996_art_61",
            "law_8_1996_art_59",
            "law_2019_art_23",
            "law_2019_art_25",
            "law_2019_art_27",
            "law_2019_art_62",
        },
    },
    {
        "question": "ما ضوابط العمل المرن وشروط عقده والتزامات الطرفين في نظام 2024؟",
        "expected_ids": {
            "flex_2024_a1",
            "flex_2024_a3",
            "flex_2024_a4",
            "flex_2024_a5",
            "regulation_44_2024_art_2",
            "regulation_44_2024_art_6",
            "regulation_44_2024_art_9",
        },
    },
]

AUDIT_BENCHMARK = [
    {
        "clause_text": "يحق لصاحب العمل إنهاء عقد العمل دون إشعار ودون سبب مشروع",
        "mode": "contract",
        "expected_status": "non_compliant",
    },
    {
        "clause_text": "يستحق العامل إجازة سنوية مدفوعة الأجر وفق أحكام قانون العمل الأردني",
        "mode": "contract",
        "expected_status": "compliant",
    },
    {
        "clause_text": "تُحدَّد رسوم تسجيل السفن العابرة لقناة السويس بالدولار الأمريكي",
        "mode": "contract",
        "expected_status": "insufficient_evidence",
    },
]


def post_json(path: str, payload: dict) -> dict:
    time.sleep(3.0)
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def safe_div(num: float, den: float) -> float:
    return (num / den) if den > 0 else 0.0


def evaluate_ask() -> None:
    print("=== /ask Retrieval Evaluation (by Article ID) ===")
    precisions, recalls, f1s, cos_means = [], [], [], []

    for idx, case in enumerate(ASK_BENCHMARK, start=1):
        try:
            res = post_json("/ask", {"question": case["question"]})
        except urllib.error.URLError as exc:
            print(f"Case {idx} failed to connect: {exc}")
            continue

        evidence = res.get("evidence_articles") or []
        retrieved_ids = {
            str(item.get("id", "")).strip()
            for item in evidence
            if item.get("id")
        }
        expected = case["expected_ids"]
        tp = len(retrieved_ids & expected)

        p = safe_div(tp, len(retrieved_ids))
        r = safe_div(tp, len(expected))
        f1 = safe_div(2 * p * r, p + r)

        cos_vals = [
            float(item["cosine_similarity"])
            for item in evidence
            if isinstance(item.get("cosine_similarity"), (int, float))
        ]
        avg_cos = sum(cos_vals) / len(cos_vals) if cos_vals else 0.0

        precisions.append(p)
        recalls.append(r)
        f1s.append(f1)
        cos_means.append(avg_cos)

        print(
            f"  Q{idx}: P={p:.2f} | R={r:.2f} | F1={f1:.2f} | "
            f"AvgCos={avg_cos:.4f} | Hit={sorted(retrieved_ids & expected)} | Ret={sorted(retrieved_ids)}"
        )

    if f1s:
        print(
            f"Summary /ask -> Precision: {sum(precisions)/len(precisions):.2f}, "
            f"Recall: {sum(recalls)/len(recalls):.2f}, "
            f"F1: {sum(f1s)/len(f1s):.2f}, "
            f"AvgCos: {sum(cos_means)/len(cos_means):.4f}\n"
        )


def evaluate_audit() -> None:
    print("=== /audit Compliance Classification Evaluation ===")
    correct = 0
    total = 0
    statuses = ["compliant", "non_compliant", "partial_conflict", "insufficient_evidence"]
    per_class = {s: {"tp": 0, "fp": 0, "fn": 0} for s in statuses}

    for idx, case in enumerate(AUDIT_BENCHMARK, start=1):
        try:
            res = post_json(
                "/audit",
                {"clause_text": case["clause_text"], "mode": case["mode"]},
            )
        except urllib.error.URLError as exc:
            print(f"Audit case {idx} failed to connect: {exc}")
            continue

        pred = str(res.get("compliance_status") or "unknown").strip()
        exp = case["expected_status"]
        total += 1
        if pred == exp:
            correct += 1
            if exp in per_class:
                per_class[exp]["tp"] += 1
        else:
            if pred in per_class:
                per_class[pred]["fp"] += 1
            if exp in per_class:
                per_class[exp]["fn"] += 1

        print(f"  Clause {idx}: Predicted={pred} | Expected={exp} | Match={pred == exp}")

    if total > 0:
        acc = correct / total
        f1_scores = []
        for s, c in per_class.items():
            p = safe_div(c["tp"], c["tp"] + c["fp"])
            r = safe_div(c["tp"], c["tp"] + c["fn"])
            if (c["tp"] + c["fp"] + c["fn"]) > 0:
                f1_scores.append(safe_div(2 * p * r, p + r))
        macro_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0
        print(f"Summary /audit -> Accuracy: {acc:.2f} ({correct}/{total}) | Macro-F1: {macro_f1:.2f}\n")


if __name__ == "__main__":
    evaluate_ask()
    evaluate_audit()
