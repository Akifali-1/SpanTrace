"use client";

import Link from "next/link";
import { Bug, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from "../components/ui";

type Investigation = {
  id: string;
  name: string;
  status: string;
  failure_category: string;
  failure_summary: string;
  original: { execution_id?: string; trace_id: string };
  source: { revision?: string; analysis_id?: string };
  root_causes: { explanation: string; confidence: string }[];
  progress: Record<string, boolean>;
  created_at: string;
};

const proxy = (path: string) => `/api/proxy/${path}`;

export default function InvestigationsPage() {
  const [items, setItems] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(proxy("v1/investigations"), { cache: "no-store" })
      .then(async (response) => response.ok ? response.json() : Promise.reject(new Error((await response.json()).detail || "Could not load investigations")))
      .then((data) => setItems(data.items || []))
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState>Loading investigations…</LoadingState>;
  if (error) return <ErrorState title="Investigations unavailable" message={error} />;

  return <>
    <PageHeader eyebrow="Failure → reproduction → verified fix" title="Investigations" description="Follow persisted failure evidence through reproduction, regression testing, isolated patch review, and controlled verification." />
    <section className="panel">
      <div className="panel-header"><div><h2>Debugging workspace</h2><p className="card-subtitle">{items.length} project-scoped investigations</p></div><StatusBadge status={items.length ? "running" : "unknown"} label={items.length ? "Evidence-backed" : "No investigations"} /></div>
      {items.length === 0 ? <EmptyState title="No investigations yet" icon={<Bug size={17} />}><span>Open a failed execution or trace and start an investigation from its evidence.</span></EmptyState> : <div className="evaluation-list">{items.map((item) => <Link href={`/investigations/${encodeURIComponent(item.id)}`} className="evaluation-row" key={item.id}><div className="evaluation-icon"><Bug size={16} /></div><div className="evaluation-copy"><h3>{item.name}</h3><div className="trace-id">Trace {item.original.trace_id}</div><p>{item.failure_summary || item.failure_category.replaceAll("_", " ")}</p><div className="incident-meta"><span>{item.root_causes.length} ranked candidates</span><span>{new Date(item.created_at).toLocaleString()}</span></div></div><StatusBadge status={item.status} /><ChevronRight size={17} /></Link>)}</div>}
    </section>
  </>;
}
