"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type Run = { trace_id: string; name: string; status: string; duration_ms?: number; event_count: number; started_at: string; incidents?: unknown[] };
type Project = { id: string; name: string; created_at: string };

const proxy = (path: string) => `/api/proxy/${path}`;

function formatDuration(ms?: number) { return ms == null ? "—" : ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(2)}s`; }
function formatDate(value: string) { return new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }

export default function Home() {
  const [project, setProject] = useState<Project | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetch(proxy("v1/project")).then(async (r) => r.ok ? r.json() : Promise.reject(new Error((await r.json()).detail || "Could not load project"))), fetch(proxy("v1/runs?limit=100")).then(async (r) => r.ok ? r.json() : Promise.reject(new Error((await r.json()).detail || "Could not load runs")))])
      .then(([projectData, runsData]) => { setProject(projectData); setRuns(runsData.items); })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => runs.filter((run) => (!status || run.status === status) && (!query || `${run.name} ${run.trace_id}`.toLowerCase().includes(query.toLowerCase()))), [runs, query, status]);
  const failed = runs.filter((run) => run.status === "failed").length;
  const incidents = runs.reduce((total, run) => total + (run.incidents?.length || 0), 0);

  if (loading) return <div className="empty">Loading your workspace…</div>;
  if (error) return <Onboarding message={error} />;
  return <>
    <div className="hero"><div><div className="eyebrow">Observability workspace</div><h1>{project?.name || "Your project"}</h1><p className="lede">Follow multi-agent execution from handoff to tool call, with evidence-backed incidents instead of guesswork.</p></div><div className="hero-actions"><Link href="/settings" className="button button-secondary">Project settings</Link></div></div>
    <div className="grid-4"><div className="stat-card"><div className="stat-label">Recent runs</div><div className="stat-value">{runs.length}</div></div><div className="stat-card"><div className="stat-label">Failed runs</div><div className="stat-value">{failed}</div></div><div className="stat-card"><div className="stat-label">Policy incidents</div><div className="stat-value">{incidents}</div></div><div className="stat-card"><div className="stat-label">Project ID</div><div className="stat-value mono" style={{fontSize: 14}}>{project?.id.slice(0, 8)}…</div></div></div>
    <section className="panel"><div className="panel-header"><h2>Recent execution runs</h2><span className="cell">{filtered.length} shown</span></div><div className="filters"><input className="input" placeholder="Search runs or trace IDs" value={query} onChange={(event) => setQuery(event.target.value)} /><select className="select" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option><option value="succeeded">Succeeded</option><option value="failed">Failed</option><option value="running">Running</option></select></div>{filtered.length === 0 ? <div className="empty"><strong>No matching runs</strong>Run the travel-booking demo to send a real trace here.</div> : filtered.map((run) => <Link href={`/runs/${encodeURIComponent(run.trace_id)}`} className="run-row" key={run.trace_id}><div><div className="run-name">{run.name}</div><div className="run-id">{run.trace_id}</div></div><div><span className={`badge badge-${run.status}`}>{run.status}</span></div><div className="cell hide-mobile">{formatDuration(run.duration_ms)}</div><div className="cell hide-mobile">{run.event_count} events</div><div className="cell hide-mobile">{formatDate(run.started_at)}</div><div className="arrow">›</div></Link>)}</section>
  </>;
}

function Onboarding({ message }: { message: string }) { return <div><div className="hero"><div><div className="eyebrow">First connection</div><h1>Bring your agents into focus.</h1><p className="lede">{message} Connect the SDK, run one workflow, and the trace will appear in this workspace.</p></div></div><div className="onboarding"><div><h2>Connect your Python application</h2><div className="step"><span className="step-number">1</span><div><strong>Install the SDK</strong><p>Use the local package while developing, or install the published package when available.</p></div></div><div className="step"><span className="step-number">2</span><div><strong>Configure the environment</strong><p>Set the API URL, project ID, and one-time API key in the application that runs your agents.</p></div></div><div className="step"><span className="step-number">3</span><div><strong>Run a trace</strong><p>Open Runs to inspect actual persisted events, handoffs, tool calls, and incidents.</p></div></div></div><div><pre className="code"><span className="key">pip install</span> -e packages/python-sdk{`\n\n`}<span className="key">export</span> SPANTRACE_API_URL=http://localhost:8070{`\n`}<span className="key">export</span> SPANTRACE_PROJECT_ID=&lt;project-id&gt;{`\n`}<span className="key">export</span> SPANTRACE_API_KEY=&lt;one-time-key&gt;{`\n\n`}<span className="key">from</span> spantrace <span className="key">import</span> SpanTrace{`\n\n`}scope = SpanTrace.from_env(){`\n`}provider, adapter = scope.instrument_opentelemetry(service_name=<span className="string">"my-workflow"</span>){`\n`}<span className="key">with</span> provider.get_tracer(<span className="string">"my-app"</span>).start_as_current_span(<span className="string">"planner"</span>):{`\n`}    planner.run(request)</pre></div></div></div>; }
