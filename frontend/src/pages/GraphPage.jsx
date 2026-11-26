import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { api, getErrorMessage } from "../services/api";
import {
  Button,
  EmptyState,
  ErrorState,
  Icon,
  legislationTypeLabel,
  LoadingState,
  OfficialSource,
  PageHeader,
  Panel,
  RelationBadge,
  SimilarityBadge,
  StatusBadge,
  relationLabel
} from "../components/common/UI";

const relationClasses = {
  repeals: "edge-repeal",
  repealed_by: "edge-repeal",
  amends: "edge-amendment",
  amended_by: "edge-amendment",
  overlaps_with: "edge-overlap",
  contradicts: "edge-contradiction",
  references: "edge-reference",
  protects_over: "edge-protection",
  implements: "edge-implementation",
  details_or_links: "edge-link"
};

const GRAPH_LAYOUT = Object.freeze({
  name: "cose",
  animate: false,
  padding: 48,
  nodeRepulsion: 160000,
  nodeOverlap: 72,
  idealEdgeLength: 250,
  edgeElasticity: 90,
  componentSpacing: 210,
  gravity: 0.08,
  numIter: 1100
});

const CONFLICT_RELATIONS = new Set(["repeals", "repealed_by", "amends", "amended_by", "overlaps_with", "contradicts"]);
const CONFLICT_RELATION_LIST = ["repeals", "repealed_by", "amends", "amended_by", "overlaps_with", "contradicts"];
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

function applyImpactHighlight(graph, selectedId, impact, nodeMap) {
  if (!graph) return;
  graph.elements().removeClass("impact-node current-node impact-edge");
  graph.nodes().unselect();
  graph.getElementById(String(selectedId)).addClass("current-node").select();

  const impactedIds = new Set((impact?.impacted_nodes || []).map((node) => String(node.id)));
  const idByLabel = new Map([...nodeMap].map(([id, node]) => [String(node.label || ""), String(id)]));
  const paths = (Array.isArray(impact?.impact_paths) ? impact.impact_paths : []).map((path) => {
    const source = nodeMap.has(String(path.from)) ? String(path.from) : idByLabel.get(String(path.from));
    const target = nodeMap.has(String(path.to)) ? String(path.to) : idByLabel.get(String(path.to));
    if (source) impactedIds.add(source);
    if (target) impactedIds.add(target);
    return {
      source,
      target,
      relation: String(path.relation_type || "").replace(/^incoming_/, "").toLowerCase()
    };
  }).filter((path) => path.source && path.target && path.relation);

  graph.nodes().forEach((node) => {
    if (impactedIds.has(node.id()) && node.id() !== String(selectedId)) node.addClass("impact-node");
  });
  graph.edges().forEach((edge) => {
    const relation = String(edge.data("relation") || "").replace(/^incoming_/, "").toLowerCase();
    const matchesPath = paths.some((path) => path.relation === relation && (
      (path.source === edge.source().id() && path.target === edge.target().id()) ||
      (path.source === edge.target().id() && path.target === edge.source().id())
    ));
    if (matchesPath) edge.addClass("impact-edge");
  });
}

function changeTitle(edge, nodeMap) {
  const source = nodeMap.get(String(edge.source));
  const target = nodeMap.get(String(edge.target));
  return `${source ? nodeLabel(source).replace("\n", " — ") : edge.source_label || edge.source} ← ${target ? nodeLabel(target).replace("\n", " — ") : edge.target_label || edge.target}`;
}

