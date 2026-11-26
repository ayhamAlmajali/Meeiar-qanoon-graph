import { useCallback, useMemo, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useApp } from "../../context/AppContext";
import { PageActionsProvider } from "../../context/PageActionsContext";
import ArticleDetailDialog from "../legislation/ArticleDetailDialog";
import { Icon, NavLinkItem } from "../common/UI";

const pageTitles = {
  "/": "لوحة القيادة",
  "/ask": "الاستعلام التشريعي",
  "/audit": "مدقق الامتثال والمسودات",
  "/graph": "الخريطة التشريعية",
  "/timeline": "الجدول الزمني"
};

export default function AppShell() {
  const { health, refreshData } = useApp();
  const [articleIdentifier, setArticleIdentifier] = useState(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();
  const pageTitle = pageTitles[location.pathname] || "منصة معيار";

  const openArticle = useCallback((identifier) => {
    if (identifier != null && String(identifier).trim()) setArticleIdentifier(String(identifier));
  }, []);
  const actionValue = useMemo(() => ({ openArticle }), [openArticle]);
  const closeArticle = useCallback(() => setArticleIdentifier(null), []);
  const closeMobileMenu = () => setMobileMenuOpen(false);

  const healthLabel = health.status === "online"
    ? "الخدمة متصلة"
    : health.status === "checking"
      ? "جارٍ التحقق"
      : health.status === "degraded"
        ? "استجابة جزئية"
        : "الخدمة غير متاحة";

  return (
    <PageActionsProvider value={actionValue}>
      <div className="app-shell" dir="rtl">
        {mobileMenuOpen && <button className="mobile-backdrop" aria-label="إغلاق القائمة" onClick={closeMobileMenu} />}
        <aside className={`sidebar${mobileMenuOpen ? " sidebar-open" : ""}`}>
          <Link className="brand-card" to="/" onClick={closeMobileMenu}>
            <img src="/assets/maeyar-logo.png" alt="معيار - MEEIAR" />
            <div className="brand-tagline">
              <span className="brand-tagline-dot" />
              <span>الذكاء التشريعي الأردني</span>
            </div>
          </Link>

          <div className="nav-section">
            <div className="nav-caption">نظرة عامة</div>
            <nav className="main-nav" aria-label="التنقل العام">
              <NavLinkItem to="/" icon="home" onClick={closeMobileMenu}>لوحة القيادة</NavLinkItem>
            </nav>
          </div>

          <div className="nav-section">
            <div className="nav-caption">أدوات الذكاء القانوني</div>
            <nav className="main-nav" aria-label="مساحات التحليل">
              <NavLinkItem to="/ask" icon="ask" badge="AI" onClick={closeMobileMenu}>الاستعلام التشريعي</NavLinkItem>
              <NavLinkItem to="/audit" icon="audit" onClick={closeMobileMenu}>مدقق الامتثال والمسودات</NavLinkItem>
              <NavLinkItem to="/graph" icon="graph" onClick={closeMobileMenu}>الخريطة التشريعية</NavLinkItem>
              <NavLinkItem to="/timeline" icon="timeline" onClick={closeMobileMenu}>الجدول الزمني</NavLinkItem>
            </nav>
          </div>

          <div className="sidebar-bottom">
            <div className="sidebar-assurance">
              <Icon name="shield" size={18} />
              <div>
                <strong>تحليل موثّق بالمصدر</strong>
                <span>كل نتيجة مرتبطة بنص المادة التشريعية ومرجعها الرسمي.</span>
              </div>
            </div>
            <div className="sidebar-attribution">
              <strong>Al-Saif wal-Qalam | السيف والقلم</strong>
              <span>جامعة مؤتة · الأردن</span>
              <span>هاكاثون التشريعات الذكية</span>
            </div>
          </div>
        </aside>

        <main className="main-content">
          <header className="topbar">
            <div className="topbar-leading">
              <button
                className="mobile-menu-button"
                type="button"
                aria-label="فتح القائمة"
                aria-expanded={mobileMenuOpen}
                onClick={() => setMobileMenuOpen(true)}
              >
                <Icon name="menu" size={20} />
              </button>
              <nav className="breadcrumb" aria-label="مسار التنقل">
                <Link to="/">الرئيسية</Link>
                <span className="breadcrumb-sep">/</span>
                <strong>{pageTitle}</strong>
              </nav>
            </div>
            <div className="topbar-actions">
              <button
                type="button"
                className="topbar-refresh-btn"
                title="تحديث حالة الاتصال والبيانات"
                onClick={refreshData}
              >
                <Icon name="refresh" size={14} />
                <span>تحديث</span>
              </button>
              <div className={`health-indicator health-${health.status}`} role="status" aria-live="polite">
                <span className="health-dot" />
                <span>{healthLabel}</span>
              </div>
            </div>
          </header>

          {health.status === "offline" && (
            <div className="connection-banner" role="alert">
              <div className="connection-banner-body">
                <Icon name="alert" size={20} />
                <div>
                  <strong>تعذّر الوصول إلى خدمة معيار</strong>
                  <p>
                    تحقق من تشغيل FastAPI على <bdi dir="ltr">{import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"}</bdi>. ستُحدّث حالة الاتصال تلقائياً.
                  </p>
                </div>
              </div>
              <button type="button" className="button button-secondary button-sm" onClick={refreshData}>
                <Icon name="refresh" size={14} />
                <span>إعادة الفحص</span>
              </button>
            </div>
          )}

          <div className="page-container">
            <Outlet />
          </div>

          <footer className="app-footer">
            <span>MEEIAR | مِعيار</span>
            <span>Developed by Al-Saif wal-Qalam | السيف والقلم · جامعة مؤتة · هاكاثون التشريعات الذكية</span>
            <span>© {new Date().getFullYear()} السيف والقلم — جميع الحقوق محفوظة</span>
          </footer>
        </main>
        <ArticleDetailDialog identifier={articleIdentifier} onClose={closeArticle} onOpenArticle={openArticle} />
      </div>
    </PageActionsProvider>
  );
}
