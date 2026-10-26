"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";

type Finding = {
  id: string;
  finding_id: string;
  kind: string;
  name: string;
  symbol_type?: string;
  file_path: string;
  start_line: number;
  end_line: number;
  symbol_name?: string;
  framework?: string;
  detection_method: string;
  evidence_summary: string;
  confidence: string;
  instrumentation_status: string;
};
type Relationship = {
  id: string;
  source_finding_id: string;
  target_finding_id?: string;
  target_name?: string;
  type: string;
  confidence: string;
  detection_method: string;
  evidence_summary: string;
  file_path: string;
  start_line: number;
};
type Analysis = {
  id: string;
  name: string;
  source_kind: string;
  source_url?: string;
  branch?: string;
  commit_sha?: string;
  source_revision: string;
  archive_fingerprint: string;
  status: string;
  analysis_version: number;
  summary: {
    files_analyzed?: number;
    files_skipped?: number;
    language_counts?: Record<string, number>;
    manifest_files?: string[];
    frameworks?: { name: string; evidence?: string[] }[];
    entry_points?: { finding_id: string; name: string; file_path: string; start_line: number; confidence: string; reason: string }[];
    environment_variable_names?: string[];
    parse_errors?: string[];
    coverage?: { Python?: string; other_languages?: string };
  };
  findings: Finding[];
  relationships: Relationship[];
  limitations: string[];
  configuration?: { id: string; version: number; stale: boolean; valid: boolean; config: Record<string, unknown> } | null;
  error_message?: string;
};
type Evidence = { path: string; lines: { line: number; text: string }[] };

const proxy = (path: string) => `/api/proxy/${path}`;
const confidenceLabel: Record<string, string> = {
  confirmed_syntax: "Confirmed from syntax/configuration",
  strong_candidate: "Strong candidate",
  possible: "Possible",
  unknown: "Unknown",
};
const kindLabel: Record<string, string> = {
  workflow_entry: "Entry point",
  workflow_graph: "Workflow graph",
  agent: "Agent",
  tool: "Tool",
  model_call: "Model call",
  external_service: "External boundary",
  framework: "Framework",
  instrumentation: "Instrumentation",
};

function badgeConfidence(value: string) {
  return value === "confirmed_syntax" ? "succeeded" : value === "strong_candidate" || value === "possible" ? "running" : "unknown";
}

