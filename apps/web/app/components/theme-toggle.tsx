"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { useTheme } from "./theme-provider";

export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { preference, setPreference } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const isLight = mounted && ((document.documentElement.dataset.theme || preference) === "light");
  return <button type="button" className="theme-toggle-btn" suppressHydrationWarning onClick={() => setPreference(isLight ? "dark" : "light")} aria-label={compact ? "Toggle theme" : isLight ? "Switch to dark mode" : "Switch to light mode"} title={isLight ? "Switch to dark mode" : "Switch to light mode"}>
    {isLight ? <Moon size={16} aria-hidden="true" /> : <Sun size={16} aria-hidden="true" />}
  </button>;
}
