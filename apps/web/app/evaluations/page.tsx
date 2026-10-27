"use client";

import Link from "next/link";
import { CheckCircle2, FlaskConical, Play, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from "../components/ui";

type Result = { id: string; passed: boolean; actual: Record<string, unknown>; created_at: string };
type Evaluation = { id: string; name: string; source_trace_id: string; created_at: string; latest_result?: Result | null };
const proxy = (path: string) => `/api/proxy/${path}`;

export default function EvaluationsPage() {
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    const response = await fetch(proxy("v1/regression-cases"), { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not load evaluations");
    setEvaluations(data.items || []);
  }

  useEffect(() => { load().catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false)); }, []);

  async function runEvaluation(id: string) {
    setBusy(id);
    setError("");
    try {
      const response = await fetch(proxy(`v1/regression-cases/${encodeURIComponent(id)}/run`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fixed: true }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Evaluation failed");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Evaluation failed"); }
    finally { setBusy(""); }
  }

  if (loading) return <LoadingState>Loading evaluations…</LoadingState>;
  if (error && !evaluations.length) return <ErrorState title="Evaluations unavailable" message={error} action={<Link href="/traces" className="button button-secondary">Open traces</Link>} />;

  return <>
    <PageHeader eyebrow="Verification" title="Evaluations" description="Turn evidence-backed incidents into deterministic regression checks and verify corrected workflow behavior." />
    {error && <div className="error-banner"><strong>Evaluation needs attention</strong><span>{error}</span></div>}
    <section className="panel">
      <div className="panel-header"><div><h2>Regression cases</h2><p className="card-subtitle">Created from recorded incident evidence</p></div><span className="status-badge status-neutral"><FlaskConical size={12} /> Deterministic checks</span></div>
      {evaluations.length === 0 ? <EmptyState title="No evaluations yet" icon={<FlaskConical size={17} />}><span>Open an incident trace and create a regression case from its evidence.</span></EmptyState> : <div className="evaluation-list">{evaluations.map((evaluation) => <article className="evaluation-row" key={evaluation.id}><div className="evaluation-icon">{evaluation.latest_result ? (evaluation.latest_result.passed ? <CheckCircle2 size={16} /> : <XCircle size={16} />) : <FlaskConical size={16} />}</div><div className="evaluation-copy"><h3>{evaluation.name}</h3><div className="trace-id">Source trace {evaluation.source_trace_id}</div><p>{evaluation.latest_result ? `Last run ${new Date(evaluation.latest_result.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}` : "Not run yet"}</p></div><StatusBadge status={evaluation.latest_result ? (evaluation.latest_result.passed ? "passed" : "failed") : "unknown"} label={evaluation.latest_result ? (evaluation.latest_result.passed ? "Passed" : "Failed") : "Not run"} /><Link href={`/runs/${encodeURIComponent(evaluation.source_trace_id)}`} className="button button-secondary">Source trace</Link><button type="button" className="button button-primary" onClick={() => runEvaluation(evaluation.id)} disabled={busy !== ""}><Play size={13} />{busy === evaluation.id ? "Running…" : "Run check"}</button></article>)}</div>}
    </section>
  </>;
}
