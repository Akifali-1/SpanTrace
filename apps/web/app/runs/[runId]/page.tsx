"use client";

import Link from "next/link";
import { Bug } from "lucide-react";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import TraceGraph, { type TraceFlowNode } from "../../components/trace-graph";

type Event = {
  event_id: string;
  event_type: string;
  kind: string;
  status: string;
  agent_name?: string;
  model_name?: string;
  tool_name?: string;
  parent_span_id?: string;
  span_id?: string;
  duration_ms?: number;
  occurred_at: string;
  input?: unknown;
  output?: unknown;
  tool_args?: unknown;
  tool_result?: unknown;
  handoff_to?: string;
  error_details?: string;
  integration?: string;
  framework?: string;
  relationship_confidence?: string;
};

type Incident = {
  title: string;
  summary: string;
  severity: string;
  evidence: { event_id: string; fact: string }[];
  inference: string;
  responsible_span_id?: string;
};

type Graph = {
  status: string;
  nodes: { event_id: string; span_id?: string; parent_span_id?: string; label: string; event_type: string; kind?: string; status: string; occurred_at?: string; relationship_confidence?: string; handoff_to?: string; integration?: string; framework?: string }[];
  edges: { from: string; to?: string | null; type: string; confidence: string; target?: string }[];
  summary: {
    node_count: number;
    edge_count: number;
    unresolved_parent_count: number;
    unresolved_handoff_count: number;
    uncertain_relationship_count: number;
  };
};

type Run = {
  trace_id: string;
  name: string;
  status: string;
  event_count: number;
  duration_ms?: number;
  events: Event[];
  incidents: Incident[];
  graph: Graph;
};

const proxy = (path: string) => `/api/proxy/${path}`;
const pretty = (value: unknown) => (value == null ? "" : JSON.stringify(value, null, 2));
function duration(ms?: number) { return ms == null ? "—" : `${ms}ms`; }

export default function RunDetail({ params }: { params: Promise<{ runId: string }> }) {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState("");
  const [caseId, setCaseId] = useState("");
  const [regression, setRegression] = useState("");
  const [investigationBusy, setInvestigationBusy] = useState(false);
  const router = useRouter();
  const traceId = decodeURIComponent(use(params).runId);

  useEffect(() => {
    fetch(proxy(`v1/runs/${encodeURIComponent(traceId)}`))
      .then(async (response) => response.ok ? response.json() : Promise.reject(new Error((await response.json()).detail || "Run unavailable")))
      .then(setRun)
      .catch((err) => setError(err.message));
  }, [traceId]);

  async function createCase() {
    const response = await fetch(proxy(`v1/runs/${encodeURIComponent(traceId)}/regression-case`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Travel approval invariant" }),
    });
    const data = await response.json();
    if (!response.ok) return setRegression(data.detail);
    setCaseId(data.id);
    setRegression("Regression case created. Run it below with the corrected implementation.");
  }

  async function runCase() {
    if (!caseId) return;
    const response = await fetch(proxy(`v1/regression-cases/${caseId}/run`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fixed: true }),
    });
    const data = await response.json();
    setRegression(data.passed ? "Passed: corrected booking waits for approval." : "Failed: approval invariant still violated.");
  }

  async function startInvestigation() {
    setInvestigationBusy(true);
    setRegression("");
    try {
      const response = await fetch(proxy(`v1/runs/${encodeURIComponent(traceId)}/investigations`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: `${run?.name || "Trace"} debugging investigation` }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not start investigation");
      router.push(`/investigations/${encodeURIComponent(data.investigation.id)}`);
    } catch (reason) { setRegression(reason instanceof Error ? reason.message : "Could not start investigation"); }
    finally { setInvestigationBusy(false); }
  }

  if (error) return <div className="error"><strong>Could not load trace</strong>{error}<p><Link href="/v1">Back to runs</Link></p></div>;
  if (!run) return <div className="empty">Loading trace…</div>;

  const flowNodes: TraceFlowNode[] = run.graph.nodes.map((node) => ({
    ...node,
    ...(run.events.find((event) => event.event_id === node.event_id) || {}),
    event_id: node.event_id,
    label: node.label,
    event_type: node.event_type,
    status: node.status,
  }));

  return <div className="run-detail-page">
    <Link href="/v1" className="back">← Back to runs</Link>
    <div className="detail-header">
      <div>
        <div className="eyebrow">Trace detail</div>
        <h1>{run.name}</h1>
        <div className="detail-meta"><span className={`badge badge-${run.status}`}>{run.status}</span><span>{run.event_count} events</span><span>{duration(run.duration_ms)}</span><span className="mono">{run.trace_id}</span></div>
      </div>
       <div className="hero-actions"><button className="button button-primary" onClick={startInvestigation} disabled={investigationBusy}><Bug size={13} />{investigationBusy ? "Starting…" : "Start investigation"}</button><button className="button button-secondary" onClick={() => window.open(proxy(`v1/runs/${encodeURIComponent(traceId)}/export`), "_blank")}>Export JSON</button></div>
    </div>

    <section className="panel graph-panel execution-workspace">
          <div className="panel-header" style={{ padding: "0 0 18px", marginBottom: 16 }}>
             <div><h2>Execution flow</h2><p className="card-subtitle">Observed parent spans and explicit handoffs</p></div>
             <span className={`badge badge-${run.graph.status === "observed" ? "succeeded" : "running"}`}>{run.graph.status.replace("_", " ")}</span>
          </div>
            <p className="flow-description">The flow is conservative: it connects only relationships captured in telemetry. Unknown relationships remain visible as incomplete evidence.</p>
            <div className="graph-summary"><span>{run.graph.summary.node_count} nodes</span><span>{run.graph.summary.edge_count} edges</span><span>{run.graph.summary.uncertain_relationship_count} uncertain</span><span>{run.graph.summary.unresolved_handoff_count} unresolved handoffs</span></div>
             <TraceGraph nodes={flowNodes} edges={run.graph.edges} />
           {run.graph.edges.some((edge) => edge.to == null) && <div className="notice">Some handoffs could not be linked to a target span. The timeline below is the chronological fallback.</div>}
    </section>
    <div className="run-support-grid">
      <div>
        <section className="panel timeline">
          <div className="panel-header" style={{ padding: "0 0 18px", marginBottom: 22 }}><h2>Execution timeline</h2><span className="cell">Actual captured events</span></div>
          {run.events.map((event) => <TimelineEvent event={event} key={event.event_id} />)}
        </section>
      </div>
      <aside>
        {run.incidents.map((incident, index) => <IncidentCard incident={incident} key={`${incident.title}-${index}`} />)}
        {run.incidents.length === 0 && <div className="panel side-card"><h3>No policy incidents</h3><p>The deterministic approval rule found no violation in this trace.</p></div>}
        <div className="panel side-card"><h3>Regression workflow</h3><p>Turn this evidence-backed incident into a deterministic case, then rerun the corrected demo implementation.</p><button className="button button-primary" onClick={createCase}>Create regression case</button>{caseId && <button className="button button-secondary" style={{ marginLeft: 8 }} onClick={runCase}>Run corrected case</button>}{regression && <div className="notice">{regression}</div>}</div>
        <div className="panel side-card"><h3>Trace identity</h3><div className="side-row"><span className="side-label">Trace ID</span><span className="mono">{run.trace_id.slice(0, 12)}…</span></div><div className="side-row"><span className="side-label">Events</span><span>{run.event_count}</span></div><div className="side-row"><span className="side-label">Integrations</span><span>{Array.from(new Set(run.events.map((event) => event.integration || "manual"))).join(", ")}</span></div></div>
      </aside>
    </div>
  </div>;
}