export default function RepositoryDetail({ params }: { params: Promise<{ analysisId: string }> }) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [filterKind, setFilterKind] = useState("");
  const [filterConfidence, setFilterConfidence] = useState("");
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [entryIds, setEntryIds] = useState<string[]>([]);
  const [componentIds, setComponentIds] = useState<string[]>([]);
  const [adapterIds, setAdapterIds] = useState<string[]>(["opentelemetry"]);
  const [capturePayloads, setCapturePayloads] = useState(false);
  const [redactSecrets, setRedactSecrets] = useState(true);
  const [configMessage, setConfigMessage] = useState("");
  const analysisId = decodeURIComponent(use(params).analysisId);

  async function load() {
    const response = await fetch(proxy(`v1/repositories/${encodeURIComponent(analysisId)}`), { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Repository analysis unavailable");
    setAnalysis(data);
    const entries = data.findings.filter((finding: Finding) => finding.kind === "workflow_entry").map((finding: Finding) => finding.finding_id);
    const components = data.findings.filter((finding: Finding) => !["workflow_entry", "framework", "instrumentation"].includes(finding.kind)).map((finding: Finding) => finding.finding_id);
    setEntryIds(entries);
    setComponentIds(components);
    const saved = data.configuration?.config as { workflow_entry_points?: { finding_id: string }[]; components?: { finding_id: string }[]; adapters?: { id: string }[]; instrumentation?: { capture_payloads?: boolean; redact_secrets?: boolean } } | undefined;
    if (saved) {
      setEntryIds((saved.workflow_entry_points || []).map((item) => item.finding_id));
      setComponentIds((saved.components || []).map((item) => item.finding_id));
      setAdapterIds((saved.adapters || []).map((item) => item.id));
      setCapturePayloads(Boolean(saved.instrumentation?.capture_payloads));
      setRedactSecrets(saved.instrumentation?.redact_secrets !== false);
    }
  }

  useEffect(() => {
    load().catch((reason: Error) => setError(reason.message));
  }, [analysisId]);

  const visibleFindings = useMemo(() => (analysis?.findings || []).filter((finding) => (!filterKind || finding.kind === filterKind) && (!filterConfidence || finding.confidence === filterConfidence)), [analysis, filterKind, filterConfidence]);
  const selected = analysis?.findings.find((finding) => finding.finding_id === selectedId) || visibleFindings[0];
  const kindOptions = Array.from(new Set((analysis?.findings || []).map((finding) => finding.kind))).sort();

  useEffect(() => {
    if (selected && selected.finding_id !== selectedId) setSelectedId(selected.finding_id);
  }, [selected, selectedId]);

  useEffect(() => {
    if (!selected || !analysis) return;
    fetch(proxy(`v1/repositories/${encodeURIComponent(analysis.id)}/source?path=${encodeURIComponent(selected.file_path)}&start_line=${selected.start_line}&end_line=${selected.end_line}`))
      .then(async (response) => response.ok ? response.json() : null)
      .then(setEvidence)
      .catch(() => setEvidence(null));
  }, [analysis, selected]);

  async function reanalyze() {
    setBusy("reanalyze");
    setError("");
    try {
      const response = await fetch(proxy(`v1/repositories/${encodeURIComponent(analysisId)}/reanalyze`), { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Re-analysis failed");
      setAnalysis(data.analysis);
      setConfigMessage("Analysis refreshed from the stored source revision. Review configuration selections again.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Re-analysis failed");
    } finally {
      setBusy("");
    }
  }

  async function saveConfig() {
    setBusy("config");
    setConfigMessage("");
    try {
      const response = await fetch(proxy(`v1/repositories/${encodeURIComponent(analysisId)}/config`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ schema_version: "1.0", workflow_entry_point_ids: entryIds, component_ids: componentIds, adapter_ids: adapterIds, capture_payloads: capturePayloads, redact_secrets: redactSecrets, excluded_paths: [], notes: "Reviewed in SpanTrace repository map." }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Configuration validation failed");
      setAnalysis((current) => current ? { ...current, configuration: data.configuration } : current);
      setConfigMessage(`Validated and saved configuration v${data.configuration.version}.`);
    } catch (reason) {
      setConfigMessage(reason instanceof Error ? reason.message : "Configuration validation failed");
    } finally {
      setBusy("");
    }
  }

  async function exportConfig() {
    const response = await fetch(proxy(`v1/repositories/${encodeURIComponent(analysisId)}/config/export`));
    if (!response.ok) return setConfigMessage((await response.json()).detail || "Save a configuration before exporting.");
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "spantrace-instrumentation.json";
    link.click();
    URL.revokeObjectURL(link.href);
  }

  function toggle(setter: (value: string[]) => void, values: string[], value: string) {
    setter(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  }

  if (error && !analysis) return <div className="error"><strong>Could not load repository analysis</strong>{error}<p><Link href="/repositories">Back to repositories</Link></p></div>;
  if (!analysis) return <div className="empty">Loading repository intelligence…</div>;

  return <>
    <Link href="/repositories" className="back">← Back to repositories</Link>
    <div className="detail-header">
      <div><div className="eyebrow">Source-discovered architecture</div><h1>{analysis.name}</h1><div className="detail-meta"><span className={`badge badge-${analysis.status === "analysis_complete" ? "succeeded" : analysis.status === "partially_analyzed" ? "running" : "unknown"}`}>{analysis.status.replaceAll("_", " ")}</span><span>{analysis.summary.files_analyzed || 0} files</span><span>v{analysis.analysis_version}</span><span className="mono">{analysis.commit_sha || analysis.archive_fingerprint.slice(0, 16)}</span></div></div>
      <div className="hero-actions"><button className="button button-secondary" onClick={reanalyze} disabled={busy !== ""}>{busy === "reanalyze" ? "Re-analyzing…" : "Re-analyze source"}</button></div>
    </div>
    {error && <div className="error-banner"><strong>Action needs attention</strong><span>{error}</span></div>}

    <div className="grid-4 repository-stats"><div className="stat-card"><div className="stat-label">Components</div><div className="stat-value">{analysis.findings.length}</div></div><div className="stat-card"><div className="stat-label">Relationships</div><div className="stat-value">{analysis.relationships.length}</div></div><div className="stat-card"><div className="stat-label">Entry points</div><div className="stat-value">{(analysis.summary.entry_points || []).length}</div></div><div className="stat-card"><div className="stat-label">Frameworks</div><div className="stat-value">{(analysis.summary.frameworks || []).length}</div></div></div>

    <section className="panel architecture-panel">
      <div className="panel-header"><div><h2>Candidate architecture map</h2><div className="cell">Static source relationships only · runtime traces remain a separate view</div></div><span className="badge badge-unknown">{visibleFindings.length} visible</span></div>
      <div className="filters"><select className="select" value={filterKind} onChange={(event) => setFilterKind(event.target.value)}><option value="">All component types</option>{kindOptions.map((kind) => <option value={kind} key={kind}>{kindLabel[kind] || kind}</option>)}</select><select className="select" value={filterConfidence} onChange={(event) => setFilterConfidence(event.target.value)}><option value="">All certainty levels</option><option value="confirmed_syntax">Confirmed from syntax/configuration</option><option value="strong_candidate">Strong candidate</option><option value="possible">Possible</option><option value="unknown">Unknown</option></select></div>
      <div className="architecture-layout">
        <div className="architecture-canvas">
          <div className="architecture-columns"><div><div className="map-column-label">Entry points</div>{visibleFindings.filter((finding) => finding.kind === "workflow_entry").map((finding) => <MapNode finding={finding} selected={selected?.finding_id === finding.finding_id} onClick={() => setSelectedId(finding.finding_id)} key={finding.finding_id} />)}</div><div><div className="map-column-label">Agents & workflow</div>{visibleFindings.filter((finding) => ["agent", "workflow_graph"].includes(finding.kind)).map((finding) => <MapNode finding={finding} selected={selected?.finding_id === finding.finding_id} onClick={() => setSelectedId(finding.finding_id)} key={finding.finding_id} />)}</div><div><div className="map-column-label">Tools, models & boundaries</div>{visibleFindings.filter((finding) => ["tool", "model_call", "external_service"].includes(finding.kind)).map((finding) => <MapNode finding={finding} selected={selected?.finding_id === finding.finding_id} onClick={() => setSelectedId(finding.finding_id)} key={finding.finding_id} />)}</div></div>
          <div className="relationship-list"><div className="map-column-label">Supported relationships</div>{analysis.relationships.length === 0 ? <div className="cell">No source-supported relationship was resolved.</div> : analysis.relationships.map((relationship) => <div className="relationship-row" key={relationship.id}><span className="mono">{analysis.findings.find((finding) => finding.finding_id === relationship.source_finding_id)?.name || relationship.source_finding_id}</span><strong>{relationship.type.replaceAll("_", " ")}</strong><span className="mono">{analysis.findings.find((finding) => finding.finding_id === relationship.target_finding_id)?.name || relationship.target_name || "unresolved"}</span><span className={`badge badge-${badgeConfidence(relationship.confidence)}`}>{confidenceLabel[relationship.confidence] || relationship.confidence}</span></div>)}</div>
        </div>
        <FindingDetails finding={selected} evidence={evidence} />
      </div>
    </section>

    <section className="config-section">
      <div className="hero config-hero"><div><div className="eyebrow">Actionable next step</div><h2>Review instrumentation configuration</h2><p className="lede">Choose the workflow entry points and components SpanTrace should prepare for instrumentation. Nothing is written into the imported repository.</p></div><div className="hero-actions"><button className="button button-primary" onClick={saveConfig} disabled={busy !== ""}>{busy === "config" ? "Validating…" : "Validate & save"}</button>{analysis.configuration && <button className="button button-secondary" onClick={exportConfig}>Export JSON</button>}</div></div>
      {configMessage && <div className="notice">{configMessage}</div>}
      {analysis.configuration?.stale && <div className="warning-banner"><strong>Configuration is stale.</strong> A newer source analysis exists for this project. Review and save a configuration against the current revision.</div>}
      <div className="config-grid"><div className="panel config-card"><h3>Workflow entry points</h3>{analysis.findings.filter((finding) => finding.kind === "workflow_entry").map((finding) => <label className="check-row" key={finding.finding_id}><input type="checkbox" checked={entryIds.includes(finding.finding_id)} onChange={() => toggle(setEntryIds, entryIds, finding.finding_id)} /><span><strong>{finding.name}</strong><small>{finding.file_path}:{finding.start_line} · {confidenceLabel[finding.confidence]}</small></span></label>)}{analysis.findings.every((finding) => finding.kind !== "workflow_entry") && <div className="cell">No workflow entry point was proven. Leave empty and confirm one later.</div>}</div><div className="panel config-card"><h3>Components</h3>{analysis.findings.filter((finding) => !["workflow_entry", "framework", "instrumentation"].includes(finding.kind)).map((finding) => <label className="check-row" key={finding.finding_id}><input type="checkbox" checked={componentIds.includes(finding.finding_id)} onChange={() => toggle(setComponentIds, componentIds, finding.finding_id)} /><span><strong>{finding.name}</strong><small>{kindLabel[finding.kind] || finding.kind} · {finding.file_path}:{finding.start_line}</small></span></label>)}</div><div className="panel config-card"><h3>Adapters & policy</h3><label className="check-row"><input type="checkbox" checked={adapterIds.includes("opentelemetry")} onChange={() => toggle(setAdapterIds, adapterIds, "opentelemetry")} /><span><strong>OpenTelemetry spans</strong><small>Supported automatic adapter · tested in Task 2</small></span></label><label className="check-row"><input type="checkbox" checked={adapterIds.includes("callback")} onChange={() => toggle(setAdapterIds, adapterIds, "callback")} /><span><strong>Framework callback adapter</strong><small>Explicit lifecycle hooks · no monkey patching</small></span></label><label className="check-row"><input type="checkbox" checked={capturePayloads} onChange={(event) => setCapturePayloads(event.target.checked)} /><span><strong>Capture selected payloads</strong><small>Review content capture before enabling</small></span></label><label className="check-row"><input type="checkbox" checked={redactSecrets} onChange={(event) => setRedactSecrets(event.target.checked)} /><span><strong>Redact common secrets</strong><small>Recommended and enabled by default</small></span></label></div></div>
    </section>
    <section className="panel limitations-panel"><h2>Analysis boundaries</h2><div className="boundary-grid"><div><strong>Revision</strong><span className="mono">{analysis.source_revision}</span></div><div><strong>Languages</strong><span>{Object.entries(analysis.summary.language_counts || {}).map(([language, count]) => `${language} ${count}`).join(" · ") || "none"}</span></div><div><strong>Environment names</strong><span>{(analysis.summary.environment_variable_names || []).join(", ") || "none detected"}</span></div><div><strong>Coverage</strong><span>Python deep AST; other languages inventory only</span></div></div>{analysis.limitations.map((limitation) => <div className="limitation-row" key={limitation}>• {limitation}</div>)}</section>
  </>;
}

function MapNode({ finding, selected, onClick }: { finding: Finding; selected: boolean; onClick: () => void }) {
  return <button className={`map-node map-node-${finding.kind} ${selected ? "map-node-selected" : ""}`} onClick={onClick}><span className="map-node-kind">{kindLabel[finding.kind] || finding.kind}</span><strong>{finding.name}</strong><small>{finding.file_path}:{finding.start_line}</small></button>;
}

function FindingDetails({ finding, evidence }: { finding?: Finding; evidence: Evidence | null }) {
  if (!finding) return <aside className="finding-details"><div className="empty">Select a node to inspect its source evidence.</div></aside>;
  return <aside className="finding-details"><div className="eyebrow">Evidence detail</div><h3>{finding.name}</h3><div className="detail-pill-row"><span className="badge badge-unknown">{kindLabel[finding.kind] || finding.kind}</span><span className={`badge badge-${badgeConfidence(finding.confidence)}`}>{confidenceLabel[finding.confidence] || finding.confidence}</span></div><div className="side-row"><span className="side-label">Source</span><span className="mono">{finding.file_path}:{finding.start_line}–{finding.end_line}</span></div><div className="side-row"><span className="side-label">Detection</span><span>{finding.detection_method}</span></div><div className="side-row"><span className="side-label">Instrumentation</span><span>{finding.instrumentation_status.replaceAll("_", " ")}</span></div><p className="evidence-summary">{finding.evidence_summary}</p>{evidence && <div className="source-evidence"><div className="map-column-label">Redacted source evidence</div><pre>{evidence.lines.map((line) => `${String(line.line).padStart(4, " ")} │ ${line.text}`).join("\n")}</pre></div>}</aside>;
}
