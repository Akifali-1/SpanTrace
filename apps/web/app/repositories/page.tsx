"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

type Analysis = {
  id: string;
  name: string;
  source_kind: string;
  source_url?: string;
  branch?: string;
  commit_sha?: string;
  source_revision: string;
  status: string;
  analysis_version: number;
  summary: { files_analyzed?: number; finding_counts?: Record<string, number>; frameworks?: { name: string }[]; entry_points?: unknown[] };
  limitations: string[];
  created_at: string;
  analyzed_at?: string;
  error_message?: string;
};

const proxy = (path: string) => `/api/proxy/${path}`;

function statusClass(status: string) {
  if (status === "analysis_complete") return "succeeded";
  if (status === "analyzing" || status === "importing" || status === "source_available") return "running";
  return "unknown";
}

export default function Repositories() {
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const response = await fetch(proxy("v1/repositories"), { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not load repository analyses");
    setAnalyses(data.items);
  }

  useEffect(() => {
    load().catch((reason: Error) => setError(reason.message));
  }, []);

  async function importUrl(event: FormEvent) {
    event.preventDefault();
    setBusy("github");
    setError("");
    try {
      const response = await fetch(proxy("v1/repositories/import/url"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, ref: ref || null }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Repository import failed");
      setUrl("");
      setRef("");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Repository import failed");
    } finally {
      setBusy("");
    }
  }

  async function importZip(event: FormEvent) {
    event.preventDefault();
    if (!file) return setError("Choose a .zip archive first.");
    setBusy("zip");
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(proxy("v1/repositories/import/zip"), { method: "POST", body });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "ZIP import failed");
      setFile(null);
      const input = document.getElementById("repository-zip") as HTMLInputElement | null;
      if (input) input.value = "";
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "ZIP import failed");
    } finally {
      setBusy("");
    }
  }

  return <>
    <div className="hero">
      <div>
        <div className="eyebrow">Repository intelligence</div>
        <h1>See how your agent system is assembled.</h1>
        <p className="lede">Import a public GitHub repository or a ZIP archive. SpanTrace reads source evidence without executing the project, then builds a reviewable architecture and instrumentation plan.</p>
      </div>
    </div>

    {error && <div className="error-banner"><strong>Import needs attention</strong><span>{error}</span></div>}
    <div className="import-grid">
      <form className="panel import-card" onSubmit={importUrl}>
        <div className="eyebrow">Source A</div>
        <h2>Public GitHub repository</h2>
        <p>Read-only public import. Branch or tag is optional; the resolved commit is recorded when GitHub provides it.</p>
        <label className="field-label" htmlFor="github-url">Repository URL</label>
        <input id="github-url" className="input" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://github.com/owner/repository" required />
        <label className="field-label" htmlFor="github-ref">Branch or reference <span>optional</span></label>
        <input id="github-ref" className="input" value={ref} onChange={(event) => setRef(event.target.value)} placeholder="main" />
        <button className="button button-primary" disabled={busy !== ""}>{busy === "github" ? "Importing and analyzing…" : "Import GitHub repository"}</button>
        <div className="small-note">Private GitHub repositories are not claimed as supported until an authorized least-privilege integration is configured.</div>
      </form>
      <form className="panel import-card" onSubmit={importZip}>
        <div className="eyebrow">Source B</div>
        <h2>Upload a ZIP archive</h2>
        <p>Archives are bounded, checked for traversal and symlinks, and extracted into project-isolated storage. No scripts or dependencies run.</p>
        <label className="field-label" htmlFor="repository-zip">ZIP archive</label>
        <input id="repository-zip" className="input file-input" type="file" accept=".zip,application/zip" onChange={(event) => setFile(event.target.files?.[0] || null)} required />
        <button className="button button-primary" disabled={busy !== ""}>{busy === "zip" ? "Importing and analyzing…" : "Upload and analyze ZIP"}</button>
        <div className="small-note">Generated dependencies, build output, caches, virtual environments, and vendored directories are excluded by default.</div>
      </form>
    </div>

    <section className="panel repository-list-panel">
      <div className="panel-header"><h2>Imported repositories</h2><span className="cell">Static analyses only</span></div>
      {analyses.length === 0 ? <div className="empty"><strong>No repository analysis yet</strong>Import a source above to see candidate entry points, agents, tools, and evidence.</div> : analyses.map((analysis) => <Link href={`/repositories/${encodeURIComponent(analysis.id)}`} className="repository-row" key={analysis.id}>
        <div><div className="run-name">{analysis.name}</div><div className="run-id">{analysis.source_kind === "github" ? analysis.source_url : `ZIP · ${analysis.source_revision}`}</div></div>
        <span className={`badge badge-${statusClass(analysis.status)}`}>{analysis.status.replaceAll("_", " ")}</span>
        <div className="cell">{analysis.summary.files_analyzed || 0} files · {Object.values(analysis.summary.finding_counts || {}).reduce((sum, count) => sum + count, 0)} findings</div>
        <div className="cell hide-mobile">{(analysis.summary.frameworks || []).map((framework) => framework.name).join(", ") || "No framework marker"}</div>
        <div className="arrow">›</div>
      </Link>)}
    </section>
  </>;
}
