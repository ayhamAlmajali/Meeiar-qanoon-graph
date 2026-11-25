import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import DashboardPage from "./pages/DashboardPage";
import AskPage from "./pages/AskPage";
import AuditPage from "./pages/AuditPage";
import GraphPage from "./pages/GraphPage";
import TimelinePage from "./pages/TimelinePage";
export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="ask" element={<AskPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="graph" element={<GraphPage />} />
        <Route path="timeline" element={<TimelinePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
