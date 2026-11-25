import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { api, getErrorMessage } from "../services/api";
import { Button, EmptyState, ErrorState, Icon, legislationTypeLabel, LoadingState, OfficialSource, PageHeader, Panel, RelationBadge, StatusBadge, relationLabel } from "../components/common/UI";

const relationClasses = {
  repeals: "edge-repeal",
  repealed_by: "edge-repeal",
  amends: "edge-amendment",
  amended_by: "edge-amendment",
  overlaps_with: "edge-overlap",
  protects_over: "edge-protection",
  implements: "edge-implementation",
  details_or_links: "edge-link"
};

const CONFLICT_RELATIONS = new Set(["repeals", "repealed_by", "amends", "amended_by", "overlaps_with"]);
const CONFLICT_RELATION_LIST = ["repeals", "repealed_by", "amends", "amended_by", "overlaps_with"];
const DATA_UNAVAILABLE = "غير متوفر في البيانات الحالية";

function nodeLabel(node) {
  if (node.article_number != null) {
    const title = node.legislation_title || "تشريع غير محدد";
    return `المادة ${node.article_number}\n${title}`;
  }
  return node.label || node.legislation_title || node.id;
}

function statusKey(value) {
  const text = String(value || "").toLowerCase();
  if (/ملغ|منسوخ|repeal|cancel/.test(text)) return "repealed";
  if (/معدل|amend/.test(text)) return "amended";
  if (/ساري|نافذ|active|in_force|effective|valid/.test(text)) return "active";
  return "unknown";
}

function nodeStatusClass(status) {
  const key = statusKey(status);
  return key === "repealed" ? "node-repealed" : key === "amended" ? "node-amended" : key === "active" ? "node-active" : "node-unknown";
}

function changeTitle(edge, nodeMap) {
  const source = nodeMap.get(String(edge.source));
  const target = nodeMap.get(String(edge.target));
  return `${source ? nodeLabel(source).replace("\n", " — ") : edge.source_label || edge.source} ← ${target ? nodeLabel(target).replace("\n", " — ") : edge.target_label || edge.target}`;
}

function ChangeGroup({ title, items, className, nodeMap }) {
  const edges = Array.isArray(items) ? items : [];
  return (
    <article className={`graph-change-card ${className}`}>
      <div className="graph-change-heading"><h3>{title}</h3><span>{edges.length.toLocaleString("ar")}</span></div>
      {edges.length ? <div className="graph-change-list">{edges.map((edge, index) => (
        <div className="graph-change-item" key={`${edge.source}-${edge.target}-${index}`}>
          <strong>{changeTitle(edge, nodeMap)}</strong>
          <RelationBadge relation={edge.relation_type} />
          {edge.note && <p>{edge.note}</p>}
        </div>
      ))}</div> : <p className="muted-copy">لا توجد علاقات مسجّلة.</p>}
    </article>
  );
}

function RelationshipArticleCard({ node, fallbackLabel, role }) {
  const isArticle = Boolean(node && node.kind !== "external_ref");
  const valueOrFallback = (value) => value == null || String(value).trim() === "" ? DATA_UNAVAILABLE : value;
  const heading = node
    ? nodeLabel(node).replace("\n", " — ")
    : valueOrFallback(fallbackLabel);

  return (
    <article className="min-w-0 rounded-xl border border-slate-200 bg-white p-3">
      <p className="eyebrow">{role}</p>
      <h3 className="my-2 break-words text-base font-semibold text-slate-800">{heading}</h3>
      <dl className="grid gap-2 text-sm text-slate-600">
        <div><dt className="inline font-semibold">التشريع: </dt><dd className="inline">{valueOrFallback(isArticle ? node.legislation_title : null)}</dd></div>
        <div><dt className="inline font-semibold">رقم المادة: </dt><dd className="inline">{valueOrFallback(isArticle ? node.article_number : null)}</dd></div>
        <div className="flex flex-wrap items-center gap-2"><dt className="font-semibold">الحالة:</dt><dd>{isArticle && node.status ? <StatusBadge status={node.status} /> : DATA_UNAVAILABLE}</dd></div>
      </dl>
      <div className="legal-text mt-3 max-h-52 overflow-auto text-sm" dir="rtl" lang="ar">
        {valueOrFallback(isArticle ? node.text : null)}
      </div>
      {isArticle && <OfficialSource className="mt-2 text-sm" sourceUrl={node.source_url} sourceLabel={node.source_label} officialSource={node.official_source} />}
    </article>
  );
}

