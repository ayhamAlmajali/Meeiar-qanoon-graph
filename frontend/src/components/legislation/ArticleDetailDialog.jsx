import { useEffect, useState } from "react";
import { api, getErrorMessage } from "../../services/api";
import { Button, EmptyState, legislationTypeLabel, LoadingState, OfficialSource, RelationBadge, StatusBadge } from "../common/UI";

function topicList(tags) {
  if (Array.isArray(tags)) return tags.filter(Boolean);
  if (typeof tags === "string") return tags.split(/[،,]/).map((tag) => tag.trim()).filter(Boolean);
  return [];
}

export default function ArticleDetailDialog({ identifier, onClose, onOpenArticle }) {
  const [state, setState] = useState({ loading: false, data: null, error: "" });

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

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="article-dialog" role="dialog" aria-modal="true" aria-labelledby="article-dialog-title" dir="rtl">
        <header className="dialog-header">
          <div><p className="eyebrow">مرجع تشريعي</p><h2 id="article-dialog-title">{article ? `المادة ${article.article_number} — ${article.legislation_title}` : "تفاصيل المادة"}</h2></div>
          <Button variant="icon" icon="close" aria-label="إغلاق" onClick={onClose} />
        </header>
        <div className="dialog-body">
          {state.loading ? <LoadingState label="جارٍ تحميل المادة وروابطها..." />
            : state.error ? <div className="inline-error" role="alert">{state.error}</div>
              : article ? (
                <>
                  <div className="article-meta">
                    {article.legislation_type && <span>{legislationTypeLabel(article.legislation_type)}</span>}
                    <StatusBadge status={article.status} />
                    {article.effective_date && <span><bdi dir="ltr">{article.effective_date}</bdi></span>}
                  </div>
                  {topicList(article.topic_tags).length > 0 && (
                    <div className="tag-list">{topicList(article.topic_tags).map((tag) => <span className="topic-tag" key={tag}>{tag}</span>)}</div>
                  )}
                  <div className="legal-text" lang="ar" dir="rtl">{article.text || "لم يرد نص لهذه المادة في بيانات الخدمة."}</div>
                  <OfficialSource className="source-row" sourceUrl={article.source_url} sourceLabel={article.source_label} officialSource={article.official_source} />
                  <section className="dialog-related">
                    <h3>العلاقات التشريعية</h3>
                    {neighbors.length ? neighbors.map((edge, index) => {
                      const neighborId = edge.source === article.id ? edge.target : edge.source;
                      const neighborLabel = edge.source === article.id
                        ? edge.target_label || edge.target
                        : edge.source_label || edge.source;
                      return (
                        <button className="related-row" key={`${edge.source}-${edge.target}-${index}`} type="button" onClick={() => onOpenArticle(neighborId)}>
                          <span>{neighborLabel}</span><RelationBadge relation={edge.relation_type} />
                        </button>
                      );
                    }) : <EmptyState title="لا توجد علاقات مسجلة" />}
                  </section>
                </>
              ) : null}
        </div>
      </section>
    </div>
  );
}
