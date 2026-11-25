import { useState } from "react";
import { useApp } from "../context/AppContext";
import { usePageActions } from "../context/PageActionsContext";
import { api, getErrorMessage } from "../services/api";
import { Button, EmptyState, Icon, LoadingState, PageHeader, Panel, RelationBadge, StatusBadge } from "../components/common/UI";

const sampleQuestions = [
  "هل يحق لصاحب العمل تحويل عقدي لعمل مرن وتقليل حقوقي؟",
  "ما التزامات صاحب العمل إذا كان لديه 10 عمال فأكثر؟",
  "هل نظام العمل المرن 2017 ما زال سارياً أم ملغى؟",
  "كيف تُحسب إجازة الأمومة في العمل لبعض الوقت؟"
];

function engineDescription(mode) {
  const value = String(mode || "");
  const provider = value.match(/^(ollama|groq):(.+)$/i);
  if (provider) return { label: "تحليل ذكاء اصطناعي مبني على النصوص التشريعية", model: `${provider[1]} · ${provider[2]}` };
  if (value === "graph_semantic_reasoning") return { label: "محرك الاستدلال الدلالي المحلي" };
  if (value === "out_of_scope") return { label: "لا تتوفر مواد كافية للإجابة" };
  return value ? { label: "تحليل تشريعي", model: value } : { label: "تحليل تشريعي" };
}

function sourceLink(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.protocol === "http:" || url.protocol === "https:") return url.href;
  } catch {
    return null;
  }
  return null;
}

function EvidenceCard({ article, onOpen }) {
  const item = article && typeof article === "object" ? article : {};
  const url = sourceLink(item.official_source);
  return (
    <article className="evidence-card">
      <div className="evidence-title-row">
        <div><span className="eyebrow">مادة مستشهد بها</span><h3>{item.article_number != null ? `المادة ${item.article_number} — ` : ""}{item.legislation_title || "تشريع غير محدد"}</h3></div>
        <StatusBadge status={item.status} />
      </div>
      <p className="legal-excerpt" dir="rtl" lang="ar">{item.text || "لم يرد نص المادة ضمن نتيجة الخدمة."}</p>
      <div className="evidence-footer">
        {url ? <a href={url} target="_blank" rel="noopener noreferrer"><Icon name="external" size={15} />المصدر الرسمي</a>
          : item.official_source ? <span className="source-citation"><strong>المصدر الرسمي</strong>{item.official_source}</span>
            : <span className="muted-copy">المصدر الرسمي غير متاح</span>}
        {item.id && <button className="text-button" type="button" onClick={() => onOpen(item.id)}>فتح التفاصيل</button>}
      </div>
    </article>
  );
}

function RelationCard({ relation }) {
  const edge = relation && typeof relation === "object" ? relation : { relation_type: relation };
  return (
    <article className="relation-card">
      <div className="relation-card-top">
        <span>{edge.source_label || edge.source || "مادة مرتبطة"} ← {edge.target_label || edge.target || "مرجع تشريعي"}</span>
        <RelationBadge relation={edge.relation_type} />
      </div>
      {edge.note && <p>{edge.note}</p>}
    </article>
  );
}

