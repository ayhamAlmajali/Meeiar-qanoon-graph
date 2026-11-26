import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "../services/api";

const AppContext = createContext(null);

export function AppProvider({ children }) {
  const [health, setHealth] = useState({ status: "checking", checkedAt: null });
  const [refreshVersion, setRefreshVersion] = useState(0);

  const refreshData = useCallback(() => setRefreshVersion((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    let controller;
    let timeoutId;

    const checkHealth = async () => {
      controller = new AbortController();
      timeoutId = window.setTimeout(() => controller.abort(), 15000);
      try {
        const result = await api.health({ signal: controller.signal });
        window.clearTimeout(timeoutId);
        if (active) {
          setHealth({
            status: result?.status === "ok" ? "online" : "degraded",
            checkedAt: Date.now()
          });
        }
      } catch (error) {
        window.clearTimeout(timeoutId);
        if (active) {
          setHealth({ status: "offline", checkedAt: Date.now() });
        }
      }
    };

    void checkHealth();
    const interval = window.setInterval(checkHealth, 30000);
    return () => {
      active = false;
      window.clearTimeout(timeoutId);
      window.clearInterval(interval);
      controller?.abort();
    };
  }, [refreshVersion]);

  const value = useMemo(
    () => ({ health, refreshData, refreshVersion }),
    [health, refreshData, refreshVersion]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) throw new Error("useApp must be used within AppProvider");
  return context;
}
