import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "AgentScope · Multi-agent observability",
  description: "Evidence-backed traces for multi-agent systems.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <header className="topbar">
            <Link href="/" className="brand"><span className="brand-mark">A</span><span>AgentScope</span></Link>
            <nav className="nav-links" aria-label="Primary navigation">
              <Link href="/">Runs</Link>
              <Link href="/settings">Settings</Link>
            </nav>
            <div className="topbar-status"><span className="status-dot" />Local workspace</div>
          </header>
          <main className="page-shell">{children}</main>
        </div>
      </body>
    </html>
  );
}