export default function AskPage() {
  const { role } = useApp();
  const { openArticle } = usePageActions();
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [state, setState] = useState({ loading: false, error: "", copied: false });

  const submit = async (event) => {
    event?.preventDefault();
    const clean = question.trim();
    if (!clean || state.loading) return;
    setState({ loading: true, error: "", copied: false });
    setResult(null);
    try {
      setResult(await api.ask({ question: clean, role }));
      setState({ loading: false, error: "", copied: false });
    } catch (error) {
      setState({ loading: false, error: getErrorMessage(error), copied: false });
    }
  };

  const copyAnswer = async () => {
    const text = typeof result?.verdict === "string" ? result.verdict : "";
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setState((current) => ({ ...current, copied: true, error: "" }));
    } catch (error) {
      setState((current) => ({ ...current, error: getErrorMessage(error, "تعذّر النسخ من المتصفح.") }));
    }
  };

  const engine = result ? engineDescription(result.engine_mode) : null;
  const evidence = Array.isArray(result?.evidence_articles) ? result.evidence_articles : [];
  const relations = Array.isArray(result?.detected_relations) ? result.detected_relations : [];

  return (
    <>
      <PageHeader eyebrow="بحث قانوني مستند إلى قاعدة المعرفة" title="الاستعلام التشريعي" description="اطرح سؤالاً عن التشريعات الأردنية، وراجع النصوص والعلاقات التي أُرفقت مع التحليل." />
      <Panel className="workspace-panel">
        <div className="workspace-intro">
          <span className="workspace-icon"><Icon name="sparkle" size={23} /></span>
          <div><h2>مستشارك التشريعي</h2><p>الإجابة تفسير مساعد للنصوص المرفقة، وليست بديلاً عن مراجعة التشريع أو استشارة قانونية مختصة.</p></div>
        </div>
        <form className="question-form" onSubmit={submit}>
          <label htmlFor="legal-question">ما الذي تريد معرفته؟</label>
          <textarea id="legal-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="اكتب سؤالك التشريعي هنا..." rows={4} maxLength={1200} required disabled={state.loading} />
          <div className="form-meta"><span>{question.length.toLocaleString("ar")} / ١٢٠٠</span><Button type="submit" disabled={!question.trim() || state.loading} icon="ask">{state.loading ? "جارٍ تحليل السؤال..." : "تحليل السؤال"}</Button></div>
        </form>
        <div className="sample-area"><span className="field-label">أسئلة مقترحة</span><div className="chip-list">
          {sampleQuestions.map((sample) => <button key={sample} className="sample-chip" type="button" disabled={state.loading} onClick={() => setQuestion(sample)}>{sample}</button>)}
        </div></div>
        {state.error && <div className="inline-error" role="alert">{state.error}</div>}
        {state.loading && <LoadingState label="جارٍ البحث في المواد وتحليل العلاقات..." />}
      </Panel>

      {result && (
        <Panel className="answer-panel" aria-live="polite">
          <div className="answer-header">
            <div><p className="eyebrow">نتيجة الاستعلام</p><h2>التحليل التشريعي</h2></div>
            <div className="answer-actions">
              <span className={`conflict-indicator ${result.has_conflict_or_overlap ? "conflict-yes" : "conflict-no"}`}><span />{result.has_conflict_or_overlap ? "رُصدت علاقة أو حالة تداخل" : "لم ترصد الخدمة علاقة تعارض"}</span>
              <Button variant="secondary" icon="copy" onClick={copyAnswer}>{state.copied ? "تم النسخ" : "نسخ الإجابة"}</Button>
              <Button variant="quiet" onClick={() => { setResult(null); setQuestion(""); setState({ loading: false, error: "", copied: false }); }}>استعلام جديد</Button>
            </div>
          </div>
          <div className="engine-note"><Icon name="sparkle" size={17} /><span>{engine?.label}</span>{engine?.model && <bdi dir="ltr">{engine.model}</bdi>}</div>
          <div className="legal-disclaimer"><Icon name="shield" size={18} /><span>التفسير أدناه مستند إلى المواد التي أعادتها الخدمة. النص القانوني المعروض أدلة مرجعية منفصلة عن صياغة التحليل.</span></div>
          <section className="answer-section"><h3>الخلاصة</h3><div className="answer-text" dir="rtl">{result.verdict || "لم ترد خلاصة من الخدمة."}</div></section>
          <div className="answer-columns">
            <section className="answer-section"><div className="section-heading"><h3>المواد المستند إليها</h3><span className="count-pill">{evidence.length.toLocaleString("ar")}</span></div>
              {evidence.length ? <div className="stack-list">{evidence.map((article, index) => <EvidenceCard key={article.id || index} article={article} onOpen={openArticle} />)}</div> : <EmptyState title="لم تُرفق مواد مستشهد بها" description="لا تعرض الخدمة مواد مرجعية لهذا السؤال." />}
            </section>
            <section className="answer-section"><div className="section-heading"><h3>العلاقات التشريعية المرصودة</h3><span className="count-pill">{relations.length.toLocaleString("ar")}</span></div>
              {relations.length ? <div className="stack-list">{relations.map((relation, index) => <RelationCard key={index} relation={relation} />)}</div> : <EmptyState title="لا توجد علاقات مرفقة" description="لم تُرجع الخدمة علاقات مرتبطة بالسؤال." />}
            </section>
          </div>
        </Panel>
      )}
    </>
  );
}
