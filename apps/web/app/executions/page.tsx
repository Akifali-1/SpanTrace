"use client";

import Link from "next/link";
import { Play, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from "../components/ui";

type Execution = { id: string; analysis_id: string; status: string; trace_id: string; entry_file_path: string; entry_symbol: string; failure_category?: string; created_at: string; started_at?: string; completed_at?: string };
const proxy = (path: string) => `/api/proxy/${path}`;
const formatDate = (value?: string) => value ? new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
const terminal = new Set(["succeeded", "failed", "timed_out", "cancelled", "infrastructure_error"]);

export default function ExecutionsPage() {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    const response = await fetch(proxy("v1/executions?limit=200"), { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not load executions");
    setExecutions(data.items || []);
  }

  useEffect(() => { load().catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false)); }, []);
  const visible = useMemo(() => executions.filter((execution) => !filter || execution.status === filter), [executions, filter]);
  const active = executions.filter((execution) => !terminal.has(execution.status)).length;
  if (loading) return <LoadingState>Loading controlled executions…</LoadingState>;
  if (error) return <ErrorState title="Executions unavailable" message={error} action={<Link href="/repositories" className="button button-secondary">Open repository map</Link>} />;

  return <>
    <PageHeader eyebrow="Controlled workflow runs" title="Executions" description="Launches from an analyzed repository are supervised by the existing worker coordinator and remain linked to their resulting trace." actions={<Link href="/repositories" className="button button-primary"><Play size={14} /> Run from repository</Link>} />
    <section className="panel">
      <div className="panel-header"><div><h2>Execution history</h2><p className="card-subtitle">{active ? `${active} active` : "No active workers"} · {visible.length} shown</p></div><button type="button" className="icon-button" onClick={() => load().catch((reason: Error) => setError(reason.message))} aria-label="Refresh executions"><RefreshCw size={14} /></button></div>
      <div className="filters"><select className="select" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="">All statuses</option><option value="queued">Queued</option><option value="running">Running</option><option value="succeeded">Succeeded</option><option value="failed">Failed</option><option value="timed_out">Timed out</option><option value="cancelled">Cancelled</option></select></div>
      {visible.length === 0 ? <EmptyState title={executions.length ? "No executions in this filter" : "No controlled executions yet"}>{executions.length ? "Choose another status to see more worker records." : "Save a valid instrumentation configuration from a repository analysis before launching a workflow."}</EmptyState> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Workflow entry</th><th>Status</th><th>Trace</th><th>Created</th><th>Failure</th><th /></tr></thead><tbody>{visible.map((execution) => <tr key={execution.id}><td><Link href={`/executions/${encodeURIComponent(execution.id)}`}><span className="trace-name">{execution.entry_symbol}</span><span className="trace-id">{execution.entry_file_path}</span></Link></td><td><StatusBadge status={execution.status} /></td><td>{execution.trace_id.slice(0, 12)}…</td><td>{formatDate(execution.created_at)}</td><td>{execution.failure_category || "—"}</td><td><Link href={`/executions/${encodeURIComponent(execution.id)}`} className="table-arrow" aria-label={`Open execution ${execution.entry_symbol}`}>›</Link></td></tr>)}</tbody></table></div>}
    </section>
  </>;
}