function TimelineEvent({ event }: { event: Event }) {
  const payload = event.tool_name ? { args: event.tool_args, result: event.tool_result } : { input: event.input, output: event.output };
  const hasPayload = Boolean(payload.input || payload.output || payload.args || payload.result);
  return <div className="timeline-item"><span className="timeline-dot" /><div className="timeline-top"><span className="timeline-name">{event.agent_name || event.event_type}{event.model_name ? ` · ${event.model_name}` : ""}{event.tool_name ? ` · ${event.tool_name}` : ""}</span><span className={`badge badge-${event.status}`}>{event.status}</span></div><div className="timeline-sub">{event.kind} · {duration(event.duration_ms)} · {new Date(event.occurred_at).toLocaleTimeString()} {event.parent_span_id ? ` · child of ${event.parent_span_id.slice(0, 8)}` : ""}{event.handoff_to ? ` · handoff → ${event.handoff_to}` : ""}{event.framework ? ` · ${event.framework}` : ""}</div>{event.relationship_confidence === "unknown" && <div className="cell">Relationship unavailable from source framework</div>}{event.error_details && <div className="payload" style={{ color: "var(--red)" }}>Error: {event.error_details}</div>}{hasPayload && <details><summary style={{ marginTop: 11, color: "var(--blue)", fontSize: 12, cursor: "pointer" }}>View selected payload</summary><pre className="payload">{pretty(payload)}</pre></details>}</div>;
}

function IncidentCard({ incident }: { incident: Incident }) {
  return <div className="incident-card"><div className="eyebrow" style={{ color: "var(--red)" }}>{incident.severity} severity · incident detected</div><h3>{incident.title}</h3><p>{incident.summary}</p>{incident.responsible_span_id && <p className="mono">Responsible span: {incident.responsible_span_id.slice(0, 12)}…</p>}<ul className="evidence">{incident.evidence.map((item) => <li key={item.event_id}><span className="mono">{item.event_id.slice(0, 10)}…</span> — {item.fact}</li>)}</ul><p style={{ marginTop: 13, marginBottom: 0 }}><strong>Inference:</strong> {incident.inference}</p></div>;
}
