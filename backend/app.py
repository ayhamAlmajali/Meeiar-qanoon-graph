import os
from pathlib import Path
import tempfile
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai_ingest import (
    extract_text_from_file,
    ingest_document,
    rebuild_all_embeddings,
)
from graph_engine import PROJECT_ROOT, QanoonGraphEngine, load_legislations
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


@app.get("/articles")
def articles(q: str = Query(default="")) -> list[dict]:
    return get_engine().search_articles(q)


@app.get("/articles/{identifier}")
def article_detail(identifier: str) -> dict:
    engine = get_engine()
    art = engine.get_article_by_id_or_number(identifier)
    if not art:
        raise HTTPException(status_code=404, detail="المادة غير موجودة")
    return {
        "article": art,
        "neighbors": engine.adjacency.get(art["id"], []),
        "impact": engine.trace_impact_chain(art["id"]),
    }


@app.post("/ask")
def ask_conflict(payload: AskRequest) -> dict:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="يرجى إدخال سؤال قانوني")
    result = get_engine().analyze_legal_question(question)
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
        return {
            "mode": payload.mode,
            "role": payload.role,
            "compliance_status": "out_of_scope",
            "status_label": "خارج نطاق التشريعات المفهرسة",
            "risk_level": "unknown",
            "summary": "لا تتضمن قاعدة التشريعات المفهرسة حالياً نصوصاً صريحة تحكم موضوع هذا البند.",
            "violated_articles": [],
            "legal_reasoning": "تجنباً لأي اجتهاد غير مستند لنص، لم يتم إصدار حكم امتثال لعدم توفر مادة مرجعية مطابقة.",
            "suggested_rewrite": "",
            "referenced_articles": [],
        }

    if rerank_articles is not None:
        reranked = rerank_articles(clause, candidate_articles, top_k=5)
    else:
        reranked = [(art, 0.85) for art in candidate_articles[:5]]

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
        referenced.append({
            "id": art["id"],
            "legislation_title": art.get("legislation_title"),
            "article_number": art.get("article_number"),
            "status": art.get("status", "ساري"),
            "similarity": score,
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"فشل التحليل عبر النموذج: {exc}") from exc

    return {
        "mode": payload.mode,
        "role": payload.role,
        "compliance_status": parsed.get("compliance_status", "partial_conflict"),
        "status_label": parsed.get("status_label", "يحتاج مراجعة قانونية"),
        "risk_level": parsed.get("risk_level", "medium"),
        "summary": parsed.get("summary", ""),
        "violated_articles": parsed.get("violated_articles", []),
        "legal_reasoning": parsed.get("legal_reasoning", ""),
        "suggested_rewrite": parsed.get("suggested_rewrite", ""),
        "referenced_articles": referenced if parsed.get("compliance_status") != "out_of_scope" else [],
    }


@app.post("/ingest/text")
def ingest_raw_text(payload: IngestTextRequest) -> dict:
    if not payload.raw_text.strip():
        raise HTTPException(status_code=400, detail="النص التشريعي فارغ")
    return ingest_document(payload.raw_text, payload.source_name.strip() or "مستند تشريعي مضاف")


@app.post("/ingest/file")
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


@app.post("/embeddings/rebuild")
def rebuild_embeddings_endpoint() -> dict:
    total = rebuild_all_embeddings()
    return {"status": "ok", "embedded_articles": total}