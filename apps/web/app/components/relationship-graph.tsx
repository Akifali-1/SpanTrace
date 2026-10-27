import type { CSSProperties } from "react";

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

function groupFor(finding: Finding) {
  const index = columns.findIndex((column) => column.kinds.includes(finding.kind));
  return index >= 0 ? index : 2;
}

export default function RelationshipGraph({
  findings,
  relationships,
  selectedId,
  onSelect,
  kindLabel,
}: {
  findings: Finding[];
  relationships: Relationship[];
  selectedId?: string;
  onSelect: (id: string) => void;
  kindLabel: Record<string, string>;
}) {
  const groups = columns.map((column, columnIndex) => findings.filter((finding) => groupFor(finding) === columnIndex));
  const maxRows = Math.max(...groups.map((group) => group.length), 1);
  const rowHeight = 77;
  const graphHeight = Math.max(230, maxRows * rowHeight + 38);
  const positions = new Map<string, { column: number; y: number }>();
  groups.forEach((group, column) => group.forEach((finding, index) => positions.set(finding.finding_id, { column, y: 36 + index * rowHeight })));
  const centerX = [16.5, 50, 83.5];
  const byId = new Map(findings.map((finding) => [finding.finding_id, finding]));

  return (
    <div className="relationship-graph" aria-label="Source-supported architecture graph">
      <div className="relationship-graph-labels">{columns.map((column) => <span key={column.label}>{column.label}</span>)}</div>
      <div className="relationship-graph-canvas" style={{ "--graph-height": `${graphHeight}px` } as CSSProperties}>
        <svg className="relationship-graph-edges" viewBox={`0 0 100 ${graphHeight}`} preserveAspectRatio="none" aria-hidden="true">
          <defs><marker id="relationship-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 8 4 L 0 8 z" fill="currentColor" /></marker></defs>
          {relationships.map((relationship, index) => {
            const source = positions.get(relationship.source_finding_id);
            const target = relationship.target_finding_id ? positions.get(relationship.target_finding_id) : undefined;
            if (!source || !target) return null;
            return <line key={`${relationship.source_finding_id}-${relationship.target_finding_id}-${index}`} x1={centerX[source.column] + 13} y1={source.y} x2={centerX[target.column] - 13} y2={target.y} className={`graph-edge${relationship.confidence === "unknown" ? " graph-edge-uncertain" : ""}`} markerEnd="url(#relationship-arrow)" />;
          })}
        </svg>
        {groups.map((group, column) => group.map((finding, index) => {
          const y = 36 + index * rowHeight;
          const selected = selectedId === finding.finding_id;
          return <button key={finding.finding_id} className={`graph-graph-node map-node-${finding.kind}${selected ? " is-selected" : ""}`} style={{ left: `${column * 34 + 1}%`, top: `${y - 28}px` }} onClick={() => onSelect(finding.finding_id)} aria-pressed={selected}><span className="map-node-kind">{kindLabel[finding.kind] || finding.kind}</span><strong>{finding.name}</strong><small>{finding.file_path}:{finding.start_line}</small></button>;
        }))}
        {relationships.some((relationship) => relationship.target_finding_id && !byId.has(relationship.target_finding_id)) && <div className="graph-unresolved">Some relationships target a finding outside the active filter.</div>}
      </div>
    </div>
  );
}