function ChangeGroup({ title, items, className, nodeMap, onSelectArticle }) {
  const edges = Array.isArray(items) ? items : [];
  return (
    <article className={`graph-change-card ${className}`}>
      <div className="graph-change-heading">
        <h3>{title}</h3>
        <span>{edges.length.toLocaleString("ar")}</span>
      </div>
      {edges.length ? (
        <div className="graph-change-list">
          {edges.map((edge, index) => {
            const targetId = nodeMap.has(String(edge.source)) ? String(edge.source) : nodeMap.has(String(edge.target)) ? String(edge.target) : null;
            return (
              <div className="graph-change-item" key={`${edge.source}-${edge.target}-${index}`}>
                <div className="flex items-start justify-between gap-2">
                  <strong>{changeTitle(edge, nodeMap)}</strong>
                  {targetId && (
                    <button
                      type="button"
                      className="text-button !px-2 !py-0.5 !text-xs shrink-0"
                      onClick={() => onSelectArticle?.(targetId)}
                    >
                      تحديد
                    </button>
                  )}
                </div>
                <RelationBadge relation={edge.relation_type} />
                {edge.note && <p>{edge.note}</p>}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="muted-copy">لا توجد علاقات مسجّلة.</p>
      )}
    </article>
  );
}

function RelationshipArticleCard({ node, fallbackLabel, caption, onJump }) {
  const isArticle = Boolean(node && node.kind !== "external_ref");
  const valueOrFallback = (value) => value == null || String(value).trim() === "" ? DATA_UNAVAILABLE : value;
  const heading = node
    ? nodeLabel(node).replace("\n", " — ")
    : valueOrFallback(fallbackLabel);

  return (
    <article className="min-w-0 rounded-xl border border-slate-200 bg-white p-3.5 shadow-xs">
      <div className="flex items-center justify-between gap-2">
        <p className="eyebrow !m-0">{caption}</p>
        {node && (
          <button type="button" className="text-button !px-2 !py-0.5 !text-xs" onClick={() => onJump?.(node.id)}>
            معاينة العقدة
          </button>
        )}
      </div>
      <h3 className="my-2 break-words text-base font-bold text-slate-900">{heading}</h3>
      <dl className="grid gap-1.5 text-xs text-slate-600">
        <div><dt className="inline font-semibold">التشريع: </dt><dd className="inline">{valueOrFallback(isArticle ? node.legislation_title : null)}</dd></div>
        <div><dt className="inline font-semibold">رقم المادة: </dt><dd className="inline">{valueOrFallback(isArticle ? node.article_number : null)}</dd></div>
        <div className="flex flex-wrap items-center gap-2"><dt className="font-semibold">الحالة:</dt><dd>{isArticle && node.status ? <StatusBadge status={node.status} /> : DATA_UNAVAILABLE}</dd></div>
      </dl>
      <div className="legal-text mt-3 max-h-48 overflow-auto !text-sm !p-3" dir="rtl" lang="ar">
        {valueOrFallback(isArticle ? node.text : null)}
      </div>
      {isArticle && (
        <OfficialSource
          className="mt-2 text-xs"
          sourceUrl={node.source_url}
          sourceLabel={node.source_label}
          officialSource={node.official_source}
        />
      )}
    </article>
  );
}

function GraphCanvas({ graphData, showEdgeLabels, onSelectNode, onSelectEdge, onHoverChange, graphRef, onReady }) {
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
      const relationClass = relationClasses[relation.replace(/^incoming_/, "")] || "edge-link";
      return {
        data: {
          id: `relationship-${index}`,
          source: String(edge.source),
          target: String(edge.target),
          relation,
          relationText: relationLabel(relation),
          note: edge.note || "",
          sourceLabel: edge.source_label || "",
          targetLabel: edge.target_label || ""
        },
        classes: relationClass
      };
    }));

    const instance = cytoscape({
      container,
      elements,
      minZoom: 0.2,
      maxZoom: 2.8,
      layout: { ...GRAPH_LAYOUT, fit: true },
      style: [
        {
          selector: "node",
          style: {
            "shape": "round-rectangle",
            "background-color": "#EAF5EF",
            "border-color": "#2E785D",
            "border-width": 1.6,
            "label": "data(label)",
            "font-family": "IBM Plex Sans Arabic, sans-serif",
            "font-size": 13.5,
            "font-weight": 600,
            "color": "#162544",
            "text-wrap": "wrap",
            "text-max-width": 218,
            "text-valign": "center",
            "text-halign": "center",
            "width": 252,
            "height": 84,
            "padding": "10px",
            "text-outline-width": 0,
            "overlay-opacity": 0,
            "transition-property": "background-color, border-color, opacity",
            "transition-duration": "160ms"
          }
        },
        {
          selector: "node.node-repealed",
          style: { "background-color": "#FCECEB", "border-color": "#A63A31", "color": "#73231C" }
        },
        {
          selector: "node.node-amended",
          style: { "background-color": "#FDF4E3", "border-color": "#B48332", "color": "#6E4810" }
        },
        {
          selector: "node.node-unknown",
          style: { "background-color": "#F0ECE2", "border-color": "#9DA3AE", "color": "#3D434F" }
        },
        {
          selector: "node.node-external",
          style: {
            "shape": "ellipse",
            "width": 214,
            "height": 74,
            "background-color": "#EDF2FA",
            "border-color": "#334D82",
            "color": "#162544"
          }
        },
        {
          selector: "edge",
          style: {
            "width": 2.2,
            "line-color": "#9DA3AE",
            "target-arrow-shape": "triangle",
            "target-arrow-color": "#9DA3AE",
            "arrow-scale": 0.85,
            "curve-style": "bezier",
            "opacity": 0.78,
            "overlay-opacity": 0,
            "font-family": "IBM Plex Sans Arabic, sans-serif",
            "font-size": 11,
            "color": "#162544",
            "text-background-color": "#FFFFFF",
            "text-background-opacity": 0.9,
            "text-background-padding": "3px",
            "text-border-color": "#E3DFD4",
            "text-border-width": 1,
            "text-border-opacity": 0.9
          }
        },
        { selector: "edge.show-label", style: { "label": "data(relationText)" } },
        { selector: "edge.edge-repeal", style: { "line-color": "#A63A31", "target-arrow-color": "#A63A31" } },
        { selector: "edge.edge-amendment", style: { "line-color": "#B48332", "target-arrow-color": "#B48332" } },
        { selector: "edge.edge-overlap", style: { "line-color": "#23477C", "target-arrow-color": "#23477C" } },
        { selector: "edge.edge-contradiction", style: { "line-color": "#932E26", "target-arrow-color": "#932E26", "line-style": "dashed", "width": 2.8 } },
        { selector: "edge.edge-reference", style: { "line-color": "#2E785D", "target-arrow-color": "#2E785D", "line-style": "dotted" } },
        { selector: "edge.edge-protection", style: { "line-color": "#1F5E48", "target-arrow-color": "#1F5E48" } },
        { selector: "edge.edge-implementation", style: { "line-color": "#233863", "target-arrow-color": "#233863" } },
        { selector: "node:selected", style: { "border-color": "#162544", "border-width": 4, "background-blacken": -0.05 } },
        { selector: "node.hovered", style: { "border-color": "#B48332", "border-width": 3, "z-index": 7 } },
        { selector: "node.impact-node", style: { "background-color": "#DFF2E8", "border-color": "#1F5E48", "border-width": 3, "z-index": 5 } },
        { selector: "node.current-node", style: { "border-color": "#162544", "border-width": 4, "z-index": 6 } },
        { selector: "edge.impact-edge", style: { "line-color": "#A63A31", "target-arrow-color": "#A63A31", "width": 3.5, "opacity": 1, "z-index": 4 } },
        { selector: ".filtered-out", style: { "display": "none" } },
        { selector: ".faded", style: { "opacity": 0.16, "text-opacity": 0.2 } }
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
      event.target.addClass("hovered");
      onHoverChange?.({
        kind: "node",
        title: String(event.target.data("label") || "").replace("\n", " — "),
        meta: event.target.data("status") || "مادة"
      });
    });
    instance.on("mouseout", "node", (event) => {
      instance.elements().removeClass("faded");
      event.target.removeClass("hovered");
      onHoverChange?.(null);
    });
    instance.on("mouseover", "edge", (event) => {
      onHoverChange?.({
        kind: "edge",
        title: `${event.target.data("sourceLabel") || event.target.data("source")} ← ${event.target.data("targetLabel") || event.target.data("target")}`,
        meta: event.target.data("relationText")
      });
    });
    instance.on("mouseout", "edge", () => {
      onHoverChange?.(null);
    });

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
  }, [graphData, graphRef, onHoverChange, onReady, onSelectEdge, onSelectNode]);

  useEffect(() => {
    const instance = graphRef.current;
    if (!instance) return;
    instance.edges().toggleClass("show-label", showEdgeLabels);
  }, [showEdgeLabels, graphRef, graphData]);

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
  const [showEdgeLabels, setShowEdgeLabels] = useState(false);
  const [expandedView, setExpandedView] = useState(false);
  const [hoveredInfo, setHoveredInfo] = useState(null);
  const [copiedArticle, setCopiedArticle] = useState(false);
  const [changeTab, setChangeTab] = useState("all");
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
        setGraphState({
          loading: false,
          data: null,
          error: graphResult.status === "rejected" ? getErrorMessage(graphResult.reason) : "استجابة الرسم البياني غير متوقعة."
        });
      }
      if (changesResult.status === "fulfilled") setChanges(changesResult.value);
      else setChangesError(getErrorMessage(changesResult.reason));
    });
    return () => controller.abort();
  }, []);

  const nodes = graphState.data?.nodes || [];
  const edges = graphState.data?.edges || [];
  const nodeMap = useMemo(() => new Map(nodes.map((node) => [String(node.id), node])), [nodes]);
  const legislations = useMemo(() => [...new Set(nodes.map((node) => node.legislation_title).filter(Boolean))].sort((a, b) => a.localeCompare(b, "ar")), [nodes]);
  const relationTypes = useMemo(() => [...new Set(edges.map((edge) => edge.relation_type).filter(Boolean))], [edges]);

  const conflictNodeIds = useMemo(() => {
    if (!conflictLab) return null;
    const ids = new Set();
    edges.forEach((edge) => {
      const rawRelation = String(edge.relation_type || "").toLowerCase();
      const relation = rawRelation.replace(/^incoming_/, "");
      const matchesRelation = relationFilter === "all" || rawRelation === relationFilter;
      if (CONFLICT_RELATIONS.has(relation) && matchesRelation) {
        ids.add(String(edge.source));
        ids.add(String(edge.target));
      }
    });
    return ids;
  }, [conflictLab, edges, relationFilter]);

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

  const visibleStats = useMemo(() => {
    const stats = { active: 0, amended: 0, repealed: 0, external: 0 };
    visibleNodes.forEach((node) => {
      if (node.kind === "external_ref") {
        stats.external += 1;
        return;
      }
      const key = statusKey(node.status);
      if (key === "active") stats.active += 1;
      else if (key === "amended") stats.amended += 1;
      else if (key === "repealed") stats.repealed += 1;
    });
    return stats;
  }, [visibleNodes]);

  const onReady = useCallback(() => setGraphInstanceVersion((value) => value + 1), []);

  const onSelectNode = useCallback((identifier) => {
    const node = nodeMap.get(String(identifier));
    if (!node) return;
    const graph = graphRef.current;
    applyImpactHighlight(graph, identifier, null, nodeMap);
    if (graph) {
      const selected = graph.getElementById(String(identifier));
      graph.animate({ center: { eles: selected }, zoom: Math.max(graph.zoom(), 0.85) }, { duration: 250 });
    }
    setSelectedEdge(null);
    setSelectedNode(node);
    setCopiedArticle(false);
    setImpactError("");
    if (node.kind !== "external_ref") {
      setDetailState({ loading: true, article: null, neighbors: [], impact: null, error: "" });
      api.article(node.id)
        .then((response) => {
          const impact = response?.impact || null;
          applyImpactHighlight(graphRef.current, identifier, impact, nodeMap);
          setDetailState({
            loading: false,
            article: response?.article || node,
            neighbors: Array.isArray(response?.neighbors) ? response.neighbors : [],
            impact,
            error: ""
          });
        })
        .catch((error) => setDetailState({ loading: false, article: node, neighbors: [], impact: null, error: getErrorMessage(error) }));
    } else {
      setDetailState({ loading: false, article: node, neighbors: [], impact: null, error: "" });
    }
  }, [nodeMap]);

  const onSelectEdge = useCallback((edge) => {
    graphRef.current?.elements().removeClass("impact-node current-node impact-edge");
    graphRef.current?.nodes().unselect();
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
      visibleNodesInGraph.layout({ ...GRAPH_LAYOUT, fit: false }).run();
    } else if (!conflictLab && previousConflictLab.current) {
      graph.layout({ ...GRAPH_LAYOUT, fit: false }).run();
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
      applyImpactHighlight(graphRef.current, selectedNode.id, impact, nodeMap);
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
    graph.layout({ ...GRAPH_LAYOUT, fit: true }).run();
    graph.nodes().unselect();
  };

  const resetFilters = () => {
    setSearch("");
    setStatusFilter("all");
    setRelationFilter("all");
    setLegislationFilter("all");
    setConflictLab(false);
  };

  const copySelectedText = async () => {
    const text = detailState.article?.text || selectedNode?.text;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopiedArticle(true);
    } catch {
      setCopiedArticle(false);
    }
  };

  const hasActiveFilters = Boolean(search.trim() || statusFilter !== "all" || relationFilter !== "all" || legislationFilter !== "all" || conflictLab);
  const article = detailState.article || selectedNode;
  const topicTags = Array.isArray(article?.topic_tags) ? article.topic_tags : [];
  const paths = detailState.impact?.impact_paths;
  const impacted = detailState.impact?.impacted_nodes || [];
  const outdatedRegs = detailState.impact?.potentially_outdated_regulations || [];
  const selectedEdgeSource = selectedEdge ? nodeMap.get(String(selectedEdge.source)) : null;
  const selectedEdgeTarget = selectedEdge ? nodeMap.get(String(selectedEdge.target)) : null;
  const hasContradictions = Array.isArray(changes?.contradictions) && changes.contradictions.length > 0;

  return (
    <div className="animate-enter">
      <PageHeader
        eyebrow="استكشاف الروابط القانونية"
        title="الخريطة التشريعية"
        description="تصفّح شبكة المواد والعلاقات الفعلية في قاعدة المعرفة، فعّل مختبر التعارضات، وتتبّع سلسلة الأثر التشريعي لأي مادة."
        actions={
          <div className="flex items-center gap-2">
            <span className="count-pill">{nodes.length ? `${nodes.length.toLocaleString("ar")} عقدة` : "—"}</span>
            <span className="count-pill">{edges.length ? `${edges.length.toLocaleString("ar")} رابط` : "—"}</span>
          </div>
        }
      />

      {graphState.loading ? (
        <LoadingState label="جارٍ بناء خريطة الترابط التشريعي..." />
      ) : graphState.error ? (
        <ErrorState message={graphState.error} onRetry={() => window.location.reload()} />
      ) : (
        <Panel className="graph-workspace">
          <div className={`conflict-lab-banner ${conflictLab ? "active" : ""}`}>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2.5">
                <h2 className="m-0 text-base font-bold text-slate-900">مختبر التعارضات والتعديلات</h2>
                <span className="badge badge-neutral">{visibleNodes.length.toLocaleString("ar")} مادة ظاهرة</span>
              </div>
              <p className="mb-2 mt-1 text-sm leading-6 text-slate-600">
                يعزل المواد المرتبطة بإلغاء أو تعديل أو تداخل مسجّل لتسليط الضوء على نقاط التقاطع الحرجة. وجود علاقة تداخل لا يثبت وحده تعارضاً قانونياً.
              </p>
              <div className="flex flex-wrap gap-1.5">
                {CONFLICT_RELATION_LIST.map((relation) => (
                  <RelationBadge key={relation} relation={relation} />
                ))}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {hasActiveFilters && (
                <Button variant="quiet" size="sm" icon="refresh" onClick={resetFilters}>
                  إعادة ضبط الكل
                </Button>
              )}
              <Button
                type="button"
                variant={conflictLab ? "gold" : "secondary"}
                icon="alert"
                aria-pressed={conflictLab}
                onClick={() => setConflictLab((active) => !active)}
              >
                {conflictLab ? "إيقاف مختبر التعارضات" : "تفعيل مختبر التعارضات"}
              </Button>
            </div>
          </div>

          <div className="graph-filter-bar">
            <label className="search-field graph-search">
              <Icon name="search" size={18} />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => { if (event.key === "Enter") focusSearchResult(); }}
                placeholder="ابحث برقم المادة أو اسم التشريع..."
                aria-label="البحث في الرسم البياني"
              />
              <button type="button" onClick={focusSearchResult}>تركيز</button>
            </label>
            <label className="filter-field">
              <span>التشريع</span>
              <select value={legislationFilter} onChange={(event) => setLegislationFilter(event.target.value)}>
                <option value="all">كل التشريعات</option>
                {legislations.map((title) => <option key={title} value={title}>{title}</option>)}
              </select>
            </label>
            <label className="filter-field">
              <span>الحالة</span>
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="all">كل الحالات</option>
                <option value="active">ساري</option>
                <option value="amended">معدّل</option>
                <option value="repealed">ملغى</option>
              </select>
            </label>
            <label className="filter-field">
              <span>العلاقة</span>
              <select value={relationFilter} onChange={(event) => setRelationFilter(event.target.value)}>
                <option value="all">كل العلاقات</option>
                {relationTypes.map((relation) => <option key={relation} value={relation}>{relationLabel(relation)}</option>)}
              </select>
            </label>
          </div>

          <div className="graph-toolbar">
            <span className="graph-hint">
              <span className="health-dot" />
              <span>انقر على أي عقدة مادة أو خط علاقة لفحص النصوص والأثر التشريعي</span>
            </span>
            <div className="toolbar-actions">
              <button
                type="button"
                className={showEdgeLabels ? "active-tool" : ""}
                aria-pressed={showEdgeLabels}
                onClick={() => setShowEdgeLabels((v) => !v)}
              >
                <Icon name="tag" />
                <span>{showEdgeLabels ? "إخفاء مسميات الروابط" : "إظهار مسميات الروابط"}</span>
              </button>
              <button
                type="button"
                className={expandedView ? "active-tool" : ""}
                aria-pressed={expandedView}
                onClick={() => setExpandedView((v) => !v)}
              >
                <Icon name={expandedView ? "minimize" : "expand"} />
                <span>{expandedView ? "عرض جانبي" : "توسيع الخريطة"}</span>
              </button>
              <button type="button" title="ملاءمة العرض" onClick={fitGraph}>
                <Icon name="fit" />
                <span>ملاءمة</span>
              </button>
              <button type="button" title="إعادة ترتيب الرسم" onClick={resetGraph}>
                <Icon name="refresh" />
                <span>إعادة الترتيب</span>
              </button>
            </div>
          </div>

          <div className={`graph-layout ${expandedView ? "graph-expanded" : ""}`}>
            <div className="graph-main">
              <div className="graph-viewport">
                <GraphCanvas
                  graphData={graphState.data}
                  showEdgeLabels={showEdgeLabels}
                  graphRef={graphRef}
                  onReady={onReady}
                  onSelectNode={onSelectNode}
                  onSelectEdge={onSelectEdge}
                  onHoverChange={setHoveredInfo}
                />
                <div className="graph-hud-floating" aria-label="أدوات التكبير">
                  <button type="button" aria-label="تكبير" title="تكبير" onClick={() => zoomBy(1.22)}>
                    <Icon name="plus" size={16} />
                  </button>
                  <button type="button" aria-label="تصغير" title="تصغير" onClick={() => zoomBy(1 / 1.22)}>
                    <Icon name="minus" size={16} />
                  </button>
                  <button type="button" aria-label="ملاءمة العرض" title="ملاءمة العرض" onClick={fitGraph}>
                    <Icon name="fit" size={16} />
                  </button>
                </div>
                {hoveredInfo && (
                  <div className="graph-hover-pill" role="status">
                    <span className="font-semibold">{hoveredInfo.title}</span>
                    {hoveredInfo.meta && <span className="opacity-75">· {hoveredInfo.meta}</span>}
                  </div>
                )}
              </div>

              <div className="graph-legend">
                <span><i className="legend-node legend-active" />مادة سارية</span>
                <span><i className="legend-node legend-amended" />معدّلة</span>
                <span><i className="legend-node legend-repealed" />ملغاة</span>
                <span><i className="legend-node legend-external" />مرجع خارجي</span>
                <span><i className="legend-line legend-repeal" />إلغاء</span>
                <span><i className="legend-line legend-amendment" />تعديل</span>
                <span><i className="legend-line legend-overlap" />تداخل</span>
                <span><i className="legend-line legend-contradiction" />تعارض</span>
                <span><i className="legend-line legend-reference" />إحالة</span>
              </div>

              <details className="graph-accessible-list">
                <summary>
                  استعراض المواد الظاهرة في قائمة قابلة للتنقل ({visibleNodes.length.toLocaleString("ar")})
                </summary>
                <div>
                  {visibleNodes.length ? (
                    visibleNodes.map((node) => (
                      <button type="button" key={node.id} onClick={() => onSelectNode(node.id)}>
                        <span>{nodeLabel(node).replace("\n", " — ")}</span>
                        <StatusBadge status={node.status} />
                      </button>
                    ))
                  ) : (
                    <p className="muted-copy p-3">لا توجد مواد تطابق المرشحات الحالية.</p>
                  )}
                </div>
              </details>
            </div>

            <aside className="node-detail-panel" aria-live="polite">
              {selectedEdge ? (
                <div className="node-details">
                  <p className="eyebrow">فحص طرفي العلاقة</p>
                  <h2>
                    {selectedEdge.source_label || (selectedEdgeSource ? nodeLabel(selectedEdgeSource).replace("\n", " — ") : DATA_UNAVAILABLE)}
                    {" ← "}
                    {selectedEdge.target_label || (selectedEdgeTarget ? nodeLabel(selectedEdgeTarget).replace("\n", " — ") : DATA_UNAVAILABLE)}
                  </h2>
                  <div className="my-2">
                    <RelationBadge relation={selectedEdge.relation_type} />
                  </div>
                  <p className="result-prose !text-sm">{selectedEdge.note || "لا يوجد تفصيل إضافي للعلاقة."}</p>
                  <div className="mt-4 grid gap-3">
                    <RelationshipArticleCard
                      node={selectedEdgeSource}
                      fallbackLabel={selectedEdge.source_label}
                      caption="المادة المصدر"
                      onJump={onSelectNode}
                    />
                    <RelationshipArticleCard
                      node={selectedEdgeTarget}
                      fallbackLabel={selectedEdge.target_label}
                      caption="المادة المرتبطة"
                      onJump={onSelectNode}
                    />
                  </div>
                </div>
              ) : !selectedNode ? (
                <div className="grid gap-4">
                  <EmptyState
                    title="اختر عقدة أو علاقة للفحص"
                    description="انقر على أي مادة في الخريطة لعرض نصها القانوني وروابطها وتتبع سلسلة أثرها."
                    icon="graph"
                  />
                  <div className="rounded-xl border border-slate-200 bg-white p-4 grid gap-2.5">
                    <span className="text-xs font-bold text-slate-500">توزيع العقد الظاهرة حالياً</span>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="flex items-center justify-between rounded-lg bg-[#eaf5ef] px-3 py-2 text-[#1f6b4e]">
                        <span>سارية</span>
                        <strong>{visibleStats.active.toLocaleString("ar")}</strong>
                      </div>
                      <div className="flex items-center justify-between rounded-lg bg-[#fdf4e3] px-3 py-2 text-[#8f5c14]">
                        <span>معدّلة</span>
                        <strong>{visibleStats.amended.toLocaleString("ar")}</strong>
                      </div>
                      <div className="flex items-center justify-between rounded-lg bg-[#fceceb] px-3 py-2 text-[#a63a31]">
                        <span>ملغاة</span>
                        <strong>{visibleStats.repealed.toLocaleString("ar")}</strong>
                      </div>
                      <div className="flex items-center justify-between rounded-lg bg-[#edf2fa] px-3 py-2 text-[#23477c]">
                        <span>مراجع خارجية</span>
                        <strong>{visibleStats.external.toLocaleString("ar")}</strong>
                      </div>
                    </div>
                  </div>
                </div>
              ) : detailState.loading ? (
                <LoadingState label="جارٍ تحميل تفاصيل المادة..." />
              ) : (
                <div className="node-details">
                  <div className="node-detail-heading">
                    <p className="eyebrow !m-0">{article?.kind === "external_ref" ? "مرجع تشريعي مرتبط" : "ملف المادة"}</p>
                    <StatusBadge status={article?.status} />
                  </div>
                  <h2>{article?.article_number != null ? `المادة ${article.article_number}` : article?.label || "مرجع تشريعي"}</h2>
                  <h3>{article?.legislation_title || "تشريع غير محدد"}</h3>

                  <div className="article-meta">
                    {article?.legislation_type && <span className="badge badge-neutral">{legislationTypeLabel(article.legislation_type)}</span>}
                    {article?.effective_date && (
                      <span className="badge badge-neutral">
                        <Icon name="calendar" size={13} />
                        <bdi dir="ltr">{article.effective_date}</bdi>
                      </span>
                    )}
                    <SimilarityBadge article={article} showMeter />
                  </div>

                  {topicTags.length > 0 && (
                    <div className="tag-list">
                      {topicTags.map((tag) => <span className="topic-tag" key={tag}>{tag}</span>)}
                    </div>
                  )}

                  {detailState.error && (
                    <div className="inline-error" role="alert">
                      <Icon name="alert" size={16} />
                      <span>{detailState.error}</span>
                    </div>
                  )}

                  {article?.text && (
                    <div>
                      <div className="flex justify-end mb-1">
                        <button type="button" className="text-button !text-xs" onClick={copySelectedText}>
                          <Icon name={copiedArticle ? "check" : "copy"} size={13} />
                          <span>{copiedArticle ? "تم النسخ" : "نسخ نص المادة"}</span>
                        </button>
                      </div>
                      <div className="legal-text node-legal-text" dir="rtl" lang="ar">{article.text}</div>
                    </div>
                  )}

                  <OfficialSource
                    className="source-row"
                    sourceUrl={article?.source_url}
                    sourceLabel={article?.source_label}
                    officialSource={article?.official_source}
                  />

                  {detailState.neighbors.length > 0 && (
                    <section className="node-subsection">
                      <h4>
                        <span>مواد وعقد مرتبطة</span>
                        <span className="count-pill">{detailState.neighbors.length.toLocaleString("ar")}</span>
                      </h4>
                      {detailState.neighbors.slice(0, 8).map((edge, index) => {
                        const relatedId = edge.source === article?.id ? edge.target : edge.source;
                        const relatedNode = nodeMap.get(String(relatedId));
                        return (
                          <button
                            className="related-row"
                            key={`${edge.source}-${edge.target}-${index}`}
                            type="button"
                            disabled={!relatedNode || relatedNode.kind === "external_ref"}
                            onClick={() => onSelectNode(relatedId)}
                          >
                            <span>{relatedNode ? nodeLabel(relatedNode).replace("\n", " — ") : edge.source_label || edge.target_label}</span>
                            <RelationBadge relation={edge.relation_type} />
                          </button>
                        );
                      })}
                    </section>
                  )}

                  <div className="impact-action-row">
                    <Button variant="secondary" icon="timeline" onClick={runImpact} disabled={impactLoading}>
                      {impactLoading ? "جارٍ تتبّع الأثر..." : "تتبّع الأثر التشريعي"}
                    </Button>
                  </div>

                  {impactError && (
                    <div className="inline-error" role="alert">
                      <Icon name="alert" size={16} />
                      <span>{impactError}</span>
                    </div>
                  )}

                  {detailState.impact && (
                    <section className="node-subsection">
                      <h4>
                        <span>سلسلة الأثر التشريعي</span>
                        <span className="count-pill">{impacted.length.toLocaleString("ar")}</span>
                      </h4>
                      {impacted.length ? (
                        <div className="impact-nodes">
                          {impacted.map((node) => (
                            <button
                              key={node.id}
                              type="button"
                              className="impact-node-link"
                              onClick={() => nodeMap.has(String(node.id)) && onSelectNode(node.id)}
                            >
                              {nodeLabel(node).replace("\n", " — ")}
                            </button>
                          ))}
                        </div>
                      ) : (
                        <p className="muted-copy">لا توجد مواد متأثرة مسجّلة.</p>
                      )}

                      {outdatedRegs.length > 0 && (
                        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
                          <strong className="block text-xs text-amber-900 mb-1.5">
                            أنظمة فرعية قد تتأثر بالتغيير ({outdatedRegs.length.toLocaleString("ar")})
                          </strong>
                          <div className="grid gap-1">
                            {outdatedRegs.map((reg) => (
                              <button
                                key={reg.id}
                                type="button"
                                className="text-right text-xs text-amber-800 hover:underline"
                                onClick={() => nodeMap.has(String(reg.id)) && onSelectNode(reg.id)}
                              >
                                • {nodeLabel(reg).replace("\n", " — ")}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {Array.isArray(paths) && paths.length > 0 && (
                        <div className="impact-paths">
                          {paths.slice(0, 12).map((path, index) => (
                            <div key={index}>
                              <span>{path.from || "مادة"}</span>
                              <Icon name="arrow" size={13} />
                              <span>{path.to || "مرجع"}</span>
                              <RelationBadge relation={path.relation_type} />
                            </div>
                          ))}
                        </div>
                      )}
                    </section>
                  )}
                </div>
              )}
            </aside>
          </div>
        </Panel>
      )}

      <Panel className="changes-workspace">
        <div className="section-heading">
          <div>
            <p className="eyebrow">تتبّع الأثر القانوني</p>
            <h2>سجل التغييرات التشريعية</h2>
            <p className="muted-copy">علاقات الإلغاء والتعديل والتداخل كما أعادتها الخدمة. انقر على "تحديد" لعرض المادة على الخريطة.</p>
          </div>
          {changes && (
            <div className="chip-list" role="tablist" aria-label="تصفية التغييرات">
              {[
                ["all", "الكل"],
                ["repeals", "الإلغاءات"],
                ["amendments", "التعديلات"],
                ["overlaps", "التداخلات"],
                ...(hasContradictions ? [["contradictions", "التعارضات"]] : [])
              ].map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={changeTab === key}
                  className={`sample-chip ${changeTab === key ? "active-chip" : ""}`}
                  onClick={() => setChangeTab(key)}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>

        {changesError ? (
          <div className="inline-error" role="alert">{changesError}</div>
        ) : !changes ? (
          <LoadingState label="جارٍ تحميل التغييرات..." />
        ) : (
          <div className="graph-changes-grid">
            {(changeTab === "all" || changeTab === "repeals") && (
              <ChangeGroup title="الإلغاءات" items={changes.repeals} className="tone-danger" nodeMap={nodeMap} onSelectArticle={onSelectNode} />
            )}
            {(changeTab === "all" || changeTab === "amendments") && (
              <ChangeGroup title="التعديلات" items={changes.amendments} className="tone-warning" nodeMap={nodeMap} onSelectArticle={onSelectNode} />
            )}
            {(changeTab === "all" || changeTab === "overlaps") && (
              <ChangeGroup title="التداخلات" items={changes.overlaps} className="tone-info" nodeMap={nodeMap} onSelectArticle={onSelectNode} />
            )}
            {hasContradictions && (changeTab === "all" || changeTab === "contradictions") && (
              <ChangeGroup title="التعارضات" items={changes.contradictions} className="tone-danger" nodeMap={nodeMap} onSelectArticle={onSelectNode} />
            )}
          </div>
        )}
      </Panel>
    </div>
  );
}
