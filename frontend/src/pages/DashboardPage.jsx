import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../context/AppContext";
import { api, getErrorMessage } from "../services/api";
import { Icon, LoadingState, PageHeader, Panel, RelationBadge, StatCard } from "../components/common/UI";

const shortcuts = [
  { to: "/ask", icon: "ask", title: "الاستعلام التشريعي", description: "اسأل عن حكم أو التزام، وتعرّف على المواد التي يستند إليها التحليل." },
  { to: "/audit", icon: "audit", title: "مدقق الامتثال والمسودات", description: "راجع بند عقد أو مسودة تشريع بالاستناد إلى المواد المفهرسة." },
  { to: "/graph", icon: "graph", title: "الخريطة التشريعية", description: "استكشف الروابط والأثر بين المواد والتشريعات." },
  { to: "/timeline", icon: "timeline", title: "الجدول الزمني", description: "تصفّح المواد بحسب تاريخ نفاذها وتشريعها." },
];

function ChangeSummary({ title, items, tone }) {
  const entries = Array.isArray(items) ? items : [];
  return (
    <article className={`change-summary change-summary-${tone}`}>
      <div className="change-summary-title"><strong>{title}</strong><span>{entries.length}</span></div>
      {entries.length ? entries.slice(0, 3).map((edge, index) => (
        <div className="change-summary-row" key={`${edge.source}-${edge.target}-${index}`}>
          <span>{edge.source_label || edge.source} ← {edge.target_label || edge.target}</span>
          <RelationBadge relation={edge.relation_type} />
        </div>
      )) : <p className="muted-copy">لا توجد بيانات مسجّلة لهذا النوع.</p>}
    </article>
  );
}

export default function DashboardPage() {
  const { refreshVersion } = useApp();
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

  const summary = summaryState.data;
  const changes = changesState.data || {};
  const relationCount = Object.keys(summary?.relations_by_type || {}).length;
  const cards = [
    { label: "المواد المفهرسة", value: summary?.total_articles?.toLocaleString("ar") ?? "—", note: "وفق بيانات الخدمة الحالية", icon: "book" },
    { label: "عُقد الرسم البياني", value: summary?.total_nodes?.toLocaleString("ar") ?? "—", note: "مواد ومراجع مرتبطة", icon: "graph", tone: "teal" },
    { label: "العلاقات التشريعية", value: summary?.total_edges?.toLocaleString("ar") ?? "—", note: "روابط مرصودة في الرسم", icon: "timeline" },
    { label: "أنواع العلاقات", value: relationCount.toLocaleString("ar"), note: "تصنيفات موجودة في البيانات", icon: "shield", tone: "navy" }
  ];

  return (
    <>
      <PageHeader
        eyebrow="منصة معيار · الأردن"
        title="مرحباً بك في مِعيار"
        description="مساحة عمل موحّدة لاستكشاف التشريعات الأردنية وروابطها وتحليلها."
        actions={<span className="live-source"><span className="health-dot" />بيانات مباشرة من الخدمة</span>}
      />

      <div className="stat-grid" aria-label="ملخص قاعدة البيانات">
        {cards.map((card) => <StatCard key={card.label} {...card} />)}
      </div>

      <Panel className="dashboard-section">
        <div className="section-heading">
          <div><p className="eyebrow">ابدأ من هنا</p><h2>مساحات العمل</h2><p className="muted-copy">انتقل مباشرة إلى الأداة المناسبة لمهمتك.</p></div>
        </div>
        <div className="shortcut-grid">
          {shortcuts.map((item) => (
            <Link to={item.to} className="shortcut-card" key={item.to}>
              <span className="shortcut-icon"><Icon name={item.icon} size={22} /></span>
              <span className="shortcut-content"><strong>{item.title}</strong><span>{item.description}</span></span>
              <Icon name="arrow" size={18} className="shortcut-arrow" />
            </Link>
          ))}
        </div>
      </Panel>

      <Panel className="dashboard-section">
        <div className="section-heading">
          <div><p className="eyebrow">متابعة تشريعية</p><h2>التغييرات والعلاقات المسجّلة</h2><p className="muted-copy">ملخص مباشر لما تعرضه خدمة الرسم البياني؛ لا تُنشأ بيانات تقديرية.</p></div>
          <Link className="text-link" to="/graph">استكشف الخريطة <Icon name="arrow" size={16} /></Link>
        </div>
        {changesState.loading ? <LoadingState label="جارٍ تحميل التغييرات..." />
          : changesState.error ? <div className="inline-error" role="alert">{changesState.error}</div>
            : (
              <div className="change-summary-grid">
                <ChangeSummary title="الإلغاءات" items={changes.repeals} tone="danger" />
                <ChangeSummary title="التعديلات" items={changes.amendments} tone="warning" />
                <ChangeSummary title="التداخلات" items={changes.overlaps} tone="info" />
              </div>
            )}
      </Panel>

      {summaryState.error && <div className="inline-error" role="alert">{summaryState.error}</div>}
      {summaryState.loading && <LoadingState label="جارٍ قراءة مؤشرات قاعدة المعرفة..." />}

      <div className="dashboard-assurance"><Icon name="shield" size={19} /><p>تُعرض المواد والعلاقات كما تصل من واجهة الخدمة. راجع النص التشريعي ومصدره الرسمي قبل الاعتماد على أي تحليل.</p></div>
    </>
  );
}
