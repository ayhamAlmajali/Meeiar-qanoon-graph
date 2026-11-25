import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePageActions } from "../context/PageActionsContext";
import { api, getErrorMessage } from "../services/api";
import { Button, EmptyState, ErrorState, Icon, legislationTypeLabel, LoadingState, OfficialSource, PageHeader, Panel, StatusBadge } from "../components/common/UI";

const evolutionTypeMeta = {
  repeals: ["إلغاء", "repeals"],
  amends: ["تعديل", "amends"],
  overlaps_with: ["تداخل تشريعي", "overlap"],
  repealed_by: ["أُلغي بموجب", "repeals"],
  amended_by: ["عُدّل بموجب", "amends"],
  enacted: ["صدور التشريع", "enacted"]
};

function evolutionDateOrder(value) {
  const match = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/.exec(String(value || "").trim());
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2] || 1);
  const day = Number(match[3] || 1);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
  return date.getTime();
}

function sortEvolutionStages(stages) {
  if (!Array.isArray(stages)) return [];
  return stages.map((stage, index) => ({ stage, index, dateOrder: evolutionDateOrder(stage?.date) }))
    .sort((a, b) => {
      if (a.dateOrder == null && b.dateOrder != null) return 1;
      if (a.dateOrder != null && b.dateOrder == null) return -1;
      return (a.dateOrder ?? 0) - (b.dateOrder ?? 0) || a.index - b.index;
    })
    .map(({ stage }) => stage);
}

function EvolutionStage({ stage, onOpenArticle }) {
  const change = evolutionTypeMeta[String(stage.change_type || "").toLowerCase()] || ["تطور تشريعي", "neutral"];
  const date = typeof stage.date === "string" && stage.date.trim() ? stage.date.trim() : "التاريخ غير متاح";
  const dateIsNumeric = /^\d{4}(?:-\d{2}){0,2}$/.test(date);
  const title = typeof stage.legislation_title === "string" && stage.legislation_title.trim()
    ? stage.legislation_title.trim()
    : "تشريع غير محدد";
  const articleNumber = stage.article_number == null ? "" : String(stage.article_number);
  const reference = typeof stage.before_or_related_ref === "string" ? stage.before_or_related_ref.trim() : "";
  const note = typeof stage.note === "string" ? stage.note.trim() : "";
  const beforeText = typeof stage.before_text === "string" ? stage.before_text.trim() : "";
  const currentText = typeof stage.current_text === "string" ? stage.current_text.trim() : "";

  return (
    <article className="evolution-stage">
      <time className="evolution-stage-date" dir={dateIsNumeric ? "ltr" : "rtl"}>{date}</time>
      <div className="evolution-stage-card">
        <div className="evolution-stage-heading">
          <div><span className={`evolution-kind evolution-kind-${change[1]}`}>{change[0]}</span>{stage.status && <StatusBadge status={stage.status} />}</div>
          <h3>{articleNumber ? `المادة ${articleNumber} — ${title}` : title}</h3>
        </div>
        {reference && <p className="evolution-reference"><strong>المادة المرتبطة:</strong> {reference}</p>}
        {note && <p className="evolution-note">{note}</p>}
        {(beforeText || currentText) && (
          <details className="evolution-text-comparison">
            <summary>عرض النصوص المرتبطة بالتطور</summary>
            <div>
              {beforeText && <section><strong>النص السابق أو المرتبط</strong><p dir="rtl" lang="ar">{beforeText}</p></section>}
              {currentText && <section><strong>النص الحالي</strong><p dir="rtl" lang="ar">{currentText}</p></section>}
            </div>
          </details>
        )}
        <div className="evolution-stage-actions">
          <OfficialSource sourceUrl={stage.source_url} sourceLabel={stage.source_label} />
          {stage.article_id && <Button variant="secondary" icon="book" onClick={() => onOpenArticle(stage.article_id)}>عرض تفاصيل المادة</Button>}
        </div>
      </div>
    </article>
  );
}

