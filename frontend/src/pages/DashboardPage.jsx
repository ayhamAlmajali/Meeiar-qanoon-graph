import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApp } from "../context/AppContext";
import { usePageActions } from "../context/PageActionsContext";
import { api, getErrorMessage } from "../services/api";
import {
  Button,
  Icon,
  Panel,
  RelationBadge,
  SkeletonCards,
  StatCard
} from "../components/common/UI";

const shortcuts = [
  {
    to: "/ask",
    icon: "ask",
    title: "الاستعلام التشريعي",
    description: "اسأل عن حكم أو التزام عمالي، واحصل على تحليل مدعوم بالمواد والروابط.",
    tag: "ذكاء اصطناعي موثّق"
  },
  {
    to: "/audit",
    icon: "audit",
    title: "مدقق الامتثال والمسودات",
    description: "راجع بند عقد أو مسودة تشريع وقارنه بالقواعد الآمرة والمواد السارية.",
    tag: "فحص العقود واللوائح"
  },
  {
    to: "/graph",
    icon: "graph",
    title: "الخريطة التشريعية",
    description: "استكشف شبكة العلاقات التشريعية، مختبر التعارضات، وسلاسل الأثر.",
    tag: "رسم بياني تفاعلي"
  },
  {
    to: "/timeline",
    icon: "timeline",
    title: "الجدول الزمني",
    description: "تتبّع التطور التاريخي للتشريعات وتصفّح المواد بحسب تاريخ النفاذ.",
    tag: "تطور تشريعي"
  }
];

function ChangeSummary({ title, items, tone, onInspect }) {
  const entries = Array.isArray(items) ? items : [];
  return (
    <article className={`change-summary change-summary-${tone}`}>
      <div className="change-summary-title">
        <strong>{title}</strong>
        <span>{entries.length.toLocaleString("ar")}</span>
      </div>
      {entries.length ? (
        entries.slice(0, 4).map((edge, index) => (
          <button
            type="button"
            className="change-summary-row"
            key={`${edge.source}-${edge.target}-${index}`}
            onClick={() => onInspect?.(edge.source || edge.target)}
            title="انقر لعرض تفاصيل المادة"
          >
            <span>{edge.source_label || edge.source} ← {edge.target_label || edge.target}</span>
            <RelationBadge relation={edge.relation_type} />
          </button>
        ))
      ) : (
        <p className="muted-copy">لا توجد بيانات مسجّلة لهذا النوع.</p>
      )}
    </article>
  );
}

