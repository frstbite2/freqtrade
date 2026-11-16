"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

/**
 * Demo: the design prototype's sample values, each one badged DEMO.
 * Live: only what the backend really returns; everything else shows as unavailable.
 */
export type DataMode = "demo" | "live";

const KEY = "orbit.dataMode";
const DataModeContext = createContext<{ mode: DataMode; setMode: (m: DataMode) => void }>({
  mode: "demo",
  setMode: () => {},
});

export function DataModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<DataMode>("demo");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(KEY);
      if (saved === "demo" || saved === "live") setModeState(saved);
    } catch {
      // Storage can be blocked (private windows); the default is fine.
    }
  }, []);

  const setMode = useCallback((m: DataMode) => {
    setModeState(m);
    try {
      window.localStorage.setItem(KEY, m);
    } catch {
      // Not remembered across visits; still switched for this one.
    }
  }, []);

  return <DataModeContext.Provider value={{ mode, setMode }}>{children}</DataModeContext.Provider>;
}

export function useDataMode() {
  return useContext(DataModeContext);
}
