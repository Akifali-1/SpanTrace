import type { CSSProperties, ReactNode } from "react";

export type ActivityPoint = {
  label: string;
  events: number;
  duration: number;
};

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div className="page-header-copy">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p className="lede">{description}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  );
}

export function BentoCard({
  title,
  description,
  action,
  className = "",
  children,
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`bento-card ${className}`}>
      {(title || description || action) && (
        <div className="card-header">
          <div>{title && <h2>{title}</h2>}{description && <p>{description}</p>}</div>
          {action && <div className="card-action">{action}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const normalized = status.toLowerCase();
  const tone = normalized === "succeeded" || normalized === "completed" || normalized === "analysis_complete" || normalized === "events_received" || normalized === "passed"
    ? "success"
    : normalized === "failed" || normalized === "error" || normalized === "critical" || normalized === "high" || normalized === "infrastructure_error" || normalized === "timed_out"
      ? "danger"
      : normalized === "warning" || normalized === "medium" || normalized === "running" || normalized === "queued" || normalized === "analyzing" || normalized === "partially_observed" || normalized === "partially_analyzed"
        ? "warning"
        : "neutral";
  return <span className={`status-badge status-${tone}`}><span className="status-badge-dot" />{label || normalized.replaceAll("_", " ")}</span>;
}

export function MetricCard({
  label,
  value,
  detail,
  points,
  accent = "blue",
  delay = 0,
}: {
  label: string;
  value: string | number;
  detail: string;
  points?: number[];
  accent?: "blue" | "violet" | "cyan" | "red" | "amber";
  delay?: number;
}) {
  return (
    <article className={`metric-card metric-${accent}`} style={{ "--entry-delay": `${delay}ms` } as CSSProperties}>
      <div className="metric-top"><span className="metric-label">{label}</span><span className="metric-accent" /></div>
      <strong className="metric-value">{value}</strong>
      <div className="metric-bottom"><span>{detail}</span>{points && <Sparkline points={points} color={`var(--${accent})`} />}</div>
    </article>
  );
}

export function Sparkline({ points, color = "var(--blue)" }: { points: number[]; color?: string }) {
  if (points.length < 2) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const path = points.map((point, index) => {
    const x = (index / (points.length - 1)) * 96 + 2;
    const y = 28 - ((point - min) / range) * 23;
    return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(" ");
  return <svg className="sparkline" viewBox="0 0 100 32" role="img" aria-label="Trend sparkline"><path d={path} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" /></svg>;
}

export function ActivityChart({ points }: { points: ActivityPoint[] }) {
  if (!points.length) return <div className="chart-empty">No captured activity in this workspace yet.</div>;
  const width = 720;
  const height = 224;
  const padding = { left: 18, right: 12, top: 16, bottom: 30 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const peak = Math.max(...points.map((point) => Math.max(point.events, point.duration)), 1);
  const xFor = (index: number) => padding.left + (index / Math.max(points.length - 1, 1)) * chartWidth;
  const yFor = (value: number) => padding.top + chartHeight - (value / peak) * chartHeight;
  const durationPath = points.map((point, index) => `${index === 0 ? "M" : "L"}${xFor(index).toFixed(1)} ${yFor(point.duration).toFixed(1)}`).join(" ");
  return (
    <div className="activity-chart-wrap">
      <svg className="activity-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Workflow activity chart">
        {[0, 0.5, 1].map((ratio) => <line key={ratio} x1={padding.left} x2={width - padding.right} y1={padding.top + chartHeight * ratio} y2={padding.top + chartHeight * ratio} className="chart-grid-line" />)}
        {points.map((point, index) => {
          const barWidth = Math.min(36, chartWidth / points.length * 0.52);
          const x = xFor(index) - barWidth / 2;
          const y = yFor(point.events);
          return <g key={`${point.label}-${index}`} className="chart-bar-group"><title>{`${point.label}: ${point.events} events, ${point.duration}ms`}</title><rect x={x} y={y} width={barWidth} height={Math.max(2, padding.top + chartHeight - y)} rx="4" className="chart-bar" /><text x={xFor(index)} y={height - 9} textAnchor="middle" className="chart-label">{point.label}</text></g>;
        })}
        <path d={durationPath} className="chart-line" fill="none" />
        {points.map((point, index) => <circle key={`dot-${point.label}-${index}`} cx={xFor(index)} cy={yFor(point.duration)} r="3.5" className="chart-point"><title>{`${point.label}: ${point.duration}ms median duration`}</title></circle>)}
      </svg>
    </div>
  );
}

export function StatusDonut({ segments }: { segments: { label: string; value: number; color: string }[] }) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <div className="donut-layout">
      <div className="donut-chart">
        <svg viewBox="0 0 112 112" role="img" aria-label={`${total} execution runs by status`}>
          <circle cx="56" cy="56" r={radius} className="donut-track" />
          {total > 0 && segments.filter((segment) => segment.value > 0).map((segment) => {
            const length = (segment.value / total) * circumference;
            const circle = <circle key={segment.label} cx="56" cy="56" r={radius} className="donut-segment" stroke={segment.color} strokeDasharray={`${length} ${circumference - length}`} strokeDashoffset={-offset} />;
            offset += length;
            return circle;
          })}
        </svg>
        <div className="donut-total"><strong>{total}</strong><span>runs</span></div>
      </div>
      <div className="donut-legend">{segments.map((segment) => <div className="legend-row" key={segment.label}><span className="legend-swatch" style={{ background: segment.color }} /><span>{segment.label}</span><strong>{segment.value}</strong></div>)}</div>
    </div>
  );
}

export function EmptyState({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return <div className="empty-state">{icon && <div className="empty-icon">{icon}</div>}<strong>{title}</strong>{children && <p>{children}</p>}</div>;
}

export function LoadingState({ children = "Loading workspace data…" }: { children?: ReactNode }) {
  return <div className="loading-state"><span className="loading-spinner" aria-hidden="true" />{children}</div>;
}

export function ErrorState({ title, message, action }: { title: string; message: string; action?: ReactNode }) {
  return <div className="error-state"><strong>{title}</strong><p>{message}</p>{action}</div>;
}
