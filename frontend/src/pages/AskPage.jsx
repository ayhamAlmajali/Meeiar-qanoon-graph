import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
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
  RelationBadge,
  SimilarityBadge,
  SkeletonCards,
  StatusBadge,
  validHttpUrl
} from "../components/common/UI";

const sampleQuestions = [
  { label: "العمل المرن وتقليل الحقوق", text: "هل يحق لصاحب العمل تحويل عقدي لعمل مرن وتقليل حقوقي؟" },
  { label: "التزامات الـ 10 عمال فأكثر", text: "ما التزامات صاحب العمل إذا كان لديه 10 عمال فأكثر؟" },
  { label: "سريان نظام العمل المرن 2017", text: "هل نظام العمل المرن 2017 ما زال سارياً أم ملغى؟" },
  { label: "إجازة الأمومة والعمل لبعض الوقت", text: "كيف تُحسب إجازة الأمومة في العمل لبعض الوقت؟" }
];

const HISTORY_KEY = "meeiar_ask_history_v1";

function loadHistory() {
  try {
    const raw = window.sessionStorage.getItem(HISTORY_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.slice(0, 5) : [];
  } catch {
    return [];
  }
}

function saveHistory(items) {
  try {
    window.sessionStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, 5)));
  } catch {
    // Ignore storage errors
  }
}

function engineDescription(mode) {
  const value = String(mode || "");
  const provider = value.match(/^(ollama|groq):(.+)$/i);
  if (provider) {
    return {
      label: "تحليل ذكاء اصطناعي مبني على النصوص التشريعية",
      model: `${provider[1]} · ${provider[2]}`
    };
  }
  if (value === "graph_semantic_reasoning") return { label: "محرك الاستدلال الدلالي المحلي" };
  if (value === "out_of_scope" || value === "insufficient_evidence") {
    return { label: "لا تتوفر مواد كافية في الفهرس للإجابة" };
  }
  return value ? { label: "تحليل تشريعي", model: value } : { label: "تحليل تشريعي" };
}

function sourceKeys(source) {
  const keys = [];
  if (source.url) {
    const url = new URL(source.url);
    url.hash = "";
    url.searchParams.sort();
    keys.push(`url:${url.origin}${url.pathname.replace(/\/+$/, "")}${url.search}`);
  }
  const label = source.label.toLocaleLowerCase().replace(/\s+/g, " ");
  const title = source.legislation_title.toLocaleLowerCase().replace(/\s+/g, " ");
  if (label || title) keys.push(`text:${label}|${title}`);
  return keys;
}

function uniqueSources(value) {
  if (!Array.isArray(value)) return [];
  const sources = [];
  const sourceIndexes = new Map();
  value.forEach((item) => {
    if (!item || typeof item !== "object") return;
    const source = {
      label: typeof item.label === "string" ? item.label.trim() : "",
      legislation_title: typeof item.legislation_title === "string" ? item.legislation_title.trim() : "",
      url: validHttpUrl(item.url)
    };
    if (!source.label && !source.legislation_title && !source.url) return;
    const keys = sourceKeys(source);
    const existingIndex = keys.map((key) => sourceIndexes.get(key)).find((index) => index != null);
    if (existingIndex != null) {
      const existing = sources[existingIndex];
      if (!existing.label) existing.label = source.label;
      if (!existing.legislation_title) existing.legislation_title = source.legislation_title;
      if (!existing.url) existing.url = source.url;
      sourceKeys(existing).forEach((key) => sourceIndexes.set(key, existingIndex));
      keys.forEach((key) => sourceIndexes.set(key, existingIndex));
      return;
    }
    const index = sources.length;
    sources.push({ ...source, key: keys[0] || `source:${index}` });
    keys.forEach((key) => sourceIndexes.set(key, index));
  });
  return sources;
}