function GraphCanvas({ graphData, onSelectNode, onSelectEdge, graphRef, onReady }) {
  const containerRef = useRef(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !graphData) return undefined;
    const nodes = Array.isArray(graphData.nodes) ? graphData.nodes.filter((node) => node && node.id != null) : [];
    const edges = Array.isArray(graphData.edges) ? graphData.edges.filter((edge) => edge?.source != null && edge?.target != null) : [];
    const elements = nodes.map((node) => ({
      data: {
        id: String(node.id),
        label: nodeLabel(node),
        title: node.legislation_title || "",
        articleNumber: String(node.article_number ?? ""),
        status: node.status || "",
        kind: node.kind || "article"
      },
      classes: nodeStatusClass(node.status) + (node.kind === "external_ref" ? " node-external" : "")
    })).concat(edges.map((edge, index) => {
      const relation = String(edge.relation_type || "").toLowerCase();
      return {
        data: {
          id: `relationship-${index}`,
          source: String(edge.source),
          target: String(edge.target),
          relation,
          note: edge.note || "",
          sourceLabel: edge.source_label || "",
          targetLabel: edge.target_label || ""
        },
        classes: relationClasses[relation] || "edge-link"
      };
    }));

    const instance = cytoscape({
      container,
      elements,
      minZoom: 0.2,
      maxZoom: 2.8,
      layout: {
        name: "cose",
        animate: false,
        fit: true,
        padding: 48,
        nodeRepulsion: 115000,
        nodeOverlap: 54,
        idealEdgeLength: 220,
        edgeElasticity: 90,
        componentSpacing: 190,
        gravity: 0.08,
        numIter: 1100
      },
      style: [
        { selector: "node", style: {
          "shape": "round-rectangle",
          "background-color": "#E7F2EF",
          "border-color": "#7AB6AA",
          "border-width": 1.5,
          "label": "data(label)",
          "font-family": "IBM Plex Sans Arabic, sans-serif",
          "font-size": 13,
          "font-weight": 500,
          "color": "#22364A",
          "text-wrap": "wrap",
          "text-max-width": 205,
          "text-valign": "center",
          "text-halign": "center",
          "width": 238,
          "height": 76,
          "padding": "10px",
          "text-outline-width": 0,
          "overlay-opacity": 0,
          "transition-property": "background-color, border-color, opacity",
          "transition-duration": "160ms"
        } },
        { selector: "node.node-repealed", style: { "background-color": "#FCEDEA", "border-color": "#CB8078", "color": "#773C3B" } },
        { selector: "node.node-amended", style: { "background-color": "#FFF4DF", "border-color": "#D4A64E", "color": "#705329" } },
        { selector: "node.node-unknown", style: { "background-color": "#F0F2F4", "border-color": "#A7B1BC", "color": "#586777" } },
        { selector: "node.node-external", style: { "shape": "ellipse", "width": 200, "height": 68, "background-color": "#F1EDF9", "border-color": "#A392C0", "color": "#594A75" } },
        { selector: "edge", style: {
          "width": 2,
          "line-color": "#A8B6C2",
          "target-arrow-shape": "triangle",
          "target-arrow-color": "#A8B6C2",
          "arrow-scale": 0.8,
          "curve-style": "bezier",
          "opacity": 0.76,
          "overlay-opacity": 0
        } },
        { selector: "edge.edge-repeal", style: { "line-color": "#C6655B", "target-arrow-color": "#C6655B" } },
        { selector: "edge.edge-amendment", style: { "line-color": "#C4933C", "target-arrow-color": "#C4933C" } },
        { selector: "edge.edge-overlap", style: { "line-color": "#4D8DA5", "target-arrow-color": "#4D8DA5" } },
        { selector: "edge.edge-protection", style: { "line-color": "#6F8F56", "target-arrow-color": "#6F8F56" } },
        { selector: "edge.edge-implementation", style: { "line-color": "#7A70AA", "target-arrow-color": "#7A70AA" } },
        { selector: "node:selected", style: { "border-color": "#0F766E", "border-width": 4, "background-blacken": -0.07 } },
        { selector: "node.impact-node", style: { "background-color": "#D9F0E7", "border-color": "#159A91", "border-width": 3, "z-index": 5 } },
        { selector: "node.current-node", style: { "border-color": "#101C2C", "border-width": 4, "z-index": 6 } },
        { selector: ".filtered-out", style: { "display": "none" } },
        { selector: ".faded", style: { "opacity": 0.18, "text-opacity": 0.22 } }
      ]
    });

    graphRef.current = instance;
    instance.on("tap", "node", (event) => {
      instance.nodes().unselect();
      event.target.select();
      onSelectNode(event.target.data("id"));
    });
    instance.on("tap", "edge", (event) => onSelectEdge({
      relation_type: event.target.data("relation"),
      note: event.target.data("note"),
      source: event.target.data("source"),
      target: event.target.data("target"),
      source_label: event.target.data("sourceLabel"),
      target_label: event.target.data("targetLabel")
    }));
    instance.on("mouseover", "node", (event) => {
      instance.elements().addClass("faded");
      event.target.closedNeighborhood().removeClass("faded");
    });
    instance.on("mouseout", () => instance.elements().removeClass("faded"));

    const resize = () => instance.resize();
    window.addEventListener("resize", resize);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(resize);
    observer?.observe(container);
    onReady(instance);

    return () => {
      window.removeEventListener("resize", resize);
      observer?.disconnect();
      instance.destroy();
      if (graphRef.current === instance) graphRef.current = null;
    };
  }, [graphData, graphRef, onReady, onSelectEdge, onSelectNode]);

  return <div ref={containerRef} className="graph-canvas" role="img" aria-label="خريطة تفاعلية للعلاقات التشريعية" />;
}

