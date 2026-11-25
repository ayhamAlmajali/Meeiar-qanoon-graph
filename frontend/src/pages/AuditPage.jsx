import { useState } from "react";
import { api, getErrorMessage } from "../services/api";
import { Button, EmptyState, Icon, LoadingState, OfficialSource, PageHeader, Panel, SimilarityBadge, StatusBadge } from "../components/common/UI";

const contractSample = "يحق لصاحب العمل منفرداً تحويل عقد العامل الدائم إلى نظام العمل المرن وتخفيض أجره بما يتناسب مع ساعات العمل دون الحاجة لموافقة العامل الخطية.";
const draftSample = "يلتزم صاحب العمل بتطبيق نظام العمل المرن على كافة العاملين دون الحاجة لموافقة خطية أو اتفاق مسبق.";

const statusInfo = {
  compliant: ["مطابق للقانون", "assessment-success"],
  non_compliant: ["مخالف / باطل قانوناً", "assessment-danger"],
  partial_conflict: ["يحتاج تعديل صياغي", "assessment-warning"],
  insufficient_evidence: ["عدم كفاية الأدلة الموثقة للحكم", "assessment-neutral"],
  out_of_scope: ["خارج نطاق التشريعات المفهرسة", "assessment-neutral"]
};

const riskLabels = { low: "منخفض", medium: "متوسط", high: "مرتفع", unknown: "غير محدد" };

function asList(value) {
  if (Array.isArray(value)) return value;
  return value == null || value === "" ? [] : [value];
}

function textValue(value) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map((item) => typeof item === "string" ? item : item?.text || item?.label || JSON.stringify(item)).join("\n");
  if (value && typeof value === "object") return value.text || value.summary || value.description || JSON.stringify(value);
  return "";
}