function dateValue(value) {
  const text = String(value || "").trim();
  const match = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/.exec(text);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2] || 1);
  const day = Number(match[3] || 1);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    return null;
  }
  return date;
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
  const [selectedLegislation, setSelectedLegislation] = useState("");
  const [evolutionArticle, setEvolutionArticle] = useState("");
  const [evolutionState, setEvolutionState] = useState({ loading: true, data: null, error: "" });
  const evolutionController = useRef(null);

  const loadEvolution = useCallback(async (legislationTitle = "", articleNumber = "") => {
    evolutionController.current?.abort();
    const controller = new AbortController();
    evolutionController.current = controller;
    setEvolutionState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const data = await api.timelineEvolution({
        legislation_title: legislationTitle,
        article_number: articleNumber
      }, { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (!data || !Array.isArray(data.available_legislations) || !Array.isArray(data.stages)) {
        throw new Error("استجابة التطور التشريعي غير متوقعة.");
      }
      setEvolutionState({ loading: false, data, error: "" });
      setSelectedLegislation(data.selected_legislation || legislationTitle || "");
    } catch (error) {
      if (!controller.signal.aborted) {
        setEvolutionState((current) => ({ ...current, loading: false, error: getErrorMessage(error) }));
      }
    }
  }, []);

  useEffect(() => {
    void loadEvolution();
    return () => evolutionController.current?.abort();
  }, [loadEvolution]);

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
  const availableLegislations = Array.isArray(evolutionState.data?.available_legislations)
    ? evolutionState.data.available_legislations
    : [];
  const evolutionStages = useMemo(
    () => sortEvolutionStages(evolutionState.data?.stages),
    [evolutionState.data]
  );

  const submitEvolutionFilters = (event) => {
    event.preventDefault();
    if (evolutionState.loading || !selectedLegislation.trim()) return;
    void loadEvolution(selectedLegislation.trim(), evolutionArticle.trim());
  };

  const resetEvolutionFilters = () => {
    setEvolutionArticle("");
    void loadEvolution();
  };

  return (
    <>
      <PageHeader eyebrow="التطور الزمني للتشريعات" title="الجدول الزمني" description="استكشف المواد المؤرخة بحسب تاريخ النفاذ المسجل في بيانات الخدمة. التواريخ غير المتاحة لا تُستنتج." actions={<span className="count-pill">{filtered.length.toLocaleString("ar")} مادة</span>} />
      <Panel className="evolution-panel" aria-live="polite">
        <div className="section-heading evolution-heading">
          <div><p className="eyebrow">Legislative Evolution · التطور التشريعي</p><h2>تطور التشريع وعلاقاته</h2><p className="muted-copy">تابع مراحل الإلغاء والتعديل والتداخل أو صدور التشريع، مع الروابط والمراجع التي توفرها الخدمة.</p></div>
        </div>
        <form className="evolution-filters" onSubmit={submitEvolutionFilters}>
          <label className="evolution-filter-field" htmlFor="evolution-legislation"><span>التشريع</span>
            <select id="evolution-legislation" value={selectedLegislation} onChange={(event) => setSelectedLegislation(event.target.value)} disabled={evolutionState.loading || availableLegislations.length === 0}>
              {availableLegislations.length ? availableLegislations.map((item) => <option key={item.legislation_title} value={item.legislation_title}>{item.legislation_title} ({Number(item.article_count || 0).toLocaleString("ar")} مادة)</option>) : <option value="">لا توجد تشريعات متاحة</option>}
            </select>
          </label>
          <label className="evolution-filter-field" htmlFor="evolution-article"><span>رقم المادة (اختياري)</span>
            <input id="evolution-article" type="text" value={evolutionArticle} onChange={(event) => setEvolutionArticle(event.target.value)} placeholder="مثال: 4" disabled={evolutionState.loading || availableLegislations.length === 0} />
          </label>
          <div className="evolution-filter-actions">
            <Button type="submit" icon="search" disabled={evolutionState.loading || !selectedLegislation.trim()}>عرض التطور</Button>
            <Button type="button" variant="secondary" icon="refresh" disabled={evolutionState.loading} onClick={resetEvolutionFilters}>إعادة الضبط</Button>
          </div>
        </form>
        {evolutionState.loading ? <LoadingState label="جارٍ تحميل مراحل التطور التشريعي..." />
          : evolutionState.error ? <ErrorState message={evolutionState.error} onRetry={() => loadEvolution(selectedLegislation, evolutionArticle)} />
            : evolutionState.data ? (
              <>
                <div className="evolution-results-meta"><span>التشريع المحدد: <strong>{evolutionState.data.selected_legislation || selectedLegislation}</strong></span><span>{evolutionStages.length.toLocaleString("ar")} مرحلة</span></div>
                {evolutionStages.length ? <div className="evolution-stage-list">{evolutionStages.map((stage, index) => <EvolutionStage key={`${stage.article_id || stage.change_type || "stage"}-${stage.date || "undated"}-${index}`} stage={stage} onOpenArticle={openArticle} />)}</div>
                  : <EmptyState title="لا توجد مراحل تطور مسجلة" description="لم تُرجع الخدمة مراحل لهذا التشريع أو المادة المحددة." icon="timeline" />}
              </>
            ) : <EmptyState title="لا تتوفر بيانات التطور التشريعي" description="تعذّر تحميل التشريعات المتاحة حالياً." icon="timeline" />}
      </Panel>
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
