"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

type Execution = {
  id: string;
  analysis_id: string;
  configuration_id: string;
  source_revision: string;
  archive_fingerprint: string;
  workflow_entry_point_id: string;
  entry_file_path: string;
  entry_symbol: string;
  trace_id: string;
  status: string;
  input: Record<string, unknown>;
  result: Record<string, unknown>;
  logs: string;
  failure_category?: string;
  exit_code?: number;
  trace_available?: boolean;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  timeout_seconds: number;
  memory_mb: number;
  cpu_limit: string;
  pids_limit: number;
};

const proxy = (path: string) => `/api/proxy/${path}`;
const terminal = new Set(["succeeded", "failed", "timed_out", "cancelled", "infrastructure_error"]);
function badge(status: string) { return status === "succeeded" ? "succeeded" : status === "failed" || status === "timed_out" || status === "infrastructure_error" ? "failed" : status === "cancelled" ? "unknown" : "running"; }

export default function ExecutionDetail({ params }: { params: Promise<{ executionId: string }> }) {
  const executionId = decodeURIComponent(use(params).executionId);
  const [execution, setExecution] = useState<Execution | null>(null);
  const [error, setError] = useState("");
  const [cancelMessage, setCancelMessage] = useState("");

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        const response = await fetch(proxy(`v1/executions/${encodeURIComponent(executionId)}`), { cache: "no-store" });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Execution unavailable");
        if (active) {
          setExecution(data);
          if (!terminal.has(data.status)) timer = setTimeout(load, 1000);
        }
      } catch (reason) { if (active) setError(reason instanceof Error ? reason.message : "Execution unavailable"); }
    };
    load();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [executionId]);

  async function cancel() {
    const response = await fetch(proxy(`v1/executions/${encodeURIComponent(executionId)}/cancel`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "Cancelled from dashboard" }) });
    const data = await response.json();
    if (!response.ok) return setCancelMessage(data.detail || "Cancellation failed");
    setExecution(data.execution);
    setCancelMessage("Cancellation requested; waiting for the worker to stop.");
  }

  if (error) return <div className="error"><strong>Could not load execution</strong>{error}<p><Link href="/repositories">Back to repositories</Link></p></div>;
  if (!execution) return <div className="empty">Loading controlled execution…</div>;
  const isActive = !terminal.has(execution.status);
  return <>
    <Link href={`/repositories/${encodeURIComponent(execution.analysis_id)}`} className="back">← Back to repository map</Link>
    <div className="detail-header"><div><div className="eyebrow">Controlled worker execution</div><h1>{execution.entry_symbol}</h1><div className="detail-meta"><span className={`badge badge-${badge(execution.status)}`}>{execution.status.replaceAll("_", " ")}</span><span className="mono">{execution.trace_id}</span><span>{execution.entry_file_path}</span></div></div><div className="hero-actions">{isActive && <button className="button button-secondary" onClick={cancel}>Cancel worker</button>}{execution.trace_available && <Link className="button button-primary" href={`/runs/${encodeURIComponent(execution.trace_id)}`}>Open runtime trace</Link>}</div></div>
    {cancelMessage && <div className="notice">{cancelMessage}</div>}
    <div className="grid-4 repository-stats"><div className="stat-card"><div className="stat-label">Status</div><div className="stat-value" style={{ fontSize: 18 }}>{execution.status.replaceAll("_", " ")}</div></div><div className="stat-card"><div className="stat-label">Exit code</div><div className="stat-value">{execution.exit_code ?? "—"}</div></div><div className="stat-card"><div className="stat-label">Timeout</div><div className="stat-value">{execution.timeout_seconds}s</div></div><div className="stat-card"><div className="stat-label">Revision</div><div className="stat-value mono" style={{ fontSize: 12 }}>{execution.source_revision.slice(0, 16)}</div></div></div>
    <div className="detail-grid"><section className="panel side-card"><h2>Execution settings</h2><div className="side-row"><span className="side-label">Source</span><span className="mono">{execution.entry_file_path}</span></div><div className="side-row"><span className="side-label">Function</span><span>{execution.entry_symbol}</span></div><div className="side-row"><span className="side-label">Resources</span><span>{execution.memory_mb}MB · {execution.cpu_limit} CPU · {execution.pids_limit} PIDs</span></div><div className="side-row"><span className="side-label">Failure</span><span>{execution.failure_category || "—"}</span></div><h3>Validated inputs</h3><pre className="payload">{JSON.stringify(execution.input, null, 2)}</pre></section><section className="panel side-card"><h2>Worker output</h2>{execution.result && Object.keys(execution.result).length > 0 && <pre className="payload">{JSON.stringify(execution.result, null, 2)}</pre>}<h3>Sanitized logs</h3><pre className="source-evidence"><code>{execution.logs || (isActive ? "Waiting for worker output…" : "No worker logs were returned.")}</code></pre></section></div>
  </>;
}
