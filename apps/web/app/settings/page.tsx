"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type Project = { id: string; name: string; created_at: string; keys: { id: string; name: string; prefix: string; created_at: string; revoked_at?: string }[] };
const proxy = (path: string) => `/api/proxy/${path}`;

export default function Settings() {
  const [project, setProject] = useState<Project | null>(null); const [error, setError] = useState(""); const [newKey, setNewKey] = useState(""); const [name, setName] = useState("local-development");
  async function load() { const response = await fetch(proxy("v1/project")); const data = await response.json(); if (!response.ok) setError(data.detail); else setProject(data); }
  useEffect(() => { load(); }, []);
  async function createKey() { const response = await fetch(proxy("v1/project/keys"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }); const data = await response.json(); if (!response.ok) return setError(data.detail); setNewKey(data.api_key); await load(); }
  async function revoke(id: string) { await fetch(proxy(`v1/project/keys/${id}`), { method: "DELETE" }); await load(); }
  if (error) return <div className="error"><strong>Settings unavailable</strong>{error}<p><Link href="/">Back to runs</Link></p></div>;
  if (!project) return <div className="empty">Loading settings…</div>;
  return <><div className="hero"><div><div className="eyebrow">Workspace controls</div><h1>Project settings</h1><p className="lede">Manage the identity used by your SDK clients. Raw keys are shown only once by the API.</p></div></div><div className="settings-grid"><section className="panel settings-card"><h2>Project identity</h2><p>This project scopes every trace and protects runs from other projects.</p><div className="side-row"><span className="side-label">Name</span><strong>{project.name}</strong></div><div className="side-row"><span className="side-label">Project ID</span><span className="mono">{project.id}</span></div><div className="side-row"><span className="side-label">Created</span><span>{new Date(project.created_at).toLocaleDateString()}</span></div></section><section className="panel settings-card"><h2>API keys</h2><p>Use one key per environment. Never commit keys or paste them into frontend code.</p>{newKey && <div className="notice">Copy this key now; it will not be shown again.<br /><span className="mono">{newKey}</span></div>}{project.keys.map((key) => <div className="key-row" key={key.id}><div><div className="key-prefix">{key.prefix}••••••</div><div className="cell">{key.name} · {key.revoked_at ? "revoked" : "active"}</div></div>{!key.revoked_at && <button className="button button-danger" onClick={() => revoke(key.id)}>Revoke</button>}</div>)}<div style={{display: "flex", gap: 8, marginTop: 18}}><input className="input" value={name} onChange={(event) => setName(event.target.value)} /><button className="button button-primary" onClick={createKey}>Create key</button></div></section></div></>;
}