export default function DashboardPage() {
  const { refreshVersion } = useApp();
  const { openArticle } = usePageActions();
  const navigate = useNavigate();
  const [quickQuery, setQuickQuery] = useState("");
  const [summaryState, setSummaryState] = useState({ loading: true, data: null, error: "" });
  const [changesState, setChangesState] = useState({ loading: true, data: null, error: "" });

  useEffect(() => {
    const controller = new AbortController();
    setSummaryState((state) => ({ ...state, loading: true, error: "" }));
    setChangesState((state) => ({ ...state, loading: true, error: "" }));
    Promise.allSettled([
      api.summary({ signal: controller.signal }),
      api.changes({ signal: controller.signal })
    ]).then(([summaryResult, changesResult]) => {
      if (controller.signal.aborted) return;
      setSummaryState(summaryResult.status === "fulfilled"
        ? { loading: false, data: summaryResult.value, error: "" }
        : { loading: false, data: null, error: getErrorMessage(summaryResult.reason) });
      setChangesState(changesResult.status === "fulfilled"
        ? { loading: false, data: changesResult.value, error: "" }
        : { loading: false, data: null, error: getErrorMessage(changesResult.reason) });
    });
    return () => controller.abort();
  }, [refreshVersion]);

  const handleQuickAsk = (event) => {
    event.preventDefault();
    const clean = quickQuery.trim();
    if (!clean) {
      navigate("/ask");
      return;
    }
    navigate(`/ask?q=${encodeURIComponent(clean)}`);
  };

  const summary = summaryState.data;
  const changes = changesState.data || {};
  const relationEntries = Object.entries(summary?.relations_by_type || {}).sort((a, b) => b[1] - a[1]);
  const totalEdgesForPct = summary?.total_edges || relationEntries.reduce((acc, [, count]) => acc + count, 0) || 1;
  const relationCount = relationEntries.length;

  const cards = [
    {
      label: "المواد المفهرسة",
      value: summary?.total_articles?.toLocaleString("ar") ?? "—",
      note: "نصوص تشريعية موثقة في القاعدة",
      icon: "book",
      tone: "default"
    },
    {
      label: "عُقد الرسم البياني",
      value: summary?.total_nodes?.toLocaleString("ar") ?? "—",
      note: "مواد ومراجع تشريعية مرتبطة",
      icon: "graph",
      tone: "teal"
    },
    {
      label: "العلاقات التشريعية",
      value: summary?.total_edges?.toLocaleString("ar") ?? "—",
      note: "روابط إلغاء وتعديل وتداخل وإحالة",
      icon: "timeline",
      tone: "gold"
    },
    {
      label: "أنواع العلاقات",
      value: summary ? relationCount.toLocaleString("ar") : "—",
      note: "تصنيفات مرصودة في الشبكة",
      icon: "shield",
      tone: "navy"
    }
  ];

  const hasContradictions = Array.isArray(changes.contradictions) && changes.contradictions.length > 0;

  return (
    <div className="animate-enter">
      <section className="hero-banner">
        <div className="hero-content">
          <span className="hero-eyebrow">
            <Icon name="scale" size={14} />
            منصة الذكاء التشريعي الأردني · MEEIAR
          </span>
          <h1>افهم التشريعات الأردنية، حلّل النصوص، واكتشف التعارضات</h1>
          <p>
            مساحة عمل موحّدة تربط نصوص قانون العمل والأنظمة المرتبطة به في رسم بياني معرفي دقيق، لتمنحك استعلاماً قانونياً موثقاً وتدقيق امتثال فوري.
          </p>
          <form className="hero-quick-ask" onSubmit={handleQuickAsk}>
            <input
              type="text"
              value={quickQuery}
              onChange={(event) => setQuickQuery(event.target.value)}
              placeholder="اطرح سؤالاً قانونياً سريعاً (مثال: هل يحق لصاحب العمل تخفيض الأجر في العمل المرن؟)"
              aria-label="سؤال تشريعي سريع"
            />
            <Button type="submit" icon="sparkle">استعلام فوري</Button>
          </form>
        </div>

        <aside className="hero-side-card" aria-label="حالة قاعدة المعرفة">
          <div className="hero-side-row">
            <span>حالة التغذية</span>
            <span className="live-source !py-1 !px-2.5 !text-xs">
              <span className="health-dot" />
              بيانات مباشرة
            </span>
          </div>
          <div className="hero-side-row">
            <span>الإلغاءات المرصودة</span>
            <strong>{Array.isArray(changes.repeals) ? changes.repeals.length.toLocaleString("ar") : "—"}</strong>
          </div>
          <div className="hero-side-row">
            <span>التعديلات المسجّلة</span>
            <strong>{Array.isArray(changes.amendments) ? changes.amendments.length.toLocaleString("ar") : "—"}</strong>
          </div>
          <div className="hero-side-row">
            <span>التداخلات التنظيمية</span>
            <strong>{Array.isArray(changes.overlaps) ? changes.overlaps.length.toLocaleString("ar") : "—"}</strong>
          </div>
        </aside>
      </section>

      <div className="stat-grid" aria-label="ملخص قاعدة البيانات">
        {cards.map((card) => (
          <StatCard key={card.label} {...card} loading={summaryState.loading} />
        ))}
      </div>

      {summaryState.error && (
        <div className="inline-error" role="alert">
          <Icon name="alert" size={18} />
          <span>{summaryState.error}</span>
        </div>
      )}

      {relationEntries.length > 0 && (
        <section className="relation-breakdown" aria-label="توزيع العلاقات في الرسم البياني">
          <div className="relation-breakdown-header">
            <div>
              <h3>توزيع الروابط في الرسم البياني التشريعي</h3>
              <p className="muted-copy !m-0">تصنيف فعلي لكافة العلاقات المستخرجة من النصوص المفهرسة.</p>
            </div>
            <Link className="text-link" to="/graph">
              <span>عرض الشبكة الكاملة</span>
              <Icon name="arrow" size={15} />
            </Link>
          </div>
          <div className="relation-bars-grid">
            {relationEntries.map(([type, count]) => {
              const pct = Math.max(4, Math.round((count / totalEdgesForPct) * 100));
              return (
                <div className="relation-bar-item" key={type}>
                  <div className="relation-bar-top">
                    <RelationBadge relation={type} />
                    <strong>{count.toLocaleString("ar")}</strong>
                  </div>
                  <div className="relation-bar-track" aria-hidden="true">
                    <div className="relation-bar-fill" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <Panel className="dashboard-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">ابدأ من هنا</p>
            <h2>مساحات العمل</h2>
            <p className="muted-copy">اختر الأداة المناسبة للاستعلام القانوني أو فحص العقود أو استكشاف الروابط.</p>
          </div>
        </div>
        <div className="shortcut-grid">
          {shortcuts.map((item) => (
            <Link to={item.to} className="shortcut-card" key={item.to}>
              <span className="shortcut-icon"><Icon name={item.icon} size={22} /></span>
              <span className="shortcut-content">
                <span className="flex flex-wrap items-center gap-2">
                  <strong>{item.title}</strong>
                  <span className="badge badge-neutral !text-[11px] !min-h-0 !py-0.5">{item.tag}</span>
                </span>
                <span>{item.description}</span>
              </span>
              <Icon name="arrow" size={18} className="shortcut-arrow" />
            </Link>
          ))}
        </div>
      </Panel>

      <Panel className="dashboard-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">متابعة تشريعية</p>
            <h2>التغييرات والعلاقات المسجّلة</h2>
            <p className="muted-copy">ملخص مباشر من خدمة الرسم البياني؛ انقر على أي صف لاستعراض نص المادة وتفاصيلها.</p>
          </div>
          <Link className="text-link" to="/graph">
            <span>استكشف الخريطة</span>
            <Icon name="arrow" size={15} />
          </Link>
        </div>

        {changesState.loading ? (
          <SkeletonCards count={3} />
        ) : changesState.error ? (
          <div className="inline-error" role="alert">
            <Icon name="alert" size={18} />
            <span>{changesState.error}</span>
          </div>
        ) : (
          <div className="change-summary-grid">
            <ChangeSummary title="الإلغاءات" items={changes.repeals} tone="danger" onInspect={openArticle} />
            <ChangeSummary title="التعديلات" items={changes.amendments} tone="warning" onInspect={openArticle} />
            <ChangeSummary title="التداخلات" items={changes.overlaps} tone="info" onInspect={openArticle} />
            {hasContradictions && (
              <ChangeSummary title="التعارضات" items={changes.contradictions} tone="danger" onInspect={openArticle} />
            )}
          </div>
        )}
      </Panel>

      <div className="dashboard-assurance">
        <Icon name="shield" size={19} />
        <p>
          تُعرض المواد والعلاقات كما تصل من واجهة الخدمة دون بيانات تقديرية. راجع النص التشريعي ومصدره الرسمي قبل الاعتماد على أي تحليل.
        </p>
      </div>
    </div>
  );
}
