import type { Metadata } from "next";
import "./globals.css";
import AppShell from "./components/app-shell";
import { ThemeProvider } from "./components/theme-provider";

export const metadata: Metadata = {
  title: "SpanTrace — evidence over guesswork",
  description: "Replay a multi-agent incident from trace to verified fix.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: `(() => { try { const value = localStorage.getItem("spantrace-theme"); document.documentElement.dataset.theme = value === "light" ? "light" : "dark"; } catch (_) { document.documentElement.dataset.theme = "dark"; } })();` }} /></head>
      <body suppressHydrationWarning>
        <ThemeProvider><AppShell>{children}</AppShell></ThemeProvider>
      </body>
    </html>
  );
}
