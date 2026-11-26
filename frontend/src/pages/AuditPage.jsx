import { useState } from "react";
import { usePageActions } from "../context/PageActionsContext";
import { api, getErrorMessage } from "../services/api";
import LegalProse from "../components/common/LegalProse";
import {
  Button,
  EmptyState,
  Icon,
  LoadingState,
  OfficialSource,
  PageHeader,
  Panel,
  SimilarityBadge,
  SkeletonCards,
  StatusBadge
} from "../components/common/UI";

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
  const { openArticle } = usePageActions();
  const [mode, setMode] = useState("contract");
  const [text, setText] = useState("");
  const [submittedClause, setSubmittedClause] = useState("");
  const [result, setResult] = useState(null);
  const [state, setState] = useState({ loading: false, error: "", copied: false });

  const submit = async (event) => {
    event?.preventDefault();
    const clause = text.trim();
    if (!clause || state.loading) return;
    setState({ loading: true, error: "", copied: false });
    setResult(null);
    setSubmittedClause(clause);
    try {
      setResult(await api.audit({ clause_text: clause, mode }));
      setState({ loading: false, error: "", copied: false });
    } catch (error) {
      setState({ loading: false, error: getErrorMessage(error), copied: false });
    }
  };

  const handleKeyDown = (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      if (text.trim() && !state.loading) {
        void submit();
      }
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
  const rewriteText = textValue(result?.suggested_rewrite);
  const riskKey = String(result?.risk_level || "").toLowerCase();

  return (
    <div className="animate-enter">
      <PageHeader
        eyebrow="مراجعة النص قبل اعتماده"
        title="مدقق الامتثال والمسودات"
        description="قارن بند عقد عمل أو مسودة نص تشريعي بالمواد السارية والقواعد الآمرة في قانون العمل الأردني، واحصل على تعليل موثّق وصياغة بديلة."
      />

      <Panel className="workspace-panel audit-workspace">
        <div className="audit-mode-grid" role="group" aria-label="نمط التدقيق">
          <button
            type="button"
            className={`audit-mode-card ${mode === "contract" ? "active" : ""}`}
            aria-pressed={mode === "contract"}
            disabled={state.loading}
            onClick={() => selectMode("contract")}
          >
            <span className="audit-mode-icon"><Icon name="book" size={20} /></span>
            <span>
              <strong>تدقيق بند عقد / لائحة داخلية</strong>
              <span>يفحص مطابقة الشرط للقواعد الآمرة ومبدأ النص الأعلى حماية للعامل.</span>
            </span>
          </button>

          <button
            type="button"
            className={`audit-mode-card ${mode === "draft" ? "active" : ""}`}
            aria-pressed={mode === "draft"}
            disabled={state.loading}
            onClick={() => selectMode("draft")}
          >
            <span className="audit-mode-icon"><Icon name="audit" size={20} /></span>
            <span>
              <strong>فحص مسودة تشريع</strong>
              <span>يتحقق من التعارض أو التداخل بين المادة المقترحة والنصوص السارية.</span>
            </span>
          </button>
        </div>

        <form className="question-form" onSubmit={submit}>
          <label htmlFor="audit-text">
            {mode === "contract" ? "نص البند أو اللائحة المراد تدقيقها" : "نص المادة المقترحة في المسودة"}
          </label>
          <div className="composer-box">
            <textarea
              id="audit-text"
              value={text}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={handleKeyDown}
              rows={6}
              required
              disabled={state.loading}
              placeholder={mode === "contract"
                ? "أدخل نص بند العقد أو اللائحة الداخلية المراد مراجعته..."
                : "أدخل نص المادة المقترحة في مسودة التشريع..."}
            />
            <div className="composer-footer">
              <div className="composer-meta-group">
                <span className="tabular-nums">{text.length.toLocaleString("ar")} حرف</span>
                <span className="kbd-hint" dir="ltr">Ctrl + Enter</span>
              </div>
              <div className="composer-actions">
                {text && !state.loading && (
                  <Button type="button" variant="quiet" size="sm" onClick={() => setText("")}>
                    مسح النص
                  </Button>
                )}
                <Button type="submit" icon="audit" disabled={!text.trim() || state.loading}>
                  {state.loading ? "جارٍ إجراء التدقيق..." : "ابدأ التدقيق القانوني"}
                </Button>
              </div>
            </div>
          </div>

          <div className="sample-area">
            <span className="field-label">نماذج سريعة للاختبار</span>
            <div className="chip-list">
              <button
                type="button"
                className={`sample-chip ${text.trim() === contractSample ? "active-chip" : ""}`}
                disabled={state.loading}
                onClick={() => { selectMode("contract"); setText(contractSample); }}
              >
                <Icon name="book" size={14} />
                <span>مثال بند عقد (تحويل قسري للعمل المرن)</span>
              </button>
              <button
                type="button"
                className={`sample-chip ${text.trim() === draftSample ? "active-chip" : ""}`}
                disabled={state.loading}
                onClick={() => { selectMode("draft"); setText(draftSample); }}
              >
                <Icon name="audit" size={14} />
                <span>مثال مسودة تشريع</span>
              </button>
            </div>
          </div>
        </form>

        {state.error && (
          <div className="inline-error" role="alert">
            <Icon name="alert" size={18} />
            <span>{state.error}</span>
          </div>
        )}

        {state.loading && (
          <div className="mt-4 grid gap-3">
            <LoadingState label="جارٍ مقارنة النص بالمواد التشريعية والتحقق من الامتثال..." />
            <SkeletonCards count={2} />
          </div>
        )}
      </Panel>

      {result && (
        <Panel className="audit-results animate-enter" aria-live="polite">
          <div className={`assessment-banner ${statusClass}`}>
            <div className="assessment-header-copy">
              <p className="eyebrow !mb-1">نتيجة التدقيق القانوني</p>
              <h2>{result.status_label || fallbackLabel}</h2>
            </div>
            <div className={`assessment-badge ${statusClass}`}>
              <Icon
                name={rawStatus === "compliant" ? "check" : rawStatus === "non_compliant" ? "alert" : "shield"}
                size={19}
              />
              <span>{result.status_label || fallbackLabel}</span>
            </div>
          </div>

          <div className="assessment-meta">
            <span className="meta-pill">
              <Icon name="book" size={14} />
              <span>
                النمط: {result.mode === "draft" ? "مسودة تشريع" : result.mode === "contract" ? "بند عقد / لائحة" : mode === "draft" ? "مسودة تشريع" : "بند عقد / لائحة"}
              </span>
            </span>
            {result.risk_level && (
              <span className="meta-pill">
                <span>مستوى المخاطر: <strong>{riskLabels[riskKey] || result.risk_level}</strong></span>
                {["low", "medium", "high"].includes(riskKey) && (
                  <span className={`risk-dots risk-${riskKey}`} aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </span>
                )}
              </span>
            )}
            <span className="meta-pill">
              <span>المراجع المفحوصة: <strong>{references.length.toLocaleString("ar")}</strong></span>
            </span>
          </div>

          <section className="result-block assessment-summary">
            <h3>الخلاصة التنفيذية</h3>
            <p>{textValue(result.summary) || "لم ترد خلاصة تنفيذية في نتيجة الخدمة."}</p>
          </section>

          {violated.length > 0 && (
            <section className="result-block">
              <div className="section-heading !mb-3">
                <h3>المواد المتعارضة أو المنتهكة</h3>
                <span className="count-pill">{violated.length.toLocaleString("ar")}</span>
              </div>
              <div className="reference-list">
                {violated.map((item, index) => (
                  <article className="finding-card" key={index}>
                    <Icon name="alert" size={18} />
                    <span>
                      {typeof item === "string"
                        ? item
                        : item.legislation_title
                          ? `${item.legislation_title} — المادة ${item.article_number ?? ""}`
                          : item.text || item.label || JSON.stringify(item)}
                    </span>
                    {item?.status && <StatusBadge status={item.status} />}
                  </article>
                ))}
              </div>
            </section>
          )}

          <section className="result-block">
            <h3>التعليل القانوني</h3>
            <div className="rounded-xl border border-slate-200 bg-[#fbfaf7] p-5">
              {textValue(result.legal_reasoning) ? (
                <LegalProse text={textValue(result.legal_reasoning)} />
              ) : (
                <p className="muted-copy !m-0">لم يرد تعليل قانوني في نتيجة الخدمة.</p>
              )}
            </div>
          </section>

          {rewriteText && (
            <section className="rewrite-card">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">تصحيح الامتثال المقترح</p>
                  <h3>الصياغة البديلة المتوافقة مع القانون</h3>
                </div>
                <Button variant="secondary" size="sm" icon={state.copied ? "check" : "copy"} onClick={copyRewrite}>
                  {state.copied ? "تم النسخ" : "نسخ الصياغة"}
                </Button>
              </div>
              <div className="rewrite-comparison-grid">
                {submittedClause && (
                  <div className="rewrite-pane original">
                    <span className="rewrite-pane-label">
                      <Icon name="alert" size={14} />
                      <span>النص المُدخل</span>
                    </span>
                    <p>{submittedClause}</p>
                  </div>
                )}
                <div className={`rewrite-pane suggested ${!submittedClause ? "col-span-full" : ""}`}>
                  <span className="rewrite-pane-label">
                    <Icon name="check" size={14} />
                    <span>الصياغة البديلة المقترحة</span>
                  </span>
                  <p>{rewriteText}</p>
                </div>
              </div>
            </section>
          )}

          <section className="result-block">
            <div className="section-heading">
              <div>
                <h3>المواد التشريعية المرجعية</h3>
                <p className="muted-copy">النصوص التي استند إليها المدقق مع درجة التشابه الدلالي</p>
              </div>
              <span className="count-pill">{references.length.toLocaleString("ar")}</span>
            </div>
            {references.length ? (
              <div className="reference-list">
                {references.map((article, index) => {
                  const item = typeof article === "object" && article !== null ? article : {};
                  return (
                    <article className="reference-card" key={item.id || index}>
                      <div>
                        <strong>{item.legislation_title || item.title || "تشريع غير محدد"}</strong>
                        <span>المادة {item.article_number ?? "—"}</span>
                      </div>
                      <div className="reference-card-meta">
                        <StatusBadge status={item.status} />
                        <SimilarityBadge article={item} showMeter />
                      </div>
                      <div className="reference-card-footer">
                        <OfficialSource
                          sourceUrl={item.source_url}
                          sourceLabel={item.source_label}
                          officialSource={item.official_source}
                        />
                        {item.id && (
                          <Button variant="secondary" size="sm" icon="book" onClick={() => openArticle(item.id)}>
                            عرض نص المادة
                          </Button>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <EmptyState title="لا توجد مواد مرجعية مرفقة" description="لم تُرجع الخدمة مواد مرجعية لهذا النص." />
            )}
          </section>
        </Panel>
      )}
    </div>
  );
}
