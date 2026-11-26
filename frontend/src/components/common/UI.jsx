import { NavLink } from "react-router-dom";

const icons = {
  home: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  ask: <><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8A8.5 8.5 0 0 1 8.7 3.9a8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z" /><path d="M9.5 9.5a2.1 2.1 0 1 1 3.9 1.1c-.7 1-1.9 1.1-1.9 2.4M11.5 16h.01" /></>,
  audit: <><path d="M9 4.5H6.5A2.5 2.5 0 0 0 4 7v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2.5 2.5 0 0 0-2.5-2.5H15" /><rect x="9" y="2.5" width="6" height="4" rx="1" /><path d="m8 13 2.3 2.3L16 9.8" /></>,
  graph: <><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="7" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="m8 7 7.5-.1M7.4 8.1l3.3 7.6m5.9-6.9-3.3 7" /></>,
  timeline: <><path d="M4 5h16M4 12h16M4 19h16" /><circle cx="8" cy="5" r="2" /><circle cx="15" cy="12" r="2" /><circle cx="10" cy="19" r="2" /></>,
  upload: <><path d="M12 16V4m0 0L7 9m5-5 5 5" /><path d="M5 14v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5" /></>,
  search: <><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 5 5" /></>,
  plus: <><path d="M12 5v14M5 12h14" /></>,
  minus: <path d="M5 12h14" />,
  fit: <><path d="M8 3H5a2 2 0 0 0-2 2v3m13-5h3a2 2 0 0 1 2 2v3M3 16v3a2 2 0 0 0 2 2h3m13-5v3a2 2 0 0 1-2 2h-3" /><path d="m9 9 6 6m0-6-6 6" /></>,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M5.5 9a7 7 0 0 1 11.6-2.5L20 12M4 12l2.9 5.5A7 7 0 0 0 18.5 15" /></>,
  arrow: <><path d="M19 12H5m7 7-7-7 7-7" /></>,
  arrowRight: <><path d="M5 12h14m-7-7 7 7-7 7" /></>,
  book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 0 4 22z" /><path d="M4 5.5v14A2.5 2.5 0 0 1 6.5 17H20M8 7h8m-8 4h8" /></>,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></>,
  external: <><path d="M14 4h6v6m0-6-9 9" /><path d="M18 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5" /></>,
  close: <><path d="m18 6-12 12M6 6l12 12" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  alert: <><path d="M10.3 3.9 2.6 17.2A2 2 0 0 0 4.3 20h15.4a2 2 0 0 0 1.7-2.8L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4m0 4h.01" /></>,
  menu: <><path d="M4 6h16M4 12h16M4 18h16" /></>,
  shield: <><path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z" /><path d="m9 12 2 2 4-4" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
  sparkle: <><path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z" /><path d="m19 14 .9 2.1L22 17l-2.1.9L19 20l-.9-2.1L16 17l2.1-.9L19 14Z" /></>,
  scale: <><path d="M12 3v18M5 21h14M4 7h16" /><path d="m7 7-3 6a3 3 0 0 0 6 0L7 7Zm10 0-3 6a3 3 0 0 0 6 0l-3-6Z" /></>,
  history: <><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /><path d="M12 7v5l3 2" /></>,
  expand: <><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" /></>,
  minimize: <><path d="M4 14h6v6M20 10h-6V4M14 10l7-7M10 14l-7 7" /></>,
  tag: <><path d="M12 2H2v10l9.3 9.3a2.4 2.4 0 0 0 3.4 0l6.6-6.6a2.4 2.4 0 0 0 0-3.4L12 2Z" /><circle cx="7" cy="7" r="1.2" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 16v-4m0-4h.01" /></>,
  chevronDown: <path d="m6 9 6 6 6-6" />
};

export function Icon({ name, size = 20, className = "" }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {icons[name] || icons.book}
    </svg>
  );
}

export function validHttpUrl(value) {
  if (typeof value !== "string" || !value.trim()) return "";
  try {
    const url = new URL(value.trim());
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : "";
  } catch {
    return "";
  }
}

