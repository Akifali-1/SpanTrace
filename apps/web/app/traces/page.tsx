"use client";

import Link from "next/link";
import { Search, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from "../components/ui";

type Run = { trace_id: string; name: string; status: string; duration_ms?: number; event_count: number; started_at: string };
const proxy = (path: string) => `/api/proxy/${path}`;
const formatDuration = (ms?: number) => ms == null ? "—" : ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(2)}s`;
const formatDate = (value: string) => new Date(value).toLocaleString([], { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });

export default function TracesPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(proxy("v1/runs?limit=200"), { cache: "no-store" })
      .then(async (response) => response.ok ? response.json() : Promise.reject(new Error((await response.json()).detail || "Could not load traces")))
      .then((data) => setRuns(data.items || []))
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => runs.filter((run) => (!status || run.status === status) && (!query || `${run.name} ${run.trace_id}`.toLowerCase().includes(query.toLowerCase()))), [runs, query, status]);
  if (loading) return <LoadingState>Loading trace explorer…</LoadingState>;
  if (error) return <ErrorState title="Traces unavailable" message={error} />;

  return <>
    <PageHeader eyebrow="Trace explorer" title="Traces" description="Search captured agent runs, inspect their relationships, and move from a trace to its evidence timeline." />
    <section className="panel trace-explorer-panel">
      <div className="panel-header"><div><h2>Captured traces</h2><p className="card-subtitle">{filtered.length} of {runs.length} traces shown</p></div><span className="status-badge status-neutral"><SlidersHorizontal size={12} /> Project scope</span></div>
      <div className="filters"><div className="search-field"><Search size={14} /><input className="input" placeholder="Search trace names or IDs" value={query} onChange={(event) => setQuery(event.target.value)} /></div><select className="select" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option><option value="succeeded">Succeeded</option><option value="failed">Failed</option><option value="running">Running</option><option value="cancelled">Cancelled</option></select></div>
      {filtered.length === 0 ? <EmptyState title={runs.length ? "No matching traces" : "No traces captured yet"}>{runs.length ? "Try a different search or status filter." : "Connect an instrumented workflow and run it once to create the first trace."}</EmptyState> : <div className="table-wrap"><table className="data-table trace-table"><thead><tr><th>Trace</th><th>Status</th><th>Duration</th><th>Events</th><th>Started</th><th /></tr></thead><tbody>{filtered.map((run) => <tr key={run.trace_id}><td><Link href={`/runs/${encodeURIComponent(run.trace_id)}`}><span className="trace-name">{run.name}</span><span className="trace-id">{run.trace_id}</span></Link></td><td><StatusBadge status={run.status} /></td><td>{formatDuration(run.duration_ms)}</td><td>{run.event_count}</td><td>{formatDate(run.started_at)}</td><td><Link href={`/runs/${encodeURIComponent(run.trace_id)}`} className="table-arrow" aria-label={`Open ${run.name}`}>›</Link></td></tr>)}</tbody></table></div>}
    </section>
  </>;
}
