"use client";

import Link from "next/link";
import { Bug, Copy } from "lucide-react";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import TraceGraph, { type TraceFlowEdge, type TraceFlowNode } from "../../components/trace-graph";

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

type TracePayload = {
  events: TraceFlowNode[];
  graph: { nodes: TraceFlowNode[]; edges: TraceFlowEdge[]; summary?: { node_count: number; edge_count: number; unresolved_parent_count: number; unresolved_handoff_count: number; uncertain_relationship_count: number } };
};

const proxy = (path: string) => `/api/proxy/${path}`;
const terminal = new Set(["succeeded", "failed", "timed_out", "cancelled", "infrastructure_error"]);

function badge(status: string) {
  return status === "succeeded" ? "succeeded" : status === "failed" || status === "timed_out" || status === "infrastructure_error" ? "failed" : status === "cancelled" ? "unknown" : "running";
}

function duration(execution: Execution) {
  if (!execution.started_at) return "—";
  const end = execution.completed_at ? Date.parse(execution.completed_at) : Date.now();
  const start = Date.parse(execution.started_at);
  if (Number.isNaN(start) || Number.isNaN(end)) return "—";
  const milliseconds = Math.max(0, end - start);
  return milliseconds < 1000 ? `${milliseconds}ms` : `${(milliseconds / 1000).toFixed(2)}s`;
}

function copyValue(value: string) {
  void navigator.clipboard?.writeText(value);
}

