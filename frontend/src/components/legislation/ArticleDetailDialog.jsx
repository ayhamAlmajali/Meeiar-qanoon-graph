import { useEffect, useRef, useState } from "react";
import { api, getErrorMessage } from "../../services/api";
import {
  Button,
  EmptyState,
  Icon,
  legislationTypeLabel,
  LoadingState,
  OfficialSource,
  RelationBadge,
  SimilarityBadge,
  StatusBadge
} from "../common/UI";

function topicList(tags) {
  if (Array.isArray(tags)) return tags.filter(Boolean);
  if (typeof tags === "string") return tags.split(/[،,]/).map((tag) => tag.trim()).filter(Boolean);
  return [];
}

export default function ArticleDetailDialog({ identifier, onClose, onOpenArticle }) {
  const [state, setState] = useState({ loading: false, data: null, error: "" });
  const [history, setHistory] = useState([]);
  const [copied, setCopied] = useState(false);
  const previousIdentifierRef = useRef(null);

  useEffect(() => {
    if (!identifier) {
      setHistory([]);
      previousIdentifierRef.current = null;
      return;
    }
    const prev = previousIdentifierRef.current;
    if (prev && prev !== identifier) {
      setHistory((curr) => (curr[curr.length - 1] === prev ? curr : [...curr, prev]));
    }
    previousIdentifierRef.current = identifier;
    setCopied(false);
  }, [identifier]);

  useEffect(() => {
    if (!identifier) return undefined;
    const controller = new AbortController();
    setState({ loading: true, data: null, error: "" });
    api.article(identifier, { signal: controller.signal })
      .then((data) => setState({ loading: false, data, error: "" }))
      .catch((error) => {
        if (error?.name !== "AbortError") {
          setState({ loading: false, data: null, error: getErrorMessage(error) });
        }
      });
    return () => controller.abort();
  }, [identifier]);

  useEffect(() => {
    if (!identifier) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [identifier, onClose]);

  if (!identifier) return null;
  const article = state.data?.article;
  const neighbors = Array.isArray(state.data?.neighbors) ? state.data.neighbors : [];

  const handleBack = () => {
    if (!history.length) return;
    const previous = history[history.length - 1];
    setHistory((curr) => curr.slice(0, -1));
    previousIdentifierRef.current = null;
    onOpenArticle(previous);
  };

  const copyText = async () => {
    if (!article?.text) return;
    try {
      await navigator.clipboard.writeText(article.text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section className="article-dialog" role="dialog" aria-modal="true" aria-labelledby="article-dialog-title" dir="rtl">
        <header className="dialog-header">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-1">
              {history.length > 0 && (
                <button type="button" className="text-button !px-2 !py-0.5 border border-slate-200 bg-white" onClick={handleBack}>
                  <Icon name="arrowRight" size={13} />
                  <span>رجوع</span>
                </button>
              )}
              <p className="eyebrow !m-0">ملف المادة التشريعية</p>
            </div>
            <h2 id="article-dialog-title">
              {article ? `المادة ${article.article_number} — ${article.legislation_title}` : "تفاصيل المادة"}
            </h2>
          </div>
          <div className="dialog-header-actions">
            {article?.text && (
              <Button variant="secondary" size="sm" icon={copied ? "check" : "copy"} onClick={copyText}>
                {copied ? "تم النسخ" : "نسخ النص"}
              </Button>
            )}
            <Button variant="icon" icon="close" aria-label="إغلاق" onClick={onClose} />
          </div>
        </header>

        <div className="dialog-body">
          {state.loading ? (
            <LoadingState label="جارٍ تحميل المادة وروابطها التشريعية..." />
          ) : state.error ? (
            <div className="inline-error" role="alert">
              <Icon name="alert" size={18} />
              <span>{state.error}</span>
            </div>
          ) : article ? (
            <>
              <div className="article-meta">
                {article.legislation_type && (
                  <span className="badge badge-neutral">{legislationTypeLabel(article.legislation_type)}</span>
                )}
                <StatusBadge status={article.status} />
                {article.effective_date && (
                  <span className="badge badge-neutral">
                    <Icon name="calendar" size={13} />
                    <bdi dir="ltr">{article.effective_date}</bdi>
                  </span>
                )}
                <SimilarityBadge article={article} showMeter />
              </div>

              {topicList(article.topic_tags).length > 0 && (
                <div className="tag-list">
                  {topicList(article.topic_tags).map((tag) => (
                    <span className="topic-tag" key={tag}>{tag}</span>
                  ))}
                </div>
              )}

              <div className="legal-text" lang="ar" dir="rtl">
                {article.text || "لم يرد نص لهذه المادة في بيانات الخدمة."}
              </div>

              <OfficialSource
                className="source-row"
                sourceUrl={article.source_url}
                sourceLabel={article.source_label}
                officialSource={article.official_source}
              />

              <section className="dialog-related">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="!m-0">العلاقات التشريعية المرتبطة</h3>
                  <span className="count-pill">{neighbors.length.toLocaleString("ar")}</span>
                </div>
                {neighbors.length ? (
                  <div className="grid gap-1.5">
                    {neighbors.map((edge, index) => {
                      const neighborId = edge.source === article.id ? edge.target : edge.source;
                      const neighborLabel = edge.source === article.id
                        ? edge.target_label || edge.target
                        : edge.source_label || edge.source;
                      return (
                        <button
                          className="related-row"
                          key={`${edge.source}-${edge.target}-${index}`}
                          type="button"
                          onClick={() => onOpenArticle(neighborId)}
                        >
                          <span className="font-medium text-slate-800">{neighborLabel}</span>
                          <RelationBadge relation={edge.relation_type} />
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <EmptyState title="لا توجد علاقات مسجلة" description="لم تُرصد روابط مباشرة لهذه المادة في الرسم البياني." />
                )}
              </section>
            </>
          ) : null}
        </div>
      </section>
    </div>
  );
}
