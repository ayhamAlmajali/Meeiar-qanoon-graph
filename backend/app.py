import os
from pathlib import Path
import tempfile
from typing import Any, Literal

import hmac
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai_ingest import (
    extract_text_from_file,
    ingest_document,
    rebuild_all_embeddings,
)
from graph_engine import PROJECT_ROOT, QanoonGraphEngine, enrich_article_with_source, load_legislations
from llm_client import generate_json

try:
    from reranker import rerank_articles
except Exception:
    rerank_articles = None  # type: ignore

RoleType = Literal["citizen", "lawyer", "legislator"]

app = FastAPI(title="معيار - محرك التحليل التشريعي", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ENGINE_CACHE: dict[str, Any] = {
    "mtime": 0.0,
    "engine": None,
}


class AskRequest(BaseModel):
    question: str
    role: RoleType = "lawyer"


class AuditRequest(BaseModel):
    clause_text: str
    mode: Literal["contract", "draft"] = "contract"
    role: RoleType = "lawyer"


class IngestTextRequest(BaseModel):
    source_name: str
    raw_text: str


def get_engine() -> QanoonGraphEngine:
    leg_path = PROJECT_ROOT / "data" / "legislations.json"
    mtime = leg_path.stat().st_mtime if leg_path.exists() else 0.0
    if _ENGINE_CACHE["engine"] is None or _ENGINE_CACHE["mtime"] != mtime:
        _ENGINE_CACHE["engine"] = QanoonGraphEngine(load_legislations())
        _ENGINE_CACHE["mtime"] = mtime
    return _ENGINE_CACHE["engine"]



def verify_admin_access(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    expected_key = os.environ.get("ADMIN_API_KEY", "").strip()
    require_key = os.environ.get("REQUIRE_ADMIN_KEY", "false").strip().lower() in {"1", "true", "yes"}
    if not expected_key:
        if require_key:
            raise HTTPException(
                status_code=503,
                detail="مسارات التعديل مغلقة: لم يتم تهيئة ADMIN_API_KEY على الخادم.",
            )
        return
    if not x_admin_key or not hmac.compare_digest(x_admin_key.strip(), expected_key):
        raise HTTPException(status_code=401, detail="غير مصرح بتنفيذ عمليات تعديل البيانات (X-Admin-Key غير صالح).")


def _validate_audit_llm_output(parsed: Any, referenced: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ValueError("استجابة النموذج ليست كائن JSON صالح.")

    allowed_statuses = {"compliant", "non_compliant", "partial_conflict", "insufficient_evidence", "out_of_scope"}
    raw_status = str(parsed.get("compliance_status") or "").strip()
    status = raw_status if raw_status in allowed_statuses else "partial_conflict"

    allowed_risks = {"low", "medium", "high", "unknown"}
    raw_risk = str(parsed.get("risk_level") or "").strip().lower()
    risk = raw_risk if raw_risk in allowed_risks else ("unknown" if status in {"insufficient_evidence", "out_of_scope"} else "medium")

    raw_violated = parsed.get("violated_articles")
    if isinstance(raw_violated, list):
        violated = [str(item).strip() for item in raw_violated if str(item).strip()]
    elif isinstance(raw_violated, str) and raw_violated.strip():
        violated = [raw_violated.strip()]
    else:
        violated = []

    summary = str(parsed.get("summary") or "").strip()
    reasoning = str(parsed.get("legal_reasoning") or "").strip()
    if not summary and not reasoning:
        raise ValueError("استجابة النموذج تفتقر إلى الخلاصة والتعليل القانوني.")

    default_labels = {
        "compliant": "مطابق للقانون",
        "non_compliant": "مخالف / باطل قانوناً",
        "partial_conflict": "يحتاج مراجعة أو تعديل صياغي",
        "insufficient_evidence": "عدم كفاية النصوص المفهرسة للحكم",
        "out_of_scope": "خارج نطاق التشريعات المفهرسة",
    }
    status_label = str(parsed.get("status_label") or "").strip() or default_labels[status]
    rewrite = str(parsed.get("suggested_rewrite") or "").strip()
    if status in {"compliant", "insufficient_evidence", "out_of_scope"}:
        rewrite = ""

    return {
        "compliance_status": status,
        "status_label": status_label,
        "risk_level": risk,
        "summary": summary or reasoning[:240],
        "violated_articles": violated if status not in {"insufficient_evidence", "out_of_scope"} else [],
        "legal_reasoning": reasoning or summary,
        "suggested_rewrite": rewrite,
        "referenced_articles": referenced if status not in {"insufficient_evidence", "out_of_scope"} else [],
    }


def _role_style_note(role: RoleType) -> str:
    if role == "citizen":
        return (
            "خاطب المستخدم بلغة عربية واضحة ومباشرة ومبسطة بعيدة عن المصطلحات القانونية المعقدة، "
            "وركّز على حقوقه والتزاماته العملية."
        )
    if role == "legislator":
        return (
            "خاطب المستخدم بلغة تشريعية ومؤسسية دقيقة، وركّز على التعارضات التشريعية، "
            "أثر التعديل أو الإلغاء، والاتساق مع المنظومة القانونية."
        )
    return (
        "خاطب المستخدم بلغة قانونية مهنية دقيقة مع ذكر أرقام المواد، أسماء التشريعات، "
        "والتعليل القانوني الموثق."
    )


@app.get("/")
def root() -> dict:
    return {"name": "معيار", "status": "running", "docs": "/docs"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/graph/summary")
def summary() -> dict:
    return get_engine().get_summary()


@app.get("/graph")
def graph(
    limit: int = Query(default=180, ge=1, le=2000),
    legislation_title: str | None = Query(default=None),
) -> dict:
    return get_engine().to_graph_payload(limit=limit, legislation_title=legislation_title)


@app.get("/graph/changes")
def changes() -> dict:
    return get_engine().detect_conflicts_and_changes()


@app.get("/graph/impact/{node_id}")
def impact(node_id: str) -> dict:
    return get_engine().trace_impact_chain(node_id)


@app.get("/timeline/evolution")
def timeline_evolution(
    legislation_title: str | None = None,
    article_number: str | None = None,
) -> dict:
    clean_title = legislation_title if isinstance(legislation_title, str) else None
    clean_article = article_number if isinstance(article_number, str) else None
    return get_engine().get_legislation_evolution(
        legislation_title=clean_title,
        article_number=clean_article,
    )


@app.get("/articles")
def articles(q: str = Query(default="")) -> list[dict]:
    return [enrich_article_with_source(a) for a in get_engine().search_articles(q)]


@app.get("/articles/{identifier}")
def article_detail(identifier: str) -> dict:
    engine = get_engine()
    art = engine.get_article_by_id_or_number(identifier)
    if not art:
        raise HTTPException(status_code=404, detail="المادة غير موجودة")
    return {
        "article": enrich_article_with_source(art),
        "neighbors": engine.adjacency.get(art["id"], []),
        "impact": engine.trace_impact_chain(art["id"]),
    }


@app.post("/ask")
def ask_conflict(payload: AskRequest) -> dict:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="يرجى إدخال سؤال قانوني")
    result = get_engine().analyze_legal_question(question, role=payload.role)
    if isinstance(result, dict):
        result["role"] = payload.role
    return result


@app.post("/audit")
def audit_clause_or_draft(payload: AuditRequest) -> dict[str, Any]:
    clause = payload.clause_text.strip()
    if not clause:
        raise HTTPException(status_code=400, detail="يرجى إدخال نص البند أو المسودة التشريعية")

    engine = get_engine()
    candidate_articles = engine.search_articles(clause, min_score=3.5)[:10]
    if not candidate_articles:
        candidate_articles = engine.search_articles(clause, min_score=2.0)[:6]

    if not candidate_articles:
        return {
            "mode": payload.mode,
            "role": payload.role,
            "compliance_status": "insufficient_evidence",
            "status_label": "لم يُعثر على مواد مطابقة في الفهرس الحالي",
            "risk_level": "unknown",
            "summary": "لم تُظهر نتائج البحث في النصوص المفهرسة حالياً مواد مطابقة بدرجة كافية لتدقيق هذا البند.",
            "violated_articles": [],
            "legal_reasoning": (
                "عدم العثور على تطابق نصي مباشر في الفهرس الحالي لا يُعدّ دليلاً قاطعاً على خروج الموضوع عن التشريع الأردني، "
                "لذلك لم يُصدر حكم امتثال آلي تجنباً لأي استنتاج غير مستند لنص."
            ),
            "suggested_rewrite": "",
            "referenced_articles": [],
        }

    if rerank_articles is not None:
        reranked = rerank_articles(clause, candidate_articles, top_k=5)
    else:
        reranked = [
            (art, round(max(0.20, 0.70 - idx * 0.08), 4))
            for idx, art in enumerate(candidate_articles[:5])
        ]
    reranked = [(art, sc) for art, sc in reranked if sc >= 0.25] or reranked[:2]

    context_blocks = []
    referenced = []
    for art, score in reranked:
        rels = art.get("relations", [])
        rel_notes = "; ".join(
            f"{r.get('relation_type')} -> {r.get('target_ref')}: {r.get('note', '')}" for r in rels
        )
        context_blocks.append(
            f"- [{art.get('legislation_title')} | مادة {art.get('article_number')} | الحالة: {art.get('status', 'ساري')} | دقة التطابق: {score}]: "
            f"{art.get('text')}\n  العلاقات في الرسم البياني: {rel_notes or 'لا يوجد'}"
        )
        enriched_art = enrich_article_with_source(art)
        referenced.append({
            "id": art["id"],
            "legislation_title": art.get("legislation_title"),
            "article_number": art.get("article_number"),
            "status": art.get("status", "ساري"),
            "similarity": score,
            "source_label": enriched_art.get("source_label"),
            "source_url": enriched_art.get("source_url"),
        })

    role_instruction = (
        "أنت مدقق امتثال قانوني خبير في التشريعات الأردنية. قارن بند العقد أو اللائحة الداخلية التالي بالنصوص التشريعية المرفقة فقط، "
        "وطبق قاعدة 'النص الأعلى حماية للعامل' (كل شرط ينتقص من حقوق العامل المقررة قانوناً يعد باطلاً). "
        "إذا كان موضوع البند خارج نطاق النصوص المرفقة كلياً، أرجع compliance_status = out_of_scope."
        if payload.mode == "contract"
        else "أنت مستشار صياغة تشريعية. افحص مسودة المادة التشريعية المقترحة التالية قبل إقرارها وحدد مدى تعارضها أو تداخلها مع النصوص السارية المرفقة فقط. "
        "إذا كان موضوع المسودة خارج نطاق النصوص المرفقة كلياً، أرجع compliance_status = out_of_scope."
    )

    prompt = f"""
{role_instruction}
{_role_style_note(payload.role)}
التزم حصراً بالنصوص التشريعية المرفقة أدناه ولا تختلق أي رقم مادة غير مذكور فيها.

النص المراد تدقيقه:
\"\"\"{clause}\"\"\"

النصوص التشريعية المرجعية المسترجعة من قاعدة البيانات:
{chr(10).join(context_blocks)}

أرجع JSON صالح فقط بالهيكل التالي:
{{
  "compliance_status": "compliant أو non_compliant أو partial_conflict أو out_of_scope",
  "status_label": "مطابق للقانون أو مخالف / باطل قانوناً أو يحتاج تعديل صياغي أو خارج نطاق التشريعات المفهرسة",
  "risk_level": "low أو medium أو high أو unknown",
  "summary": "خلاصة تنفيذية واضحة من سطرين بالعربية تذكر اسم التشريع ورقم المادة المستند إليها",
  "violated_articles": ["اسم التشريع ورقم المادة التي تتعارض مع النص إن وجدت"],
  "legal_reasoning": "التعليل القانوني الدقيق المستند للنصوص المرفقة وعلاقات التعديل أو التداخل في الرسم البياني",
  "suggested_rewrite": "صياغة بديلة مقترحة سليمة قانونياً ومطابقة للتشريعات (أو اتركها فارغة إذا كان النص مطابقاً أو خارج النطاق)"
}}
"""

    try:
        parsed = generate_json(prompt, temperature=0.1)
        validated = _validate_audit_llm_output(parsed, referenced)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"فشل التحليل أو التحقق من استجابة النموذج: {exc}") from exc

    return {
        "mode": payload.mode,
        "role": payload.role,
        **validated,
    }


@app.post("/ingest/text", dependencies=[Depends(verify_admin_access)])
def ingest_raw_text(payload: IngestTextRequest) -> dict:
    if not payload.raw_text.strip():
        raise HTTPException(status_code=400, detail="النص التشريعي فارغ")
    return ingest_document(payload.raw_text, payload.source_name.strip() or "مستند تشريعي مضاف")


@app.post("/ingest/file", dependencies=[Depends(verify_admin_access)])
async def ingest_uploaded_file(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "document.txt").suffix
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="حجم الملف يتجاوز الحد الأقصى المسموح به (10 ميجابايت)")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        raw_text = extract_text_from_file(tmp_path)
        return ingest_document(raw_text, file.filename or "مستند مرفوع")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@app.post("/embeddings/rebuild", dependencies=[Depends(verify_admin_access)])
def rebuild_embeddings_endpoint() -> dict:
    total = rebuild_all_embeddings()
    return {"status": "ok", "embedded_articles": total}