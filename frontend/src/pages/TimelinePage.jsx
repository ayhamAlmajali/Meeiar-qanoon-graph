import { useEffect, useMemo, useState } from "react";
import { usePageActions } from "../context/PageActionsContext";
import { api, getErrorMessage } from "../services/api";
import { EmptyState, ErrorState, Icon, legislationTypeLabel, LoadingState, PageHeader, Panel, StatusBadge } from "../components/common/UI";

function dateValue(value) {
  const text = String(value || "").trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return null;
  const date = new Date(`${text}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function compareArticles(a, b) {
  const dateCompare = String(b.effective_date || "").localeCompare(String(a.effective_date || ""));
  if (dateCompare) return dateCompare;
  return String(a.legislation_title || "").localeCompare(String(b.legislation_title || ""), "ar")
    || String(a.article_number || "").localeCompare(String(b.article_number || ""), "ar", { numeric: true });
}

function articleStatusKey(status) {
  const value = String(status || "").toLowerCase();
  if (/ملغ|منسوخ|repeal|cancel/.test(value)) return "repealed";
  if (/معدل|amend/.test(value)) return "amended";
  if (/ساري|نافذ|active|effective|valid/.test(value)) return "active";
  return "unknown";
}

function groupByLegislation(articles) {
  const groups = new Map();
  articles.forEach((article) => {
    const key = article.legislation_title || "تشريع غير محدد";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(article);
  });
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b, "ar"));
}

export default function TimelinePage() {
  const { openArticle } = usePageActions();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [type, setType] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [reloadVersion, setReloadVersion] = useState(0);
  const [state, setState] = useState({ loading: true, articles: [], error: "" });

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setState((current) => ({ ...current, loading: true, error: "" }));
      api.articles(query.trim(), { signal: controller.signal })
        .then((articles) => {
          if (!Array.isArray(articles)) throw new Error("استجابة مكتبة المواد غير متوقعة.");
          setState({ loading: false, articles, error: "" });
        })
        .catch((error) => {
          if (error?.name !== "AbortError") setState({ loading: false, articles: [], error: getErrorMessage(error) });
        });
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, reloadVersion]);

  const types = useMemo(() => [...new Set(state.articles.map((article) => article.legislation_type).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b), "ar")), [state.articles]);
  const filtered = useMemo(() => state.articles.filter((article) => {
    if (status !== "all" && articleStatusKey(article.status) !== status) return false;
    if (type !== "all" && article.legislation_type !== type) return false;
    const date = dateValue(article.effective_date);
    if (dateFrom && (!date || date < new Date(`${dateFrom}T00:00:00Z`))) return false;
    if (dateTo && (!date || date > new Date(`${dateTo}T23:59:59Z`))) return false;
    return true;
  }).sort(compareArticles), [state.articles, status, type, dateFrom, dateTo]);

  const grouped = useMemo(() => {
    const groups = new Map();
    const undated = [];
    filtered.forEach((article) => {
      const date = dateValue(article.effective_date);
      if (!date) {
        undated.push(article);
        return;
      }
      const year = String(date.getUTCFullYear());
      if (!groups.has(year)) groups.set(year, []);
      groups.get(year).push(article);
    });
    return { years: [...groups.entries()].sort(([a], [b]) => Number(b) - Number(a)), undated };
  }, [filtered]);

  return (
    <>
      <PageHeader eyebrow="التطور الزمني للتشريعات" title="الجدول الزمني" description="استكشف المواد المؤرخة بحسب تاريخ النفاذ المسجل في بيانات الخدمة. التواريخ غير المتاحة لا تُستنتج." actions={<span className="count-pill">{filtered.length.toLocaleString("ar")} مادة</span>} />
      <Panel className="timeline-filters">
        <label className="search-field timeline-search"><Icon name="search" size={19} /><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ابحث باسم التشريع أو رقم المادة أو نصها..." aria-label="البحث في المواد" /></label>
        <label className="filter-field"><span>الحالة التشريعية</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">كل الحالات</option><option value="active">ساري</option><option value="amended">معدّل</option><option value="repealed">ملغى</option></select></label>
        <label className="filter-field"><span>نوع التشريع</span><select value={type} onChange={(event) => setType(event.target.value)}><option value="all">كل الأنواع</option>{types.map((item) => <option key={item} value={item}>{legislationTypeLabel(item)}</option>)}</select></label>
        <label className="filter-field date-filter"><span>من تاريخ</span><input type="date" dir="ltr" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
        <label className="filter-field date-filter"><span>إلى تاريخ</span><input type="date" dir="ltr" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label>
      </Panel>

      {state.loading ? <LoadingState label="جارٍ تحميل المواد وترتيبها زمنياً..." />
        : state.error ? <ErrorState message={state.error} onRetry={() => setReloadVersion((value) => value + 1)} />
          : filtered.length ? (
            <div className="timeline-groups">
              {grouped.years.map(([year, articles], groupIndex) => (
                <details className="timeline-year" key={year} open={groupIndex === 0}>
                  <summary><span className="year-marker"><Icon name="calendar" size={20} /></span><strong>{year}</strong><span>{articles.length.toLocaleString("ar")} مادة مؤرخة</span></summary>
                  <div className="timeline-legislation-groups">
                    {groupByLegislation(articles).map(([title, legislationArticles], legislationIndex) => (
                      <details className="timeline-legislation" key={title} open={groupIndex === 0 && legislationIndex === 0}>
                        <summary><span>{title}</span><small>{legislationTypeLabel(legislationArticles[0]?.legislation_type)}</small><b>{legislationArticles.length.toLocaleString("ar")} مادة</b></summary>
                        <div className="timeline-items">
                          {legislationArticles.map((article, index) => (
                            <article className="timeline-item" key={article.id || `${article.article_number}-${index}`}>
                              <span className="timeline-point" />
                              <div className="timeline-date"><bdi dir="ltr">{article.effective_date}</bdi></div>
                              <button className="timeline-article" type="button" onClick={() => openArticle(article.id || article.article_number)}>
                                <span className="timeline-article-title"><strong>{article.legislation_title || "تشريع غير محدد"}</strong><span>المادة {article.article_number ?? "—"}</span></span>
                                <span className="timeline-article-meta"><span>{legislationTypeLabel(article.legislation_type)}</span><StatusBadge status={article.status} /></span>
                              </button>
                            </article>
                          ))}
                        </div>
                      </details>
                    ))}
                  </div>
                </details>
              ))}
              {grouped.undated.length > 0 && (
                <details className="timeline-year undated-group">
                  <summary><span className="year-marker"><Icon name="book" size={20} /></span><strong>تاريخ النفاذ غير متاح</strong><span>{grouped.undated.length.toLocaleString("ar")} مادة</span></summary>
                  <div className="timeline-items">{grouped.undated.map((article, index) => (
                    <article className="timeline-item" key={article.id || index}><span className="timeline-point" /><span className="timeline-date">غير مؤرخ</span>
                      <button className="timeline-article" type="button" onClick={() => openArticle(article.id || article.article_number)}><span className="timeline-article-title"><strong>{article.legislation_title || "تشريع غير محدد"}</strong><span>المادة {article.article_number ?? "—"} · {legislationTypeLabel(article.legislation_type)}</span></span><StatusBadge status={article.status} /></button>
                    </article>
                  ))}</div>
                </details>
              )}
            </div>
          ) : <Panel><EmptyState title="لا توجد مواد مطابقة" description="جرّب إزالة بعض عوامل التصفية أو تغيير عبارة البحث." icon="calendar" /></Panel>}
    </>
  );
}
