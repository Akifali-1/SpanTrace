"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type ThemePreference = "dark" | "light" | "system";

const STORAGE_KEY = "spantrace-theme";

function systemTheme(): "dark" | "light" {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function applyTheme(preference: ThemePreference) {
  const resolved = preference === "system" ? systemTheme() : preference;
  document.documentElement.dataset.theme = resolved;
}

const themeBootstrap = `(() => {
  try {
    const preference = localStorage.getItem("${STORAGE_KEY}");
    const resolved = preference === "light" || preference === "dark" ? preference : "dark";
    document.documentElement.dataset.theme = resolved;
  } catch (_) {}
})();`;

type ThemeContextValue = {
  preference: ThemePreference;
  setPreference: (preference: ThemePreference) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>("dark");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    const initial = stored === "light" || stored === "dark" || stored === "system" ? stored : "dark";
    setPreferenceState(initial);
    applyTheme(initial);
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const updateForSystem = () => { if (initial === "system") applyTheme(initial); };
    media.addEventListener?.("change", updateForSystem);
    return () => media.removeEventListener?.("change", updateForSystem);
  }, []);

  const value = useMemo(() => ({
    preference,
    setPreference: (next: ThemePreference) => {
      window.localStorage.setItem(STORAGE_KEY, next);
      applyTheme(next);
      setPreferenceState(next);
    },
  }), [preference]);

  return <ThemeContext.Provider value={value}>
    <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
    {children}
  </ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used within ThemeProvider");
  return context;
}
