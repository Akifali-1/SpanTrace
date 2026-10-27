"use client";

import Link from "next/link";
import { Activity, AlertTriangle, ArrowUpRight, BarChart3, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  ActivityChart,
  BentoCard,
  EmptyState,
  ErrorState,
  LoadingState,
  MetricCard,
  PageHeader,
  StatusBadge,
  StatusDonut,
} from "./components/ui";

type Run = {
  trace_id: string;
  name: string;
  status: string;
  duration_ms?: number;
  event_count: number;
  started_at: string;
  incidents?: Incident[];
};

type Incident = {
  title: string;
  summary: string;
  severity: string;
};

type Project = { id: string; name: string; created_at: string };
const proxy = (path: string) => `/api/proxy/${path}`;

function formatDuration(ms?: number) {
  return ms == null ? "—" : ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(2)}s`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function percentile(values: number[], ratio: number) {
  if (!values.length) return undefined;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * ratio) - 1)];
}

export default function Home() {
  const [project, setProject] = useState<Project | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(proxy("v1/project")).then(async (response) => response.ok ? response.json() : Promise.reject(new Error((await response.json()).detail || "Could not load project"))),
      fetch(proxy("v1/runs?limit=100")).then(async (response) => response.ok ? response.json() : Promise.reject(new Error((await response.json()).detail || "Could not load traces"))),
    ])
      .then(([projectData, runsData]) => { setProject(projectData); setRuns(runsData.items || []); })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  const stats = useMemo(() => {
    const successful = runs.filter((run) => run.status === "succeeded" || run.status === "completed").length;
    const durations = runs.map((run) => run.duration_ms).filter((value): value is number => value != null);
    const incidents = runs.flatMap((run) => (run.incidents || []).map((incident) => ({ ...incident, trace_id: run.trace_id, run_name: run.name, started_at: run.started_at })));
    const byStatus = (status: string) => runs.filter((run) => run.status === status).length;
    return {
      successful,
      successRate: runs.length ? `${((successful / runs.length) * 100).toFixed(1)}%` : "—",
      p95: percentile(durations, .95),
      incidents,
      status: [
        { label: "Running", value: byStatus("running"), color: "var(--info)" },
        { label: "Queued", value: byStatus("queued"), color: "var(--text-muted)" },
        { label: "Succeeded", value: successful, color: "var(--success)" },
        { label: "Failed", value: byStatus("failed"), color: "var(--danger)" },
        { label: "Cancelled", value: byStatus("cancelled"), color: "var(--warning)" },
      ],
    };
  }, [runs]);

  const activity = useMemo(() => runs.slice(0, 8).reverse().map((run) => ({
    label: new Date(run.started_at).toLocaleDateString([], { month: "short", day: "numeric" }),
    events: run.event_count,
    duration: run.duration_ms || 0,
    traceName: run.name,
    status: run.status,
  })), [runs]);
  const activityLabels = useMemo(() => {
    const days = new Set(runs.slice(0, 8).map((run) => new Date(run.started_at).toLocaleDateString()));
    return days.size <= 1 ? runs.slice(0, 8).reverse().map((run) => new Date(run.started_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })) : null;
  }, [runs]);
  const activityPoints = activity.map((point, index) => ({ ...point, label: activityLabels?.[index] || point.label }));
  const successPercent = runs.length ? (stats.successful / runs.length) * 100 : 0;
  const spark = runs.slice(0, 8).map((run) => run.event_count).reverse();

  if (loading) return <LoadingState />;
  if (error) return <ErrorState title="Workspace unavailable" message={error} action={<Link href="/settings" className="button button-secondary">Open settings</Link>} />;
  if (!project) return <ErrorState title="Project unavailable" message="The configured project could not be returned by the API." />;

  return <>
    <PageHeader
      eyebrow="Workspace overview"
      title={project.name}
      description="A compact view of captured traces, workflow activity, controlled runs, and evidence-backed incidents."
      actions={<><Link href="/repositories" className="button button-primary">Map a repository <ArrowUpRight size={14} /></Link><Link href="/traces" className="button button-secondary">Explore traces</Link></>}
    />

    {runs.length === 0 && <section className="panel onboarding dashboard-onboarding"><div><div className="eyebrow">First connection</div><h2>Bring your agents into focus.</h2><p className="lede">Connect the SDK, run one workflow, and the first trace will appear in this workspace. The dashboard stays grounded in persisted telemetry.</p><div className="step"><span className="step-number">1</span><div><strong>Install the SDK</strong><p>Use the local Python package while developing your instrumented workflow.</p></div></div><div className="step"><span className="step-number">2</span><div><strong>Configure the workspace</strong><p>Set the API URL, project ID, and one-time key in the application that runs your agents.</p></div></div><div className="step"><span className="step-number">3</span><div><strong>Run a trace</strong><p>Return to Traces to inspect captured spans, tool calls, handoffs, and incidents.</p></div></div></div><pre className="code"><span className="key">export</span> SPANTRACE_API_URL=http://localhost:8070{`\n`}<span className="key">export</span> SPANTRACE_PROJECT_ID=&lt;project-id&gt;{`\n`}<span className="key">export</span> SPANTRACE_API_KEY=&lt;one-time-key&gt;{`\n\n`}<span className="key">from</span> spantrace <span className="key">import</span> SpanTrace{`\n\n`}scope = SpanTrace.from_env(){`\n`}provider, adapter = scope.instrument_opentelemetry(service_name=<span className="string">"my-workflow"</span>)</pre></section>}

    <div className="grid-4">
      <MetricCard label="Total traces" value={runs.length} detail="Captured in this project" points={spark} icon={<Activity size={16} />} accent="blue" delay={0} />
      <MetricCard label="Success rate" value={stats.successRate} detail={`${stats.successful} successful traces`} points={runs.map((run) => run.status === "succeeded" ? 1 : 0).reverse()} icon={<Activity size={16} />} valueTone={runs.length === 0 ? "default" : successPercent >= 95 ? "success" : successPercent >= 80 ? "warning" : "danger"} accent="cyan" delay={35} />
      <MetricCard label="P95 latency" value={formatDuration(stats.p95)} detail="End-to-end observed duration" points={runs.map((run) => run.duration_ms || 0).reverse()} icon={<Activity size={16} />} accent="violet" delay={70} />
      <MetricCard label="Active incidents" value={stats.incidents.length} detail="Evidence-backed findings" points={runs.map((run) => (run.incidents || []).length).reverse()} icon={<AlertTriangle size={16} />} valueTone={stats.incidents.length ? "danger" : "success"} accent="red" delay={105} />
    </div>

    <div className="bento-grid">
      <BentoCard className="dashboard-chart" title="Workflow activity" description="Captured events and observed duration across recent traces" action={<span className="card-period">Recent traces</span>}>
         <ActivityChart points={activityPoints} />
        <div className="chart-legend"><span className="legend-item"><span className="legend-swatch" style={{ background: "var(--primary)" }} />Events</span><span className="legend-item"><span className="legend-line" style={{ background: "var(--info)" }} />Observed duration</span></div>
      </BentoCard>

      <BentoCard className="dashboard-status" title="Execution status" description="Current status across captured workflow traces" action={<Link href="/executions" className="text-link">View all <ArrowUpRight size={13} /></Link>}>
        <StatusDonut segments={stats.status} />
      </BentoCard>

      <BentoCard className="dashboard-traces" title="Recent traces" description="Latest execution traces across the project" action={<Link href="/traces" className="text-link">View all <ArrowUpRight size={13} /></Link>}>
         {runs.length === 0 ? <EmptyState title="No traces captured yet" icon={<BarChart3 size={17} />}><span>Connect an instrumented workflow and run it once to populate this view.</span></EmptyState> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Trace</th><th>Duration</th><th>Status</th><th>Started</th><th /></tr></thead><tbody>{runs.slice(0, 6).map((run) => <tr key={run.trace_id} className="clickable-row" tabIndex={0} onClick={() => { window.location.href = `/runs/${encodeURIComponent(run.trace_id)}`; }} onKeyDown={(event) => { if (event.key === "Enter") window.location.href = `/runs/${encodeURIComponent(run.trace_id)}`; }}><td><Link href={`/runs/${encodeURIComponent(run.trace_id)}`} className="dashboard-trace-link"><span className="trace-id">{run.trace_id.slice(0, 10)}…</span><span className="trace-title">{run.name}</span></Link></td><td>{formatDuration(run.duration_ms)}</td><td><StatusBadge status={run.status} /></td><td>{formatDate(run.started_at)}</td><td><span className="table-arrow" aria-hidden="true">›</span></td></tr>)}</tbody></table></div>}
      </BentoCard>

      <BentoCard className="dashboard-activity" title="Trace intensity" description="Event volume across recent traces">
         {runs.length < 5 ? <EmptyState title="Not enough data yet" icon={<BarChart3 size={17} />}><span>Trace intensity appears after five recorded traces.</span></EmptyState> : <div className="activity-mini"><div className="mini-bars">{runs.slice(0, 12).reverse().map((run, index) => <div className="mini-bar-slot" key={run.trace_id}><strong>{run.event_count}</strong><span className="mini-bar" style={{ height: `${Math.max(8, Math.min(100, (run.event_count / Math.max(...runs.map((item) => item.event_count), 1)) * 100))}%`, animationDelay: `${index * 30}ms` }} title={`${run.event_count} events`} /></div>)}</div><div className="mini-axis"><span>Older</span><span>Recent</span></div></div>}
      </BentoCard>

      <BentoCard className="dashboard-incidents" title="Recent incidents" description="Failures that need attention" action={<Link href="/incidents" className="text-link">View all <ArrowUpRight size={13} /></Link>}>
        {stats.incidents.length === 0 ? <EmptyState title="No incidents detected" icon={<Search size={17} />}><span>Evidence-backed policy findings will appear here when a trace identifies one.</span></EmptyState> : <div className="incident-list">{stats.incidents.slice(0, 5).map((incident, index) => <Link href={`/runs/${encodeURIComponent(incident.trace_id)}`} className="incident-row" key={`${incident.trace_id}-${incident.title}-${index}`}><span className={`incident-marker${incident.severity === "medium" || incident.severity === "low" ? " warning" : ""}`} /><span><h3>{incident.title}</h3><p>{incident.run_name} · {incident.summary}</p></span><StatusBadge status={incident.severity} label={incident.severity} /><span className="incident-time">{formatDate(incident.started_at)}</span></Link>)}</div>}
      </BentoCard>
    </div>
  </>;
}
