"use client";

import Link from "next/link";
import { AlertCircle, ArrowUpRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from "../components/ui";

type Incident = { title: string; summary: string; severity: string; inference: string; evidence: { event_id: string; fact: string }[] };
type Run = { trace_id: string; name: string; started_at: string; incidents?: Incident[] };
type IncidentRow = Incident & { trace_id: string; run_name: string; started_at: string };
const proxy = (path: string) => `/api/proxy/${path}`;

export default function IncidentsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(proxy("v1/runs?limit=200"), { cache: "no-store" })
      .then(async (response) => response.ok ? response.json() : Promise.reject(new Error((await response.json()).detail || "Could not load incidents")))
      .then((data) => setRuns(data.items || []))
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  const incidents = useMemo<IncidentRow[]>(() => runs.flatMap((run) => (run.incidents || []).map((incident) => ({ ...incident, trace_id: run.trace_id, run_name: run.name, started_at: run.started_at }))).filter((incident) => !filter || incident.severity === filter), [runs, filter]);
  if (loading) return <LoadingState>Loading incident signals…</LoadingState>;
  if (error) return <ErrorState title="Incidents unavailable" message={error} />;

  return <>
    <PageHeader eyebrow="Evidence-backed signals" title="Incidents" description="Prioritized findings generated from recorded trace evidence. Every incident links back to the responsible trace for investigation." />
    <section className="panel incident-page-panel">
       <div className="panel-header"><div><h2>Incident queue</h2><p className="card-subtitle">{incidents.length} findings across {runs.length} traces</p></div><StatusBadge status={incidents.length ? "critical" : "passed"} label={incidents.length ? "Needs attention" : "All clear"} /></div>
      <div className="filters"><select className="select" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="">All severities</option><option value="high">High severity</option><option value="medium">Medium severity</option><option value="low">Low severity</option><option value="unknown">Unknown</option></select></div>
       {incidents.length === 0 ? <EmptyState title={filter ? "No incidents match this filter" : "No incidents detected"} icon={<AlertCircle size={17} />}><span>{filter ? "No incidents match this filter" : "The detector has not found any issues in recorded traces."}</span></EmptyState> : <div className="incident-queue">{incidents.map((incident, index) => <article className="incident-queue-row" key={`${incident.trace_id}-${incident.title}-${index}`}><div className="incident-queue-icon"><AlertCircle size={15} /></div><div className="incident-queue-copy"><div className="incident-queue-heading"><h3>{incident.title}</h3><StatusBadge status={incident.severity} label={incident.severity} /></div><p>{incident.summary}</p><div className="incident-meta"><span>{incident.run_name}</span><span>{new Date(incident.started_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span><span>{incident.evidence.length} evidence items</span></div></div><Link href={`/runs/${encodeURIComponent(incident.trace_id)}`} className="button button-secondary incident-open">Open trace <ArrowUpRight size={13} /></Link></article>)}</div>}
    </section>
  </>;
}
