"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Activity,
  Bug,
  Boxes,
  ChevronDown,
  CircleDot,
  GitBranch,
  LayoutDashboard,
  Menu,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Settings2,
  ShieldAlert,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import ThemeToggle from "./theme-toggle";

type NavigationItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

const navigation: NavigationItem[] = [
  { href: "/v1", label: "Overview", icon: LayoutDashboard },
  { href: "/traces", label: "Traces", icon: Activity },
  { href: "/repositories", label: "Repositories", icon: GitBranch },
  { href: "/executions", label: "Executions", icon: Boxes },
  { href: "/incidents", label: "Incidents", icon: ShieldAlert },
  { href: "/evaluations", label: "Evaluations", icon: CircleDot },
  { href: "/investigations", label: "Investigations", icon: Bug },
];

const configuration: NavigationItem[] = [
  { href: "/repositories", label: "Instrumentation", icon: Network },
  { href: "/settings#integrations", label: "Integrations", icon: CircleDot },
  { href: "/settings", label: "Settings", icon: Settings2 },
];

function isCurrent(pathname: string, item: NavigationItem) {
  if (item.label === "Repositories") return pathname === "/repositories";
  if (item.label === "Instrumentation") return pathname.startsWith("/repositories/");
  const href = item.href;
  const route = href.split("#")[0];
  if (route === "/traces") return pathname.startsWith("/traces") || pathname.startsWith("/runs/");
  return pathname === route || pathname.startsWith(`${route}/`);
}

function NavLink({ item, pathname, onNavigate }: { item: NavigationItem; pathname: string; onNavigate: () => void }) {
  const Icon = item.icon;
  const active = isCurrent(pathname, item);
  return (
    <Link href={item.href} prefetch={true} className={`sidebar-link${active ? " is-active" : ""}`} aria-current={active ? "page" : undefined} aria-label={item.label} title={item.label} onClick={onNavigate}>
      <Icon size={16} strokeWidth={1.8} aria-hidden="true" />
      <span>{item.label}</span>
    </Link>
  );
}

function Sidebar({ open, collapsed, onClose, onToggle }: { open: boolean; collapsed: boolean; onClose: () => void; onToggle: () => void }) {
  const pathname = usePathname();
  return (
    <aside className={`sidebar${open ? " is-open" : ""}`} aria-label="Primary navigation">
      <div className="sidebar-top">
        <Link href="/" className="brand" onClick={onClose}>
          <span className="brand-mark"><img src="/icon.svg" alt="" /></span>
          <span>SpanTrace</span>
        </Link>
      </div>

      <div className="workspace-switcher" role="button" tabIndex={0} aria-label="Current workspace: local development">
        <span className="workspace-avatar">L</span>
        <span className="workspace-copy"><strong>Local workspace</strong><small>Development</small></span>
        <ChevronDown size={15} className="workspace-chevron" aria-hidden="true" />
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section-label">Workspace</div>
        {navigation.map((item) => <NavLink item={item} pathname={pathname} onNavigate={onClose} key={item.href} />)}
        <div className="nav-section-label nav-section-spaced">Configuration</div>
        {configuration.map((item) => <NavLink item={item} pathname={pathname} onNavigate={onClose} key={`${item.href}-${item.label}`} />)}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-footer-line"><span className="status-dot" /> API connected</div>
        <div className="sidebar-footer-note">Project-scoped telemetry</div>
      </div>
    </aside>
  );
}

function TopBar({ onMenu, onSidebarToggle, collapsed }: { onMenu: () => void; onSidebarToggle: () => void; collapsed: boolean }) {
  const pathname = usePathname();
  const label = pathname === "/v1" ? "Overview" : pathname.startsWith("/runs/") ? "Traces" : pathname.startsWith("/repositories/") ? "Instrumentation" : pathname.split("/")[1]?.replace(/[-_]/g, " ") || "Workspace";
  const currentLabel = label.charAt(0).toUpperCase() + label.slice(1);
  return (
    <header className="topbar">
      <button type="button" className="icon-button mobile-menu" onClick={onMenu} aria-label="Open navigation"><Menu size={19} /></button>
      <button type="button" className="icon-button desktop-sidebar-toggle" onClick={onSidebarToggle} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
        {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
      </button>
      <div className="topbar-context"><span>SpanTrace</span><span className="context-divider">/</span><strong>{currentLabel}</strong></div>
      <div className="topbar-actions">
        <span className="topbar-status"><span className="status-dot" /> Live workspace</span>
        <ThemeToggle />
        <Link href="/settings" className="topbar-avatar" aria-label="Open settings">L</Link>
      </div>
    </header>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem("spantrace-sidebar");
    setCollapsed(stored === "collapsed");
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setMenuOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  function toggleSidebar() {
    setCollapsed((value) => {
      const next = !value;
      window.localStorage.setItem("spantrace-sidebar", next ? "collapsed" : "expanded");
      return next;
    });
  }

  if (pathname === "/" || pathname === "/how-it-works") return <>{children}</>;

  return (
    <div className={`app-shell${collapsed ? " is-sidebar-collapsed" : ""}`}>
      <Sidebar open={menuOpen} collapsed={collapsed} onClose={() => setMenuOpen(false)} onToggle={toggleSidebar} />
      {menuOpen && <button type="button" className="sidebar-backdrop" onClick={() => setMenuOpen(false)} aria-label="Close navigation" />}
      <div className="app-main">
        <TopBar collapsed={collapsed} onSidebarToggle={toggleSidebar} onMenu={() => setMenuOpen(true)} />
        <main className="page-shell">{children}</main>
      </div>
    </div>
  );
}