function EvidenceCard({ article, index, onOpen }) {
  const item = article && typeof article === "object" ? article : {};
  const text = item.text || "لم يرد نص المادة ضمن نتيجة الخدمة.";
  const isLong = text.length > 340;
  const [expanded, setExpanded] = useState(false);
  const [copiedExcerpt, setCopiedExcerpt] = useState(false);

  const copyExcerpt = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedExcerpt(true);
      window.setTimeout(() => setCopiedExcerpt(false), 1800);
    } catch {
      // Ignore clipboard failure
    }
  };

  return (
    <article className="evidence-card">
      <div className="evidence-title-row">
        <div className="min-w-0">
          <span className="eyebrow">دليل مرجعي #{(index + 1).toLocaleString("ar")}</span>
          <h3>
            {item.article_number != null ? `المادة ${item.article_number} — ` : ""}
            {item.legislation_title || "تشريع غير محدد"}
          </h3>
        </div>
        <div className="evidence-badges">
          <StatusBadge status={item.status} />
          <SimilarityBadge article={item} showMeter />
        </div>
      </div>

      <p className={`legal-excerpt ${isLong && !expanded ? "legal-excerpt-clamped" : ""}`} dir="rtl" lang="ar">
        {text}
      </p>

      <div className="evidence-footer">
        <OfficialSource
          className="evidence-source"
          sourceUrl={item.source_url}
          sourceLabel={item.source_label}
          officialSource={item.official_source}
        />
        <div className="evidence-actions">
          {isLong && (
            <button className="text-button" type="button" onClick={() => setExpanded((v) => !v)}>
              {expanded ? "عرض مختصر" : "قراءة النص كاملاً"}
            </button>
          )}
          <button className="text-button" type="button" onClick={copyExcerpt}>
            <Icon name={copiedExcerpt ? "check" : "copy"} size={14} />
            <span>{copiedExcerpt ? "نُسخ" : "نسخ"}</span>
          </button>
          {item.id && (
            <Button variant="secondary" size="sm" icon="book" onClick={() => onOpen(item.id)}>
              ملف المادة
            </Button>
          )}
        </div>
      </div>
    </article>
  );
}

function RelationCard({ relation, onOpen }) {
  const edge = relation && typeof relation === "object" ? relation : { relation_type: relation };
  const canOpenSource = Boolean(edge.source && !String(edge.source).includes(" "));
  const canOpenTarget = Boolean(edge.target && !String(edge.target).includes(" "));

  return (
    <article className="relation-card">
      <div className="relation-card-top">
        <div className="relation-flow">
          {canOpenSource ? (
            <button type="button" className="relation-node-btn" onClick={() => onOpen(edge.source)}>
              {edge.source_label || edge.source}
            </button>
          ) : (
            <span>{edge.source_label || edge.source || "مادة مرتبطة"}</span>
          )}
          <span className="text-slate-400">←</span>
          {canOpenTarget ? (
            <button type="button" className="relation-node-btn" onClick={() => onOpen(edge.target)}>
              {edge.target_label || edge.target}
            </button>
          ) : (
            <span>{edge.target_label || edge.target || "مرجع تشريعي"}</span>
          )}
        </div>
        <RelationBadge relation={edge.relation_type} />
      </div>
      {edge.note && <p>{edge.note}</p>}
    </article>
  );
}

