"use client";

import type { CSSProperties, PointerEvent as ReactPointerEvent, WheelEvent as ReactWheelEvent } from "react";
import { useRef, useState } from "react";

type Finding = {
  finding_id: string;
  kind: string;
  name: string;
  file_path: string;
  start_line: number;
};

type Relationship = {
  source_finding_id: string;
  target_finding_id?: string;
  target_name?: string;
  type: string;
  confidence: string;
};

const columns = [
  { label: "Entry points", kinds: ["workflow_entry"] },
  { label: "Agents & workflow", kinds: ["agent", "workflow_graph"] },
  { label: "Tools, models & boundaries", kinds: ["tool", "model_call", "external_service"] },
];
const NODE_WIDTH = 240;
const COLUMN_GAP = 80;
const GRAPH_WIDTH = 3 * NODE_WIDTH + 2 * COLUMN_GAP + 64;

export function normalizeIdentifier(value?: string) {
  return (value || "").trim().toLowerCase().replaceAll("-", "_");
}

function groupFor(finding: Finding) {
  const index = columns.findIndex((column) => column.kinds.includes(finding.kind));
  return index >= 0 ? index : 2;
}

function typeClass(kind: string) {
  return `map-node-${kind}`;
}

export default function RelationshipGraph({ findings, relationships, selectedId, onSelect, kindLabel }: {
  findings: Finding[];
  relationships: Relationship[];
  selectedId?: string;
  onSelect: (id: string) => void;
  kindLabel: Record<string, string>;
}) {
  const [zoom, setZoom] = useState(.82);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const groups = columns.map((column) => findings.filter((finding) => groupFor(finding) === columns.indexOf(column)));
  const rowHeight = 78;
  const graphHeight = Math.max(360, Math.max(...groups.map((group) => group.length), 1) * rowHeight + 48);
  const positions = new Map<string, { column: number; x: number; y: number }>();
  groups.forEach((group, column) => group.forEach((finding, index) => {
    const position = { column, x: 32 + column * (NODE_WIDTH + COLUMN_GAP), y: 24 + index * rowHeight };
    positions.set(finding.finding_id, position);
    positions.set(normalizeIdentifier(finding.finding_id), position);
    positions.set(normalizeIdentifier(finding.name), position);
  }));

  function resolve(value?: string) {
    if (!value) return undefined;
    return positions.get(value) || positions.get(normalizeIdentifier(value));
  }

  function handleWheel(event: ReactWheelEvent<HTMLDivElement>) {
    event.preventDefault();
    setZoom((value) => Math.max(.55, Math.min(1.2, value * (event.deltaY > 0 ? .92 : 1.08))));
  }

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    setPan({ x: drag.current.panX + event.clientX - drag.current.x, y: drag.current.panY + event.clientY - drag.current.y });
  }

  function stopDrag(event: ReactPointerEvent<HTMLDivElement>) {
    if (drag.current && event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    drag.current = null;
  }

  return <div className="relationship-graph" aria-label="Source-supported architecture graph">
    <div className="relationship-graph-labels">{columns.map((column) => <span key={column.label}>{column.label}</span>)}</div>
    <div className="relationship-graph-toolbar"><span>Drag to pan · scroll to zoom</span><button type="button" className="button button-secondary" onClick={() => { setZoom(.82); setPan({ x: 0, y: 0 }); }}>Fit</button></div>
    <div className="relationship-graph-canvas" style={{ "--graph-height": `${Math.max(560, Math.min(720, graphHeight * zoom + 60))}px` } as CSSProperties} onWheel={handleWheel} onPointerDown={handlePointerDown} onPointerMove={handlePointerMove} onPointerUp={stopDrag} onPointerCancel={stopDrag}>
      <div className="relationship-graph-stage" style={{ width: GRAPH_WIDTH, height: graphHeight, transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}>
        <svg className="relationship-graph-edges" width={GRAPH_WIDTH} height={graphHeight} viewBox={`0 0 ${GRAPH_WIDTH} ${graphHeight}`} aria-hidden="true">
          <defs><marker id="relationship-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 8 4 L 0 8 z" fill="currentColor" /></marker></defs>
          {relationships.map((relationship, index) => {
            const source = resolve(relationship.source_finding_id);
            const target = resolve(relationship.target_finding_id || relationship.target_name);
            if (!source || !target) return null;
            return <line key={`${relationship.source_finding_id}-${relationship.target_finding_id || relationship.target_name}-${index}`} x1={source.x + NODE_WIDTH} y1={source.y + 30} x2={target.x} y2={target.y + 30} className={`graph-edge${relationship.confidence === "unknown" ? " graph-edge-uncertain" : ""}`} markerEnd="url(#relationship-arrow)" />;
          })}
        </svg>
        {groups.map((group, column) => group.map((finding, index) => {
          const position = positions.get(finding.finding_id);
          if (!position) return null;
          const selected = selectedId === finding.finding_id;
          return <button key={finding.finding_id} className={`graph-graph-node map-node ${typeClass(finding.kind)}${selected ? " is-selected" : ""}`} style={{ left: position.x, top: position.y }} onClick={() => onSelect(finding.finding_id)} aria-pressed={selected} title={finding.name}><span className="map-node-kind">{kindLabel[finding.kind] || finding.kind}</span><strong>{finding.name}</strong><small>{finding.file_path}:{finding.start_line}</small></button>;
        }))}
      </div>
      {relationships.some((relationship) => relationship.target_finding_id && !resolve(relationship.target_finding_id)) && <div className="graph-unresolved">Some relationships target a finding outside the active filter.</div>}
    </div>
  </div>;
}
