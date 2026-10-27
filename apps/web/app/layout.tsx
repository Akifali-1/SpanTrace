import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import AppShell from "./components/app-shell";
import { ThemeProvider } from "./components/theme-provider";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"], weight: ["400", "500", "600", "700"], display: "swap" });
const jetBrainsMono = JetBrains_Mono({ variable: "--font-mono", subsets: ["latin"], weight: ["400", "500"], display: "swap" });
const geist = Geist({ variable: "--font-geist", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const instrument = Instrument_Serif({ variable: "--font-instrument", subsets: ["latin"], weight: "400", style: ["normal", "italic"] });

export const metadata: Metadata = {
  title: "SpanTrace — evidence over guesswork",
  description: "Replay a multi-agent incident from trace to verified fix.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: `(() => { try { const value = localStorage.getItem("spantrace-theme"); document.documentElement.dataset.theme = value === "light" ? "light" : "dark"; } catch (_) { document.documentElement.dataset.theme = "dark"; } })();` }} /></head>
      <body className={`${inter.variable} ${jetBrainsMono.variable} ${geist.variable} ${geistMono.variable} ${instrument.variable}`} suppressHydrationWarning>
        <ThemeProvider><AppShell>{children}</AppShell></ThemeProvider>
      </body>
    </html>
  );
}
