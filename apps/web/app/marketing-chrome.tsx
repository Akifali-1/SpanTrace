import ThemeToggle from "./components/theme-toggle";

type MarketingPage = "landing" | "how-it-works";

export function MarketingHeader({ current }: { current: MarketingPage }) {
  const homeHref = current === "landing" ? "#trace" : "/";

  return (
    <div className="site-header">
      <a className="wordmark" href={homeHref} data-span="brand">SPANTRACE<span className="wordmark-slash">/</span></a>
      <span className="header-note">multi-agent observability · incident replay</span>
      <a className={`header-how ${current === "how-it-works" ? "is-active" : ""}`} href="/how-it-works" aria-current={current === "how-it-works" ? "page" : undefined}>How It Works</a>
       <ThemeToggle compact />
       <a className="header-v1" href="/v1">v1 dashboard</a>
    </div>
  );
}

export function MarketingFooter({ backHref = "/" }: { backHref?: string }) {
  return (
    <footer className="site-footer" data-span="footer">
      <div className="footer-wordmark" data-reveal>SPANTRACE<span>/</span></div>
      <div className="footer-bottom"><span>evidence over guesswork</span><span>illustrative product workflow</span><a href={backHref}>{backHref === "/" ? "back to landing ↑" : "back to trace ↑"}</a></div>
    </footer>
  );
}
