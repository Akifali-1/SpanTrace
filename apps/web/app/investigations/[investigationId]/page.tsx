"use client";

import Link from "next/link";
import { CheckCircle2, CircleAlert, FileCode2, FlaskConical, GitPullRequest, Play, ShieldCheck } from "lucide-react";
import { use, useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from "../../components/ui";

type Candidate = { id: string; rank: number; category: string; explanation: string; confidence: string; evidence_kind: string; source: { revision?: string; file_path?: string; start_line?: number; end_line?: number }; trace_event_ids: string[]; supporting_evidence: unknown[]; contradictory_evidence: unknown[]; next_step: string };
type Attempt = { id: string; status: string; reproduction_execution_id?: string; reproduction_trace_id?: string; signature_match?: boolean; differences: string[]; result: Record<string, unknown> };
type RegressionTest = { id: string; status: string; file_path: string; code: string; description: string; expected: Record<string, unknown>; assumptions: string[]; original_result: Record<string, unknown>; patched_result: Record<string, unknown> };
type Patch = { id: string; status: string; decision?: string; diff: string; explanation: string; evidence: unknown[] };
type Verification = { id: string; status: string; patched_execution_id?: string; patched_trace_id?: string; original_test: Record<string, unknown>; patched_test: Record<string, unknown>; existing_tests: Record<string, unknown>; commands: unknown[]; report: Record<string, unknown>; error?: string };
type Investigation = { id: string; name: string; status: string; failure_category: string; failure_summary: string; original: { execution_id?: string; trace_id: string }; source: { analysis_id?: string; revision?: string; archive_fingerprint?: string }; evidence: Record<string, unknown>; missing_evidence: string[]; root_causes: Candidate[]; reproductions: Attempt[]; regression_tests: RegressionTest[]; patches: Patch[]; verifications: Verification[]; progress: Record<string, boolean> };

const proxy = (path: string) => `/api/proxy/${path}`;
const active = new Set(["reproducing", "verifying"]);

export default function InvestigationDetail({ params }: { params: Promise<{ investigationId: string }> }) {
  const investigationId = decodeURIComponent(use(params).investigationId);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    const response = await fetch(proxy(`v1/investigations/${encodeURIComponent(investigationId)}`), { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Investigation unavailable");
    setInvestigation(data);
  }

  useEffect(() => { load().catch((reason: Error) => setError(reason.message)); }, [investigationId]);
  useEffect(() => {
    if (!investigation || !active.has(investigation.status)) return;
    const timer = window.setTimeout(() => { load().catch((reason: Error) => setError(reason.message)); }, 1200);
    return () => window.clearTimeout(timer);
  }, [investigation]);

  async function action(path: string, body?: Record<string, unknown>) {
    setBusy(path);
    setNotice("");
    try {
      const response = await fetch(proxy(path), { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Action failed");
      setNotice("Action recorded. Results remain tied to the original source revision.");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Action failed"); }
    finally { setBusy(""); }
  }

  if (error && !investigation) return <ErrorState title="Investigation unavailable" message={error} action={<Link href="/investigations" className="button button-secondary">Back to investigations</Link>} />;
  if (!investigation) return <LoadingState>Loading investigation evidence…</LoadingState>;

  const test = investigation.regression_tests.at(-1);
  const patch = investigation.patches.at(-1);
  const verification = investigation.verifications.at(-1);
  const reproduction = investigation.reproductions.at(-1);
  const canGenerateTest = !test && investigation.progress.root_cause;
  const canPatch = test?.status === "validated" && !patch;
  const canVerify = Boolean(test?.status === "validated" && patch && !verification);

  return <>
    <Link href="/investigations" className="back">← Back to investigations</Link>
    <PageHeader eyebrow="Automated debugging investigation" title={investigation.name} description={investigation.failure_summary || "Evidence is incomplete; review the missing context before drawing a conclusion."} actions={<StatusBadge status={investigation.status} />} />
    {error && <div className="error-banner"><strong>Action needs attention</strong><span>{error}</span></div>}
    {notice && <div className="notice">{notice}</div>}
    <div className="grid-4"><Metric label="Failure" value={investigation.failure_category.replaceAll("_", " ")} /><Metric label="Trace" value={investigation.original.trace_id.slice(0, 12)} /><Metric label="Candidates" value={investigation.root_causes.length} /><Metric label="Revision" value={investigation.source.revision || "Unavailable"} /></div>

    <section className="panel"><div className="panel-header"><div><h2>Investigation overview</h2><p className="card-subtitle">Original evidence is preserved and every artifact is revision-bound.</p></div><div className="hero-actions"><Link href={`/runs/${encodeURIComponent(investigation.original.trace_id)}`} className="button button-secondary">Open original trace</Link>{investigation.original.execution_id && <Link href={`/executions/${encodeURIComponent(investigation.original.execution_id)}`} className="button button-secondary">Open execution</Link>}</div></div><div className="progress-strip">{["evidence", "root_cause", "reproduction", "regression_test", "patch", "verification"].map((step) => <div className={investigation.progress[step] ? "progress-step is-complete" : "progress-step"} key={step}><span>{investigation.progress[step] ? <CheckCircle2 size={14} /> : "·"}</span>{step.replaceAll("_", " ")}</div>)}</div>{investigation.missing_evidence.length > 0 && <div className="notice"><strong>Missing or unavailable evidence</strong><ul>{investigation.missing_evidence.map((item) => <li key={item}>{item}</li>)}</ul></div>}</section>

    <section className="panel"><div className="panel-header"><div><h2>Ranked root-cause candidates</h2><p className="card-subtitle">Observed facts, inferences, and hypotheses are labeled separately.</p></div></div>{investigation.root_causes.map((candidate) => <article className="candidate-card" key={candidate.id}><div className="candidate-rank">#{candidate.rank}</div><div className="candidate-copy"><div className="candidate-heading"><h3>{candidate.explanation}</h3><StatusBadge status={candidate.confidence} label={`${candidate.evidence_kind} · ${candidate.confidence}`} /></div><p>{candidate.category.replaceAll("_", " ")} · next step: {candidate.next_step}</p>{candidate.source.file_path && <div className="source-ref"><FileCode2 size={14} /><span className="mono">{candidate.source.file_path}:{candidate.source.start_line}{candidate.source.end_line !== candidate.source.start_line ? `–${candidate.source.end_line}` : ""}</span><span>revision {candidate.source.revision}</span></div>}<details><summary>Evidence details</summary><pre className="payload">{JSON.stringify({ trace_event_ids: candidate.trace_event_ids, supporting: candidate.supporting_evidence, contradictory: candidate.contradictory_evidence }, null, 2)}</pre></details></div></article>)}</section>

    <div className="run-support-grid"><section className="panel"><div className="panel-header"><div><h2>Reproduction</h2><p className="card-subtitle">Same source revision and sanitized inputs through the controlled worker.</p></div>{!reproduction && <button className="button button-primary" onClick={() => action(`v1/investigations/${investigation.id}/reproduction`)} disabled={busy !== "" || !investigation.original.execution_id}><Play size={13} />{busy.includes("reproduction") ? "Starting…" : "Reproduce failure"}</button>}</div>{!reproduction ? <EmptyState title="No reproduction attempt yet"><span>{investigation.original.execution_id ? "Start a controlled reproduction to compare the failure signature." : "This trace has no linked controlled execution; reproduction is blocked until inputs and source are available."}</span></EmptyState> : <div className="detail-stack"><StatusBadge status={reproduction.status} /><div className="side-row"><span className="side-label">Signature match</span><span>{reproduction.signature_match == null ? "Not comparable" : reproduction.signature_match ? "Yes — reproduced" : "No"}</span></div>{reproduction.reproduction_trace_id && <Link href={`/runs/${encodeURIComponent(reproduction.reproduction_trace_id)}`} className="text-link">Open reproduction trace</Link>}{reproduction.differences.length > 0 && <pre className="payload">{JSON.stringify(reproduction.differences, null, 2)}</pre>}</div>}</section>

      <section className="panel"><div className="panel-header"><div><h2>Regression test</h2><p className="card-subtitle">The original-code result must fail for the intended reason before a patch is reviewable.</p></div>{canGenerateTest && <button className="button button-primary" onClick={() => action(`v1/investigations/${investigation.id}/regression-test`)} disabled={busy !== ""}><FlaskConical size={13} />Generate and validate</button>}</div>{!test ? <EmptyState title="No generated test yet"><span>Generate a deterministic test from the trace and source evidence.</span></EmptyState> : <div className="detail-stack"><StatusBadge status={test.status} /><strong>{test.description}</strong><div className="source-ref"><FileCode2 size={14} /><span className="mono">{test.file_path}</span></div><div className="result-grid"><Result label="Original source" result={test.original_result} /><Result label="Patched source" result={test.patched_result} /></div><details open><summary>Generated test code</summary><pre className="code-block">{test.code}</pre></details>{test.assumptions.length > 0 && <p className="cell">Assumptions: {test.assumptions.join(" ")}</p>}</div>}</section></div>

    <section className="panel"><div className="panel-header"><div><h2>Proposed isolated fix</h2><p className="card-subtitle">Review the diff before verification. Nothing is applied to the original repository.</p></div>{canPatch && <button className="button button-primary" onClick={() => action(`v1/investigations/${investigation.id}/patch`)} disabled={busy !== ""}><GitPullRequest size={13} />Generate patch</button>}</div>{!patch ? <EmptyState title="No proposed patch yet"><span>Validate the regression test first; supported deterministic source patterns can then produce a minimal diff.</span></EmptyState> : <div className="detail-stack"><div className="side-row"><StatusBadge status={patch.status} /><span>{patch.explanation}</span></div><pre className="code-block diff-block">{patch.diff}</pre>{patch.status === "pending_review" && <div className="hero-actions"><button className="button button-primary" onClick={() => action(`v1/investigations/${investigation.id}/patches/${patch.id}/decision`, { decision: "approved" })} disabled={busy !== ""}>Approve for isolated verification</button><button className="button button-secondary" onClick={() => action(`v1/investigations/${investigation.id}/patches/${patch.id}/decision`, { decision: "rejected" })} disabled={busy !== ""}>Reject patch</button></div>}<p className="cell">Approval records human review only. The original working tree is never modified by this workflow.</p></div>}</section>

    <section className="panel"><div className="panel-header"><div><h2>Verification report</h2><p className="card-subtitle">Regression test, existing tests, and controlled rerun evidence are all required for verified.</p></div>{canVerify && <button className="button button-primary" onClick={() => action(`v1/investigations/${investigation.id}/verify`, { run_controlled_rerun: true })} disabled={busy !== ""}><ShieldCheck size={13} />Run verification</button>}</div>{!verification ? <EmptyState title="Verification not started"><span>Review the isolated diff, then run the complete verification sequence.</span></EmptyState> : <div className="detail-stack"><StatusBadge status={verification.status} /><div className="result-grid"><Result label="Original regression" result={verification.original_test} /><Result label="Patched regression" result={verification.patched_test} /><Result label="Existing tests" result={verification.existing_tests} /></div>{verification.patched_trace_id && <Link href={`/runs/${encodeURIComponent(verification.patched_trace_id)}`} className="text-link">Open patched controlled trace</Link>}{verification.error && <div className="error-banner"><CircleAlert size={14} /><span>{verification.error}</span></div>}<details><summary>Persisted verification report</summary><pre className="payload">{JSON.stringify({ report: verification.report, commands: verification.commands }, null, 2)}</pre></details></div>}</section>
  </>;
}

function Metric({ label, value }: { label: string; value: string | number }) { return <div className="metric-card metric-blue"><span className="metric-label">{label}</span><strong className="metric-value">{value}</strong></div>; }
function Result({ label, result }: { label: string; result: Record<string, unknown> }) { const status = typeof result.status === "string" ? result.status : "unknown"; return <div className="result-card"><span>{label}</span><StatusBadge status={status} /><small>{typeof result.exit_code === "number" ? `exit ${result.exit_code}` : "Evidence persisted"}</small></div>; }