export default function AskPage() {
  const { openArticle } = usePageActions();
  const [searchParams, setSearchParams] = useSearchParams();
  const [question, setQuestion] = useState(() => searchParams.get("q") || "");
  const [result, setResult] = useState(null);
  const [state, setState] = useState({ loading: false, error: "", copied: false });
  const [history, setHistory] = useState(loadHistory);
  const initialQueryTriggered = useRef(false);

  const runAsk = useCallback(async (rawQuestion) => {
    const clean = String(rawQuestion || "").trim();
    if (!clean) return;
    setState({ loading: true, error: "", copied: false });
    setResult(null);
    try {
      const response = await api.ask({ question: clean });
      setResult(response);
      setState({ loading: false, error: "", copied: false });
      setHistory((prev) => {
        const next = [clean, ...prev.filter((item) => item !== clean)].slice(0, 5);
        saveHistory(next);
        return next;
      });
    } catch (error) {
      setState({ loading: false, error: getErrorMessage(error), copied: false });
    }
  }, []);

  useEffect(() => {
    const initialQ = searchParams.get("q");
    if (initialQ && !initialQueryTriggered.current) {
      initialQueryTriggered.current = true;
      setQuestion(initialQ);
      setSearchParams({}, { replace: true });
      void runAsk(initialQ);
    }
  }, [searchParams, setSearchParams, runAsk]);

  const submit = (event) => {
    event?.preventDefault();
    if (state.loading) return;
    void runAsk(question);
  };

  const handleKeyDown = (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      if (question.trim() && !state.loading) {
        void runAsk(question);
      }
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

  const resetAll = () => {
    setResult(null);
    setQuestion("");
    setState({ loading: false, error: "", copied: false });
  };

  const engine = result ? engineDescription(result.engine_mode) : null;
  const evidence = Array.isArray(result?.evidence_articles) ? result.evidence_articles : [];
  const relations = Array.isArray(result?.detected_relations) ? result.detected_relations : [];
  const sources = uniqueSources(result?.sources);

  return (
    <div className="animate-enter">
      <PageHeader
        eyebrow="بحث قانوني مستند إلى قاعدة المعرفة"
        title="الاستعلام التشريعي"
        description="اطرح سؤالاً عن تشريعات العمل الأردنية، وراجع التحليل الموثّق منفصلاً بوضوح عن النصوص القانونية والعلاقات المرصودة."
      />

      <Panel className="workspace-panel">
        <div className="workspace-intro">
          <span className="workspace-icon"><Icon name="sparkle" size={22} /></span>
          <div>
            <h2>المستشار التشريعي الذكي</h2>
            <p>تُبنى الإجابة حصراً على المواد المسترجعة وعلاقات الرسم البياني؛ وهي تحليل مساعد لا يغني عن الاستشارة المختصة.</p>
          </div>
        </div>

        <form className="question-form" onSubmit={submit}>
          <label htmlFor="legal-question">نص السؤال التشريعي</label>
          <div className="composer-box">
            <textarea
              id="legal-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="مثال: هل يحق لصاحب العمل إنهاء عقد العامل أو تحويله للعمل المرن دون موافقته؟"
              rows={4}
              maxLength={1200}
              required
              disabled={state.loading}
            />
            <div className="composer-footer">
              <div className="composer-meta-group">
                <span className="tabular-nums">{question.length.toLocaleString("ar")} / ١٢٠٠ حرف</span>
                <span className="kbd-hint" dir="ltr">Ctrl + Enter</span>
              </div>
              <div className="composer-actions">
                {question && !state.loading && (
                  <Button type="button" variant="quiet" size="sm" onClick={() => setQuestion("")}>
                    مسح النص
                  </Button>
                )}
                <Button type="submit" disabled={!question.trim() || state.loading} icon="ask">
                  {state.loading ? "جارٍ تحليل السؤال..." : "تحليل السؤال"}
                </Button>
              </div>
            </div>
          </div>
        </form>

        <div className="sample-area">
          <span className="field-label">أسئلة مقترحة للتجربة الفورية</span>
          <div className="chip-list">
            {sampleQuestions.map((sample) => (
              <button
                key={sample.text}
                className={`sample-chip ${question.trim() === sample.text ? "active-chip" : ""}`}
                type="button"
                disabled={state.loading}
                onClick={() => setQuestion(sample.text)}
              >
                <Icon name="sparkle" size={14} />
                <span>{sample.text}</span>
              </button>
            ))}
          </div>
        </div>

        {history.length > 0 && (
          <div className="history-strip">
            <span className="history-strip-label">
              <Icon name="history" size={14} />
              <span>استعلامات الجلسة:</span>
            </span>
            {history.map((item) => (
              <button
                key={item}
                type="button"
                className="history-chip"
                disabled={state.loading}
                title={item}
                onClick={() => {
                  setQuestion(item);
                  void runAsk(item);
                }}
              >
                {item}
              </button>
            ))}
          </div>
        )}

        {state.error && (
          <div className="inline-error" role="alert">
            <Icon name="alert" size={18} />
            <span>{state.error}</span>
          </div>
        )}

        {state.loading && (
          <div className="mt-4 grid gap-3">
            <LoadingState label="جارٍ البحث الدلالي في المواد وتحليل روابط الرسم البياني..." />
            <SkeletonCards count={2} />
          </div>
        )}
      </Panel>

      {result && (
        <Panel className="answer-panel animate-enter" aria-live="polite">
          <div className="answer-header">
            <div>
              <p className="eyebrow">نتيجة الاستعلام الموثّق</p>
              <h2>التحليل التشريعي والأدلة</h2>
            </div>
            <div className="answer-actions">
              <span className={`conflict-indicator ${result.has_conflict_or_overlap ? "conflict-yes" : "conflict-no"}`}>
                <span />
                {result.has_conflict_or_overlap ? "رُصدت علاقة تعارض أو تداخل" : "لم يُرصد تعارض مباشر"}
              </span>
              <Button variant="secondary" size="sm" icon={state.copied ? "check" : "copy"} onClick={copyAnswer}>
                {state.copied ? "تم النسخ" : "نسخ الإجابة"}
              </Button>
              <Button variant="quiet" size="sm" onClick={resetAll}>استعلام جديد</Button>
            </div>
          </div>

          <div className="provenance-bar">
            <div className="engine-note">
              <Icon name="sparkle" size={16} />
              <span>{engine?.label}</span>
              {engine?.model && <bdi dir="ltr">{engine.model}</bdi>}
            </div>
            <div className="quick-jump-pills">
              <a className="jump-pill" href="#ask-evidence">
                <Icon name="book" size={14} />
                <span>{evidence.length.toLocaleString("ar")} مواد مستشهد بها</span>
              </a>
              <a className="jump-pill" href="#ask-relations">
                <Icon name="graph" size={14} />
                <span>{relations.length.toLocaleString("ar")} علاقات مرصودة</span>
              </a>
            </div>
          </div>

          <div className="legal-disclaimer">
            <Icon name="shield" size={18} />
            <span>
              يُفصل التحليل الاستنتاجي أدناه بوضوح عن النصوص القانونية الحرفية المرفقة في قسم الأدلة لتسهيل التحقق والمراجعة.
            </span>
          </div>

          <section className="answer-section">
            <h3>التحليل والخلاصة القانونية</h3>
            <div className="answer-text-card">
              {result.verdict ? (
                <LegalProse text={result.verdict} />
              ) : (
                <p className="muted-copy !m-0">لم ترد خلاصة من الخدمة.</p>
              )}
            </div>
          </section>

          <div className="answer-columns">
            <section className="answer-section" id="ask-evidence">
              <div className="section-heading">
                <div>
                  <h3>المواد القانونية المستند إليها</h3>
                  <p className="muted-copy">نصوص تشريعية فعلية مع درجة التشابه الدلالي</p>
                </div>
                <span className="count-pill">{evidence.length.toLocaleString("ar")}</span>
              </div>
              {evidence.length ? (
                <div className="stack-list">
                  {evidence.map((article, index) => (
                    <EvidenceCard key={article.id || index} article={article} index={index} onOpen={openArticle} />
                  ))}
                </div>
              ) : (
                <EmptyState title="لم تُرفق مواد مستشهد بها" description="لا تعرض الخدمة مواد مرجعية لهذا السؤال." />
              )}
            </section>

            <section className="answer-section" id="ask-relations">
              <div className="section-heading">
                <div>
                  <h3>العلاقات التشريعية المرصودة</h3>
                  <p className="muted-copy">روابط التعديل والإلغاء والتداخل في الرسم</p>
                </div>
                <span className="count-pill">{relations.length.toLocaleString("ar")}</span>
              </div>
              {relations.length ? (
                <div className="stack-list">
                  {relations.map((relation, index) => (
                    <RelationCard key={index} relation={relation} onOpen={openArticle} />
                  ))}
                </div>
              ) : (
                <EmptyState title="لا توجد علاقات مرفقة" description="لم تُرجع الخدمة علاقات مرتبطة بالسؤال." icon="graph" />
              )}
            </section>
          </div>

          {sources.length > 0 && (
            <details className="source-results" open={sources.length <= 4}>
              <summary>
                <span><Icon name="book" size={18} />المصادر والمراجع التشريعية الرسمية</span>
                <span className="count-pill">{sources.length.toLocaleString("ar")}</span>
              </summary>
              <div className="source-reference-list">
                {sources.map((source) => (
                  <article className="source-reference-card" key={source.key}>
                    <div className="source-reference-copy">
                      <strong>{source.legislation_title || "مرجع تشريعي"}</strong>
                      {source.label && <span>{source.label}</span>}
                    </div>
                    <OfficialSource className="source-reference-action" heading="" sourceUrl={source.url} />
                  </article>
                ))}
              </div>
            </details>
          )}
        </Panel>
      )}
    </div>
  );
}