export function OfficialSource({
  sourceUrl,
  sourceLabel,
  officialSource,
  className = "",
  heading = "المصدر الرسمي"
}) {
  const href = validHttpUrl(sourceUrl);
  const label = typeof sourceLabel === "string" && sourceLabel.trim()
    ? sourceLabel.trim()
    : !href && typeof officialSource === "string"
      ? officialSource.trim()
      : "";
  if (!href && !label) return null;

  return (
    <div className={`legal-source ${className}`.trim()}>
      {heading && <strong>{heading}</strong>}
      {label && <span className="legal-source-label">{label}</span>}
      {href && (
        <a className="source-link" href={href} target="_blank" rel="noopener noreferrer">
          <Icon name="external" size={14} />
          فتح المصدر الرسمي
        </a>
      )}
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <header className="page-header animate-enter">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}

export function Panel({ className = "", children, ...props }) {
  return <section className={`panel ${className}`.trim()} {...props}>{children}</section>;
}

export function Button({ variant = "primary", size = "md", icon, children, className = "", ...props }) {
  const sizeClass = size === "sm" ? "button-sm" : "";
  return (
    <button className={`button button-${variant} ${sizeClass} ${className}`.trim()} {...props}>
      {icon && <Icon name={icon} size={size === "sm" ? 15 : 17} />}
      {children != null && <span>{children}</span>}
    </button>
  );
}

export function LoadingState({ label = "جارٍ تحميل البيانات..." }) {
  return (
    <div className="state-card loading-state" role="status">
      <span className="spinner" />
      <span>{label}</span>
    </div>
  );
}

export function SkeletonCards({ count = 3 }) {
  return (
    <div className="grid gap-3" aria-hidden="true">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="rounded-xl border border-slate-200 bg-white p-4 grid gap-3">
          <div className="skeleton skeleton-line short" />
          <div className="skeleton skeleton-line" />
          <div className="skeleton skeleton-line medium" />
        </div>
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="state-card error-state" role="alert">
      <Icon name="alert" size={22} />
      <div>
        <strong>تعذّر تحميل المحتوى</strong>
        <p>{message}</p>
      </div>
      {onRetry && (
        <Button variant="secondary" size="sm" icon="refresh" onClick={onRetry}>
          إعادة المحاولة
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ title, description, icon = "book" }) {
  return (
    <div className="empty-state">
      <span className="empty-icon"><Icon name={icon} size={23} /></span>
      <strong>{title}</strong>
      {description && <p>{description}</p>}
    </div>
  );
}

const statusMeta = [
  { match: /ساري|نافذ|active|in_force|effective|valid/i, label: "ساري", className: "badge-success" },
  { match: /ملغ|منسوخ|repeal|cancel|inactive/i, label: "ملغى", className: "badge-danger" },
  { match: /معدل|معدّل|amend/i, label: "معدّل", className: "badge-warning" },
  { match: /مرجع خارجي/i, label: "مرجع خارجي", className: "badge-neutral" }
];

export function StatusBadge({ status }) {
  const value = String(status || "");
  const item = statusMeta.find((candidate) => candidate.match.test(value));
  const label = item?.label || (/[\u0600-\u06ff]/.test(value) ? value : "غير محدد");
  return <span className={`badge ${item?.className || "badge-neutral"}`}>{label}</span>;
}

function finiteScore(value) {
  if ((typeof value !== "number" && typeof value !== "string") || (typeof value === "string" && !value.trim())) return null;
  const score = Number(value);
  return Number.isFinite(score) ? score : null;
}

export function SimilarityBadge({ article, className = "", showMeter = false }) {
  const cosine = finiteScore(article?.cosine_similarity);
  const fallback = finiteScore(article?.similarity);
  if (article?.rank_status === "unranked" && (cosine ?? 0) === 0 && (fallback ?? 0) === 0) return null;
  const score = cosine == null ? fallback : cosine;
  if (score == null) return null;
  const formatted = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
    useGrouping: false
  }).format(score);
  const pct = Math.max(0, Math.min(100, Math.round(score * 100)));
  const explanation = `درجة التشابه الدلالي بين النصوص: ${formatted}. لا تمثل صحة الحكم القانوني أو درجة اليقين.`;

  return (
    <span className={`similarity-badge ${showMeter ? "similarity-meter" : ""} ${className}`.trim()} title={explanation} aria-label={explanation}>
      <span>تشابه دلالي</span>
      {showMeter && (
        <span className="similarity-bar-track" aria-hidden="true">
          <span className="similarity-bar-fill" style={{ width: `${pct}%`, display: "block" }} />
        </span>
      )}
      <bdi dir="ltr">{formatted}</bdi>
    </span>
  );
}

const relationMeta = {
  repeals: ["إلغاء تشريعي", "relation-repeal"],
  repealed_by: ["إلغاء تشريعي", "relation-repeal"],
  amends: ["تعديل", "relation-amendment"],
  amended_by: ["تعديل", "relation-amendment"],
  overlaps_with: ["تداخل / تقاطع أحكام", "relation-overlap"],
  contradicts: ["تعارض تشريعي", "relation-contradiction"],
  references: ["إحالة تشريعية", "relation-reference"],
  protects_over: ["حماية تشريعية", "relation-protection"],
  implements: ["تنفيذ تشريعي", "relation-implementation"],
  details_or_links: ["ارتباط تنظيمي", "relation-links"],
  issued_under: ["صادر بموجب", "relation-implementation"],
  possible_implicit_repeal: ["إلغاء ضمني محتمل", "relation-repeal"]
};

export function relationLabel(value) {
  const key = String(value || "").replace(/^incoming_/, "").toLowerCase();
  return relationMeta[key]?.[0] || "ارتباط تشريعي";
}

export function legislationTypeLabel(value) {
  const text = String(value || "").trim();
  if (!text) return "نوع التشريع غير محدد";
  if (/[\u0600-\u06ff]/.test(text)) return text;
  const labels = {
    regulation: "نظام",
    regulations: "أنظمة",
    law: "قانون",
    statute: "قانون",
    bylaw: "نظام داخلي",
    instruction: "تعليمات",
    instructions: "تعليمات",
    decision: "قرار"
  };
  return labels[text.toLowerCase()] || "تشريع";
}

export function RelationBadge({ relation }) {
  const key = String(relation || "").replace(/^incoming_/, "").toLowerCase();
  const [label, className] = relationMeta[key] || ["ارتباط تشريعي", "relation-links"];
  return <span className={`badge relation-badge ${className}`}>{label}</span>;
}

export function StatCard({ label, value, note, icon, tone = "default", loading = false }) {
  return (
    <article className={`stat-card stat-${tone}`}>
      <div className="stat-top">
        <span>{label}</span>
        <span className="stat-icon"><Icon name={icon} size={19} /></span>
      </div>
      {loading ? (
        <div className="skeleton h-8 w-20 my-1" />
      ) : (
        <strong className="stat-value">{value ?? "—"}</strong>
      )}
      {note && <span className="stat-note">{note}</span>}
    </article>
  );
}

export function ArticleReference({ article, onOpen }) {
  const item = article && typeof article === "object" ? article : {};
  const title = item.legislation_title || item.title || "تشريع غير محدد";
  const number = item.article_number ?? item.articleNumber;
  const id = item.id || item.article_id || (number != null ? String(number) : null);
  return (
    <button className="reference-link" type="button" disabled={!id} onClick={() => onOpen?.(id)}>
      <Icon name="book" size={16} />
      <span>{number == null ? title : `المادة ${number} — ${title}`}</span>
      <Icon name="arrow" size={15} />
    </button>
  );
}

export function NavLinkItem({ to, icon, badge, children, onClick }) {
  return (
    <NavLink to={to} end={to === "/"} className="nav-link" onClick={onClick}>
      <span className="nav-link-icon"><Icon name={icon} size={18} /></span>
      <span>{children}</span>
      {badge && <span className="nav-link-badge">{badge}</span>}
    </NavLink>
  );
}