export default function ExecutionDetail({ params }: { params: Promise<{ executionId: string }> }) {
  const executionId = decodeURIComponent(use(params).executionId);
  const [execution, setExecution] = useState<Execution | null>(null);
  const [error, setError] = useState("");
  const [cancelMessage, setCancelMessage] = useState("");
  const [trace, setTrace] = useState<TracePayload | null>(null);
  const [traceError, setTraceError] = useState("");
  const [investigationBusy, setInvestigationBusy] = useState(false);
  const router = useRouter();

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
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "Execution unavailable");
      }
    };
    load();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [executionId]);

  useEffect(() => {
    if (!execution?.trace_available) return;
    let active = true;
    fetch(proxy(`v1/executions/${encodeURIComponent(executionId)}/trace`), { cache: "no-store" })
      .then(async (response) => response.ok ? response.json() : Promise.reject(new Error((await response.json()).detail || "Trace unavailable")))
      .then((data) => { if (active) setTrace(data); })
      .catch((reason: Error) => { if (active) setTraceError(reason.message); });
    return () => { active = false; };
  }, [execution?.trace_available, executionId]);

  async function cancel() {
    const response = await fetch(proxy(`v1/executions/${encodeURIComponent(executionId)}/cancel`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "Cancelled from dashboard" }) });
    const data = await response.json();
    if (!response.ok) return setCancelMessage(data.detail || "Cancellation failed");
    setExecution(data.execution);
    setCancelMessage("Cancellation requested; waiting for the worker to stop.");
  }

  async function startInvestigation() {
    setInvestigationBusy(true);
    setCancelMessage("");
    try {
      const response = await fetch(proxy(`v1/executions/${encodeURIComponent(executionId)}/investigations`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: `${execution?.entry_symbol || "Execution"} debugging investigation` }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not start investigation");
      router.push(`/investigations/${encodeURIComponent(data.investigation.id)}`);
    } catch (reason) { setCancelMessage(reason instanceof Error ? reason.message : "Could not start investigation"); }
    finally { setInvestigationBusy(false); }
  }

  if (error) return <div className="error"><strong>Could not load execution</strong>{error}<p><Link href="/repositories">Back to repositories</Link></p></div>;
  if (!execution) return <div className="empty">Loading controlled execution…</div>;

  const isActive = !terminal.has(execution.status);
  const flowNodes = trace?.graph.nodes.map((node) => ({ ...node, ...(trace.events.find((event) => event.event_id === node.event_id) || {}), event_id: node.event_id, label: node.label, event_type: node.event_type, status: node.status })) || [];
  const summary = trace?.graph.summary;

  return <div className="execution-detail-page">
    <Link href={`/repositories/${encodeURIComponent(execution.analysis_id)}`} className="back">← Back to repository map</Link>
      <div className="detail-header execution-header"><div><div className="eyebrow">Controlled worker execution</div><h1>{execution.entry_symbol}</h1><div className="detail-meta"><span className={`badge badge-${badge(execution.status)}`}>{execution.status.replaceAll("_", " ")}</span><span className="copyable-meta"><span className="mono">{execution.id}</span><button type="button" className="copy-button" aria-label="Copy execution ID" title="Copy execution ID" onClick={() => copyValue(execution.id)}><Copy size={12} /></button></span><span className="mono">{execution.trace_id}</span><span>{execution.entry_file_path}</span></div></div><div className="hero-actions"><button className="button button-primary" onClick={startInvestigation} disabled={investigationBusy}><Bug size={13} />{investigationBusy ? "Starting…" : "Start investigation"}</button>{isActive && <button className="button button-secondary" onClick={cancel}>Cancel worker</button>}{execution.trace_available && <Link className="button button-secondary" href={`/runs/${encodeURIComponent(execution.trace_id)}`}>Open full trace</Link>}</div></div>
     {cancelMessage && <div className="notice">{cancelMessage}</div>}

      <div className="execution-summary-strip" aria-label="Execution summary"><div><span>Status</span><strong>{execution.status.replaceAll("_", " ")}</strong></div><div><span>Worker duration</span><strong title="Time measured by the controlled worker">{duration(execution)}</strong></div><div><span>Operations</span><strong>{summary?.node_count ?? "—"}</strong></div><div><span>Errors</span><strong className={execution.failure_category ? "summary-danger" : ""}>{execution.failure_category ? 1 : 0}</strong></div><div><span>Exit code</span><strong className={execution.exit_code ? "summary-danger" : ""}>{execution.exit_code ?? "—"}</strong></div></div>

    {execution.trace_available && <section className="panel execution-flow-panel execution-workspace"><div className="workspace-heading"><div><div className="eyebrow">Execution workspace</div><h2>Observed workflow map</h2><p className="card-subtitle">Navigate captured parent spans and explicit handoffs. Details open only when you select an operation.</p></div><span className="workspace-evidence">{summary?.edge_count ?? 0} captured links</span></div>{trace ? <TraceGraph nodes={flowNodes} edges={trace.graph.edges} /> : traceError ? <div className="error-state"><strong>Trace flow unavailable</strong><p>{traceError}</p></div> : <div className="loading-state"><span className="loading-spinner" />Loading captured flow…</div>}</section>}
    {!execution.trace_available && <section className="panel flow-placeholder execution-no-trace"><strong>Trace not available yet</strong><p>The controlled worker has not returned captured telemetry. Execution status and sanitized output remain available below.</p></section>}

     <div className="execution-secondary-grid"><details className="panel collapsible-panel" open><summary><span><strong>Execution settings</strong><small>Source, resources, validated inputs</small></span><span className="accordion-label">Open details</span></summary><div className="collapsible-content"><div className="side-row"><span className="side-label">Source</span><span className="mono">{execution.entry_file_path}</span></div><div className="side-row"><span className="side-label">Function</span><span>{execution.entry_symbol}</span></div><div className="side-row"><span className="side-label">Resources</span><span>{execution.memory_mb}MB · {execution.cpu_limit} CPU · {execution.pids_limit} PIDs</span></div><div className="side-row"><span className="side-label">Failure</span><span>{execution.failure_category || "—"}</span></div><h3>Validated inputs</h3><pre className="payload">{JSON.stringify(execution.input, null, 2)}</pre></div></details><details className="panel collapsible-panel" open><summary><span><strong>Worker output</strong><small>Sanitized result and logs</small></span><span className="accordion-label">Open details</span></summary><div className="collapsible-content">{execution.failure_category && <div className="error-summary"><strong>{execution.failure_category}</strong><p>{execution.logs?.split("\n").filter(Boolean).at(-1) || "The worker reported a validation failure."}</p></div>}{execution.result && Object.keys(execution.result).length > 0 && <pre className="payload">{JSON.stringify(execution.result, null, 2)}</pre>}<div className="log-heading"><h3>Sanitized logs</h3><button type="button" className="copy-button" onClick={() => copyValue(execution.logs || "")} aria-label="Copy logs" title="Copy logs"><Copy size={13} /></button></div><pre className="payload worker-log">{(execution.logs || (isActive ? "Waiting for worker output…" : "No worker logs were returned.")).split("\n").map((line, index, lines) => <span className={index === lines.length - 1 && line ? "log-final-error" : undefined} key={`${index}-${line}`}>{line}{index < lines.length - 1 ? "\n" : ""}</span>)}</pre></div></details></div>
  </div>;
}