export default function AuditPage() {
  const [mode, setMode] = useState("contract");
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [state, setState] = useState({ loading: false, error: "", copied: false });

  const submit = async (event) => {
    event.preventDefault();
    const clause = text.trim();
    if (!clause || state.loading) return;
    setState({ loading: true, error: "", copied: false });
    setResult(null);
    try {
      setResult(await api.audit({ clause_text: clause, mode }));
      setState({ loading: false, error: "", copied: false });
    } catch (error) {
      setState({ loading: false, error: getErrorMessage(error), copied: false });
    }
  };

  const selectMode = (nextMode) => {
    setMode(nextMode);
    setResult(null);
    setState({ loading: false, error: "", copied: false });
  };

  const copyRewrite = async () => {
    const rewrite = textValue(result?.suggested_rewrite);
    if (!rewrite) return;
    try {
      await navigator.clipboard.writeText(rewrite);
      setState((current) => ({ ...current, copied: true, error: "" }));
    } catch (error) {
      setState((current) => ({ ...current, error: getErrorMessage(error, "تعذّر النسخ من المتصفح.") }));
    }
  };

  const rawStatus = String(result?.compliance_status || "").toLowerCase();
  const [fallbackLabel, statusClass] = statusInfo[rawStatus] || ["حالة غير محددة", "assessment-neutral"];
  const violated = asList(result?.violated_articles);
  const references = asList(result?.referenced_articles);

  return (
    <>
      <PageHeader eyebrow="مراجعة النص قبل اعتماده" title="مدقق الامتثال والمسودات" description="قارن بنداً أو مسودة بما أرجعته قاعدة المعرفة من مواد تشريعية، واطّلع على التعليل والمراجع." />
      <Panel className="workspace-panel audit-workspace">
        <div className="mode-tabs" role="group" aria-label="نمط التدقيق">
          <button type="button" className={mode === "contract" ? "mode-tab active" : "mode-tab"} aria-pressed={mode === "contract"} disabled={state.loading} onClick={() => selectMode("contract")}><Icon name="book" size={18} />تدقيق بند عقد / لائحة</button>
          <button type="button" className={mode === "draft" ? "mode-tab active" : "mode-tab"} aria-pressed={mode === "draft"} disabled={state.loading} onClick={() => selectMode("draft")}><Icon name="audit" size={18} />فحص مسودة تشريع</button>
        </div>
        <form className="question-form" onSubmit={submit}>
          <label htmlFor="audit-text">{mode === "contract" ? "نص البند أو اللائحة" : "نص المادة المقترحة"}</label>
          <textarea id="audit-text" value={text} onChange={(event) => setText(event.target.value)} rows={8} required disabled={state.loading} placeholder={mode === "contract" ? "أدخل بند العقد المراد مراجعته..." : "أدخل المادة المقترحة في المسودة..."} />
          <div className="sample-area"><span className="field-label">ابدأ بمثال</span><div className="chip-list">
            <button type="button" className="sample-chip" disabled={state.loading} onClick={() => { selectMode("contract"); setText(contractSample); }}>مثال بند عقد</button>
            <button type="button" className="sample-chip" disabled={state.loading} onClick={() => { selectMode("draft"); setText(draftSample); }}>مثال مسودة</button>
          </div></div>
          <div className="form-meta"><span>{mode === "contract" ? "المراجعة موجهة للعقود واللوائح الداخلية" : "المراجعة موجهة لمسودات التشريعات"}</span><Button type="submit" icon="audit" disabled={!text.trim() || state.loading}>{state.loading ? "جارٍ إجراء المراجعة..." : "ابدأ التدقيق"}</Button></div>
        </form>
        {state.error && <div className="inline-error" role="alert">{state.error}</div>}
        {state.loading && <LoadingState label="جارٍ مقارنة النص بالمواد التشريعية..." />}
      </Panel>

      {result && (
        <Panel className="audit-results" aria-live="polite">
          <div className="assessment-header">
            <div><p className="eyebrow">نتيجة المراجعة</p><h2>{result.status_label || fallbackLabel}</h2></div>
            <div className={`assessment-badge ${statusClass}`}><Icon name={rawStatus === "compliant" ? "check" : rawStatus === "non_compliant" ? "alert" : "shield"} size={19} /><span>{result.status_label || fallbackLabel}</span></div>
          </div>
          <div className="assessment-meta"><span>النمط: {result.mode === "draft" ? "مسودة تشريع" : result.mode === "contract" ? "بند عقد / لائحة" : mode === "draft" ? "مسودة تشريع" : "بند عقد / لائحة"}</span>{result.risk_level && <span>مستوى المخاطر: {riskLabels[result.risk_level] || result.risk_level}</span>}</div>
          <section className="result-block assessment-summary"><h3>الخلاصة التنفيذية</h3><p>{textValue(result.summary) || "لم ترد خلاصة تنفيذية في نتيجة الخدمة."}</p></section>
          {violated.length > 0 && <section className="result-block"><h3>المواد المتعارضة أو المنتهكة</h3><div className="reference-list">{violated.map((item, index) => <article className="finding-card" key={index}><Icon name="alert" size={18} /><span>{typeof item === "string" ? item : item.legislation_title ? `${item.legislation_title} — المادة ${item.article_number ?? ""}` : item.text || item.label || JSON.stringify(item)}</span>{item?.status && <StatusBadge status={item.status} />}</article>)}</div></section>}
          <section className="result-block"><h3>التعليل القانوني</h3><p className="result-prose">{textValue(result.legal_reasoning) || "لم يرد تعليل قانوني في نتيجة الخدمة."}</p></section>
          {textValue(result.suggested_rewrite) && <section className="rewrite-card"><div className="section-heading"><div><p className="eyebrow">صياغة بديلة مقترحة</p><h3>مراجعة الصياغة</h3></div><Button variant="secondary" icon={state.copied ? "check" : "copy"} onClick={copyRewrite}>{state.copied ? "تم النسخ" : "نسخ الصياغة"}</Button></div><p>{textValue(result.suggested_rewrite)}</p></section>}
          <section className="result-block"><div className="section-heading"><h3>المواد التشريعية المرجعية</h3><span className="count-pill">{references.length.toLocaleString("ar")}</span></div>
            {references.length ? <div className="reference-list">{references.map((article, index) => {
              const item = typeof article === "object" && article !== null ? article : {};
              return <article className="reference-card" key={item.id || index}>
                <div><strong>{item.legislation_title || item.title || "تشريع غير محدد"}</strong><span>المادة {item.article_number ?? "—"}</span></div>
                <div className="reference-card-meta"><StatusBadge status={item.status} /><SimilarityBadge article={item} /></div>
                <OfficialSource sourceUrl={item.source_url} sourceLabel={item.source_label} officialSource={item.official_source} />
              </article>;
            })}</div> : <EmptyState title="لا توجد مواد مرجعية مرفقة" description="لم تُرجع الخدمة مواد مرجعية لهذا النص." />}
          </section>
        </Panel>
      )}
    </>
  );
}