export default function GraphPage() {
  const [graphState, setGraphState] = useState({ loading: true, data: null, error: "" });
  const [changes, setChanges] = useState(null);
  const [changesError, setChangesError] = useState("");
  const [selectedNode, setSelectedNode] = useState(null);
  const [detailState, setDetailState] = useState({ loading: false, article: null, neighbors: [], impact: null, error: "" });
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [impactError, setImpactError] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [relationFilter, setRelationFilter] = useState("all");
  const [legislationFilter, setLegislationFilter] = useState("all");
  const [conflictLab, setConflictLab] = useState(false);
  const graphRef = useRef(null);
  const previousConflictLab = useRef(false);
  const [graphInstanceVersion, setGraphInstanceVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setGraphState({ loading: true, data: null, error: "" });
    Promise.allSettled([api.graph({ signal: controller.signal }), api.changes({ signal: controller.signal })]).then(([graphResult, changesResult]) => {
      if (controller.signal.aborted) return;
      if (graphResult.status === "fulfilled" && Array.isArray(graphResult.value?.nodes)) {
        setGraphState({ loading: false, data: graphResult.value, error: "" });
      } else {
        setGraphState({ loading: false, data: null, error: graphResult.status === "rejected" ? getErrorMessage(graphResult.reason) : "استجابة الرسم البياني غير متوقعة." });
      }
      if (changesResult.status === "fulfilled") setChanges(changesResult.value);
      else setChangesError(getErrorMessage(changesResult.reason));
    });
    return () => controller.abort();
  }, []);

  const nodes = graphState.data?.nodes || [];
  const nodeMap = useMemo(() => new Map(nodes.map((node) => [String(node.id), node])), [nodes]);
  const legislations = useMemo(() => [...new Set(nodes.map((node) => node.legislation_title).filter(Boolean))].sort((a, b) => a.localeCompare(b, "ar")), [nodes]);
  const relationTypes = useMemo(() => [...new Set((graphState.data?.edges || []).map((edge) => edge.relation_type).filter(Boolean))], [graphState.data]);
  const conflictNodeIds = useMemo(() => {
    if (!conflictLab) return null;
    const ids = new Set();
    (graphState.data?.edges || []).forEach((edge) => {
      const rawRelation = String(edge.relation_type || "").toLowerCase();
      const relation = rawRelation.replace(/^incoming_/, "");
      const matchesRelation = relationFilter === "all" || rawRelation === relationFilter;
      if (CONFLICT_RELATIONS.has(relation) && matchesRelation) {
        ids.add(String(edge.source));
        ids.add(String(edge.target));
      }
    });
    return ids;
  }, [conflictLab, graphState.data, relationFilter]);
  const visibleNodes = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return nodes.filter((node) => {
      const matchesSearch = !query || [node.id, node.label, node.legislation_title, node.article_number]
        .some((value) => String(value || "").toLocaleLowerCase().includes(query));
      const matchesStatus = statusFilter === "all" || statusKey(node.status) === statusFilter;
      const matchesLegislation = legislationFilter === "all" || node.legislation_title === legislationFilter;
      const matchesConflict = !conflictNodeIds || conflictNodeIds.has(String(node.id));
      return matchesSearch && matchesStatus && matchesLegislation && matchesConflict;
    });
  }, [nodes, search, statusFilter, legislationFilter, conflictNodeIds]);
  const onReady = useCallback(() => setGraphInstanceVersion((value) => value + 1), []);
  const onSelectNode = useCallback((identifier) => {
    const node = nodeMap.get(String(identifier));
    if (!node) return;
    const graph = graphRef.current;
    if (graph) {
      graph.nodes().removeClass("impact-node current-node").unselect();
      const selected = graph.getElementById(String(identifier));
      selected.select();
      graph.animate({ center: { eles: selected }, zoom: Math.max(graph.zoom(), 0.82) }, { duration: 250 });
    }
    setSelectedEdge(null);
    setSelectedNode(node);
    setImpactError("");
    if (node.kind !== "external_ref") {
      setDetailState({ loading: true, article: null, neighbors: [], impact: null, error: "" });
      api.article(node.id)
        .then((response) => setDetailState({
          loading: false,
          article: response?.article || node,
          neighbors: Array.isArray(response?.neighbors) ? response.neighbors : [],
          impact: response?.impact || null,
          error: ""
        }))
        .catch((error) => setDetailState({ loading: false, article: node, neighbors: [], impact: null, error: getErrorMessage(error) }));
    } else {
      setDetailState({ loading: false, article: node, neighbors: [], impact: null, error: "" });
    }
  }, [nodeMap]);
  const onSelectEdge = useCallback((edge) => {
    setSelectedNode(null);
    setSelectedEdge(edge);
    setDetailState({ loading: false, article: null, neighbors: [], impact: null, error: "" });
  }, []);

  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    const visibleNodeIds = new Set(visibleNodes.map((node) => String(node.id)));
    graph.batch(() => {
      graph.nodes().forEach((node) => {
        node.toggleClass("filtered-out", !visibleNodeIds.has(node.id()));
      });
      graph.edges().forEach((edge) => {
        const matchesRelation = relationFilter === "all" || edge.data("relation") === relationFilter;
        const relation = String(edge.data("relation") || "").replace(/^incoming_/, "").toLowerCase();
        const matchesConflict = !conflictLab || CONFLICT_RELATIONS.has(relation);
        const endpointsVisible = !edge.source().hasClass("filtered-out") && !edge.target().hasClass("filtered-out");
        edge.toggleClass("filtered-out", !(matchesRelation && matchesConflict && endpointsVisible));
      });
    });
  }, [relationFilter, conflictLab, visibleNodes, graphInstanceVersion]);

  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    const visibleNodesInGraph = graph.nodes().filter((node) => !node.hasClass("filtered-out"));
    if (conflictLab && visibleNodesInGraph.length) {
      visibleNodesInGraph.layout({
        name: "cose", animate: false, fit: false, padding: 48,
        nodeRepulsion: 115000, nodeOverlap: 54, idealEdgeLength: 220,
        edgeElasticity: 90, componentSpacing: 190, gravity: 0.08, numIter: 1100
      }).run();
    } else if (!conflictLab && previousConflictLab.current) {
      graph.layout({
        name: "cose", animate: false, fit: false, padding: 48,
        nodeRepulsion: 115000, nodeOverlap: 54, idealEdgeLength: 220,
        edgeElasticity: 90, componentSpacing: 190, gravity: 0.08, numIter: 1100
      }).run();
    }
    if (visibleNodesInGraph.length) graph.fit(visibleNodesInGraph, 56);
    previousConflictLab.current = conflictLab;
  }, [conflictLab, relationFilter, visibleNodes, graphInstanceVersion]);

  const focusSearchResult = () => {
    const graph = graphRef.current;
    if (!graph || !search.trim()) return;
    const query = search.trim().toLocaleLowerCase();
    const match = graph.nodes().filter((node) => !node.hasClass("filtered-out")).toArray().sort((a, b) => {
      const aExact = String(a.data("articleNumber")) === query ? -1 : 0;
      const bExact = String(b.data("articleNumber")) === query ? -1 : 0;
      return aExact - bExact;
    })[0];
    if (!match) return;
    graph.animate({ center: { eles: match }, zoom: Math.max(graph.zoom(), 1.1) }, { duration: 250 });
    match.select();
    onSelectNode(match.id());
  };

  const runImpact = async () => {
    if (!selectedNode || impactLoading) return;
    setImpactLoading(true);
    setImpactError("");
    try {
      const impact = await api.impact(selectedNode.id);
      setDetailState((current) => ({ ...current, impact }));
      const graph = graphRef.current;
      if (graph) {
        const impactedIds = new Set((impact?.impacted_nodes || []).map((node) => String(node.id)));
        graph.nodes().removeClass("impact-node current-node");
        graph.getElementById(String(selectedNode.id)).addClass("current-node");
        impactedIds.forEach((id) => graph.getElementById(id).addClass("impact-node"));
      }
    } catch (error) {
      setImpactError(getErrorMessage(error));
    } finally {
      setImpactLoading(false);
    }
  };

  const fitGraph = () => {
    const graph = graphRef.current;
    if (!graph) return;
    const visibleNodesInGraph = graph.nodes().filter((node) => !node.hasClass("filtered-out"));
    if (visibleNodesInGraph.length) graph.fit(visibleNodesInGraph, 56);
  };
  const zoomBy = (scale) => {
    const graph = graphRef.current;
    if (!graph) return;
    graph.zoom({ level: graph.zoom() * scale, renderedPosition: { x: graph.width() / 2, y: graph.height() / 2 } });
  };
  const resetGraph = () => {
    const graph = graphRef.current;
    if (!graph) return;
    graph.layout({
      name: "cose", animate: false, fit: true, padding: 48,
      nodeRepulsion: 115000, nodeOverlap: 54, idealEdgeLength: 220,
      edgeElasticity: 90, componentSpacing: 190, gravity: 0.08, numIter: 1100
    }).run();
    graph.nodes().unselect();
  };

  const article = detailState.article || selectedNode;
  const topicTags = Array.isArray(article?.topic_tags) ? article.topic_tags : [];
  const paths = detailState.impact?.impact_paths;
  const impacted = detailState.impact?.impacted_nodes || [];
  const selectedEdgeSource = selectedEdge ? nodeMap.get(String(selectedEdge.source)) : null;
  const selectedEdgeTarget = selectedEdge ? nodeMap.get(String(selectedEdge.target)) : null;

  return (
    <>
      <PageHeader eyebrow="استكشاف الروابط القانونية" title="الخريطة التشريعية" description="تصفّح المواد والعلاقات الفعلية في قاعدة المعرفة، ثم افتح مادة أو تتبّع أثرها." actions={<span className="graph-data-count">{nodes.length ? `${nodes.length.toLocaleString("ar")} عقدة` : "—"}</span>} />
      {graphState.loading ? <LoadingState label="جارٍ بناء خريطة الترابط..." />
        : graphState.error ? <ErrorState message={graphState.error} onRetry={() => window.location.reload()} />
          : (
            <Panel className="graph-workspace">
              <div className="mb-5 border-b border-slate-200 pb-4">
                <div className="min-w-0">
                  <p className="eyebrow">معيار · مختبر العلاقات التشريعية</p>
                  <h2 className="mb-1 text-lg font-semibold text-slate-900">استكشف الروابط بين المواد</h2>
                  <p className="muted-copy">قارن طرفي العلاقة المسجّلة وافحص أثرها على الخريطة.</p>
                </div>
              </div>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-amber-200 bg-amber-50/60 p-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-3">
                    <h2 className="m-0 text-base font-semibold text-slate-800">مختبر التعارضات</h2>
                    <span className="badge badge-neutral">{visibleNodes.length.toLocaleString("ar")} مادة ظاهرة</span>
                  </div>
                  <p className="mb-2 mt-1 text-sm leading-6 text-slate-600">
                    يعرض المواد المرتبطة بإلغاء أو تعديل أو تداخل مسجّل. وجود علاقة تداخل لا يثبت وحده وقوع تعارض قانوني.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {CONFLICT_RELATION_LIST.map((relation) => <RelationBadge key={relation} relation={relation} />)}
                  </div>
                </div>
                <button
                  type="button"
                  className="button button-secondary"
                  aria-pressed={conflictLab}
                  onClick={() => setConflictLab((active) => !active)}
                  style={conflictLab ? { borderColor: "#bd9141", backgroundColor: "#fffaf0", color: "#735b2b" } : undefined}
                >
                  <Icon name="alert" size={18} />
                  <span>{conflictLab ? "إيقاف مختبر التعارضات" : "تفعيل مختبر التعارضات"}</span>
                </button>
              </div>
              <div className="graph-filter-bar">
                <label className="search-field graph-search"><Icon name="search" size={19} /><input value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") focusSearchResult(); }} placeholder="ابحث برقم المادة أو اسم التشريع..." aria-label="البحث في الرسم البياني" /><button type="button" onClick={focusSearchResult}>بحث</button></label>
                <label className="filter-field"><span>التشريع</span><select value={legislationFilter} onChange={(event) => setLegislationFilter(event.target.value)}><option value="all">كل التشريعات</option>{legislations.map((title) => <option key={title} value={title}>{title}</option>)}</select></label>
                <label className="filter-field"><span>الحالة</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">كل الحالات</option><option value="active">ساري</option><option value="amended">معدّل</option><option value="repealed">ملغى</option></select></label>
                <label className="filter-field"><span>العلاقة</span><select value={relationFilter} onChange={(event) => setRelationFilter(event.target.value)}><option value="all">كل العلاقات</option>{relationTypes.map((relation) => <option key={relation} value={relation}>{relationLabel(relation)}</option>)}</select></label>
              </div>
              <div className="graph-toolbar">
                <span className="graph-hint"><span className="health-dot" />اضغط على عقدة أو علاقة لعرض التفاصيل</span>
                <div className="toolbar-actions">
                  <button type="button" aria-label="تكبير" title="تكبير" onClick={() => zoomBy(1.2)}><Icon name="plus" /></button>
                  <button type="button" aria-label="تصغير" title="تصغير" onClick={() => zoomBy(1 / 1.2)}><Icon name="minus" /></button>
                  <button type="button" title="ملاءمة العرض" onClick={fitGraph}><Icon name="fit" />ملاءمة العرض</button>
                  <button type="button" title="إعادة ترتيب الرسم" onClick={resetGraph}><Icon name="refresh" />إعادة الترتيب</button>
                </div>
              </div>
              <div className="graph-layout">
                <div className="graph-main">
                  <GraphCanvas graphData={graphState.data} graphRef={graphRef} onReady={onReady} onSelectNode={onSelectNode} onSelectEdge={onSelectEdge} />
                  <div className="graph-legend">
                    <span><i className="legend-node legend-active" />مادة سارية</span><span><i className="legend-node legend-amended" />معدّلة</span><span><i className="legend-node legend-repealed" />ملغاة</span>
                    <span><i className="legend-line legend-repeal" />إلغاء</span><span><i className="legend-line legend-amendment" />تعديل</span><span><i className="legend-line legend-overlap" />تداخل</span>
                  </div>
                  <details className="graph-accessible-list">
                    <summary>استعراض المواد الظاهرة في قائمة قابلة للتنقل ({visibleNodes.length.toLocaleString("ar")})</summary>
                    <div>{visibleNodes.length ? visibleNodes.map((node) => <button type="button" key={node.id} onClick={() => onSelectNode(node.id)}><span>{nodeLabel(node).replace("\n", " — ")}</span><StatusBadge status={node.status} /></button>) : <p className="muted-copy p-3">لا توجد مواد تطابق المرشحات الحالية.</p>}</div>
                  </details>
                </div>
                <aside className="node-detail-panel" aria-live="polite">
                  {selectedEdge ? (
                    <div className="node-details">
                      <p className="eyebrow">فحص طرفي العلاقة</p>
                      <h2>{selectedEdge.source_label || (selectedEdgeSource ? nodeLabel(selectedEdgeSource).replace("\n", " — ") : DATA_UNAVAILABLE)} ← {selectedEdge.target_label || (selectedEdgeTarget ? nodeLabel(selectedEdgeTarget).replace("\n", " — ") : DATA_UNAVAILABLE)}</h2>
                      <RelationBadge relation={selectedEdge.relation_type} />
                      <p className="result-prose">{selectedEdge.note || "لا يوجد تفصيل إضافي للعلاقة."}</p>
                      <div className="mt-4 grid gap-3">
                        <RelationshipArticleCard node={selectedEdgeSource} fallbackLabel={selectedEdge.source_label} role="المادة المصدر" />
                        <RelationshipArticleCard node={selectedEdgeTarget} fallbackLabel={selectedEdge.target_label} role="المادة المرتبطة" />
                      </div>
                    </div>
                  ) : !selectedNode ? (
                    <EmptyState title="اختر عقدة لعرض التفاصيل" description="انقر على مادة في الخريطة لعرض بياناتها وروابطها وأثرها." icon="graph" />
                  ) : detailState.loading ? <LoadingState label="جارٍ تحميل تفاصيل المادة..." />
                    : (
                      <div className="node-details">
                        <div className="node-detail-heading"><p className="eyebrow">{article?.kind === "external_ref" ? "مرجع تشريعي مرتبط" : "بيانات المادة"}</p><StatusBadge status={article?.status} /></div>
                        <h2>{article?.article_number != null ? `المادة ${article.article_number}` : article?.label || "مرجع تشريعي"}</h2>
                        <h3>{article?.legislation_title || "تشريع غير محدد"}</h3>
                        <div className="article-meta">{article?.legislation_type && <span>{legislationTypeLabel(article.legislation_type)}</span>}{article?.effective_date && <span><Icon name="calendar" size={15} />{article.effective_date}</span>}</div>
                        {topicTags.length > 0 && <div className="tag-list">{topicTags.map((tag) => <span className="topic-tag" key={tag}>{tag}</span>)}</div>}
                        {detailState.error && <div className="inline-error" role="alert">{detailState.error}</div>}
                        {article?.text && <div className="legal-text node-legal-text" dir="rtl" lang="ar">{article.text}</div>}
                        <OfficialSource className="source-row" sourceUrl={article?.source_url} sourceLabel={article?.source_label} officialSource={article?.official_source} />
                        {detailState.neighbors.length > 0 && <section className="node-subsection"><h4>مواد مرتبطة</h4>{detailState.neighbors.slice(0, 8).map((edge, index) => {
                          const relatedId = edge.source === article?.id ? edge.target : edge.source;
                          const relatedNode = nodeMap.get(String(relatedId));
                          return <button className="related-row" key={`${edge.source}-${edge.target}-${index}`} type="button" disabled={!relatedNode || relatedNode.kind === "external_ref"} onClick={() => onSelectNode(relatedId)}><span>{relatedNode ? nodeLabel(relatedNode).replace("\n", " — ") : edge.source_label || edge.target_label}</span><RelationBadge relation={edge.relation_type} /></button>;
                        })}</section>}
                        <div className="impact-action-row"><Button variant="secondary" icon="timeline" onClick={runImpact} disabled={impactLoading}>{impactLoading ? "جارٍ تتبّع الأثر..." : "تتبّع الأثر التشريعي"}</Button></div>
                        {impactError && <div className="inline-error" role="alert">{impactError}</div>}
                        {detailState.impact && <section className="node-subsection"><h4>سلسلة الأثر <span className="count-pill">{impacted.length.toLocaleString("ar")}</span></h4>
                          {impacted.length ? <div className="impact-nodes">{impacted.map((node) => <button key={node.id} type="button" className="impact-node-link" onClick={() => nodeMap.has(String(node.id)) && onSelectNode(node.id)}>{nodeLabel(node).replace("\n", " — ")}</button>)}</div> : <p className="muted-copy">لا توجد مواد متأثرة مسجّلة.</p>}
                          {Array.isArray(paths) && paths.length > 0 && <div className="impact-paths">{paths.slice(0, 12).map((path, index) => <div key={index}><span>{path.from || "مادة"}</span><Icon name="arrow" size={14} /><span>{path.to || "مرجع"}</span><RelationBadge relation={path.relation_type} /></div>)}</div>}
                        </section>}
                      </div>
                    )}
                </aside>
              </div>
            </Panel>
          )}

      <Panel className="changes-workspace">
        <div className="section-heading"><div><p className="eyebrow">تتبّع الأثر القانوني</p><h2>التغييرات التشريعية</h2><p className="muted-copy">علاقات الإلغاء والتعديل والتداخل كما أعادتها الخدمة.</p></div></div>
        {changesError ? <div className="inline-error" role="alert">{changesError}</div> : !changes ? <LoadingState label="جارٍ تحميل التغييرات..." /> : (
          <div className="graph-changes-grid">
            <ChangeGroup title="الإلغاءات" items={changes.repeals} className="tone-danger" nodeMap={nodeMap} />
            <ChangeGroup title="التعديلات" items={changes.amendments} className="tone-warning" nodeMap={nodeMap} />
            <ChangeGroup title="التداخلات" items={changes.overlaps} className="tone-info" nodeMap={nodeMap} />
          </div>
        )}
      </Panel>
    </>
  );
}
