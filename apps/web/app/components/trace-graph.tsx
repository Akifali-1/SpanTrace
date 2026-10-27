"use client";

import type { PointerEvent as ReactPointerEvent, WheelEvent as ReactWheelEvent } from "react";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Check, CircleAlert, Clock3, Crosshair, Minus, PanelRightClose, PanelRightOpen, Plus, RotateCcw, Search, Workflow, X } from "lucide-react";

export type TraceFlowNode = {
  event_id: string;
  node_id?: string;
  span_id?: string;
  parent_span_id?: string;
  label: string;
  event_type: string;
  kind?: string;
  status: string;
  occurred_at?: string;
  ended_at?: string;
  duration_ms?: number;
  agent_name?: string;
  model_name?: string;
  tool_name?: string;
  error_type?: string;
  error_details?: string;
  relationship_confidence?: string;
  integration?: string;
  framework?: string;
  metadata?: Record<string, unknown>;
};

export type TraceFlowEdge = {
  from: string;
  to?: string | null;
  type: string;
  confidence: string;
  target?: string;
};

type PositionedNode = TraceFlowNode & { x: number; y: number; level: number; failed: boolean };
type Point = { x: number; y: number };
type ResolvedEdge = { edge: TraceFlowEdge; index: number; from: PositionedNode; to: PositionedNode; loop: boolean };
type GraphLayout = {
  positioned: PositionedNode[];
  resolvedEdges: ResolvedEdge[];
  width: number;
  height: number;
  unresolvedCount: number;
};

const NODE_WIDTH = 200;
const NODE_HEIGHT = 56;
const COLUMN_GAP = 72;
const ROW_GAP = 26;
const MIN_ZOOM = 0.8;
const MAX_ZOOM = 2.2;

function isFailed(node: TraceFlowNode) {
  const status = node.status.toLowerCase();
  return ["failed", "error", "exception", "timed_out", "infrastructure_error"].includes(status)
    || Boolean(node.error_type || node.error_details)
    || node.event_type === "exception";
}

function statusTone(node: TraceFlowNode) {
  if (isFailed(node)) return "failed";
  const status = node.status.toLowerCase();
  if (["running", "queued", "starting", "cancel_requested"].includes(status)) return "running";
  if (["cancelled", "timed_out", "warning"].includes(status)) return "warning";
  if (["unknown", "incomplete"].includes(status)) return "neutral";
  return "success";
}

function displayName(node: TraceFlowNode) {
  return node.tool_name || node.agent_name || node.model_name || node.label || node.event_type.replaceAll("_", " ");
}

function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, Math.max(1, length - 1))}â€¦` : value;
}

function shortId(value?: string) {
  return value ? `${value.slice(0, 12)}â€¦` : "â€”";
}

function formatDuration(value?: number) {
  if (value == null) return "Unavailable";
  return value < 1000 ? `${value}ms` : `${(value / 1000).toFixed(2)}s`;
}

function formatTimestamp(value?: string) {
  if (!value) return "Unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unavailable" : date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function edgeKey(edge: TraceFlowEdge, index: number) {
  return `${edge.from}-${edge.to || edge.target || "unresolved"}-${edge.type}-${index}`;
}

function layoutNodes(nodes: TraceFlowNode[], edges: TraceFlowEdge[]): GraphLayout {
  const ordered = [...nodes].sort((a, b) => (a.occurred_at || "").localeCompare(b.occurred_at || "") || a.event_id.localeCompare(b.event_id));
  const ids = new Set(ordered.map((node) => node.event_id));
  const spanToEvent = new Map<string, string>();
  ordered.forEach((node) => { if (node.span_id && !spanToEvent.has(node.span_id)) spanToEvent.set(node.span_id, node.event_id); });
  const resolve = (value?: string | null) => value && (ids.has(value) ? value : spanToEvent.get(value));
  const orderedIndex = new Map(ordered.map((node, index) => [node.event_id, index]));
  const resolvedPairs = edges.flatMap((edge, index) => {
    const from = resolve(edge.from);
    const to = resolve(edge.to);
    return from && to && from !== to ? [{ edge, index, from, to }] : [];
  });
  const levels = new Map(ordered.map((node) => [node.event_id, 0]));

  // Rank observed forward relationships. Backward edges remain visible as retry/loop connectors.
  if (resolvedPairs.length) {
    for (let pass = 0; pass < ordered.length; pass += 1) {
      let changed = false;
      resolvedPairs.forEach(({ from, to }) => {
        if ((orderedIndex.get(from) || 0) >= (orderedIndex.get(to) || 0)) return;
        const next = (levels.get(from) || 0) + 1;
        if (next > (levels.get(to) || 0)) {
          levels.set(to, next);
          changed = true;
        }
      });
      if (!changed) break;
    }
  } else {
    // With no relationship evidence, use a chronological grid rather than inventing connectors.
    const rows = Math.min(5, Math.max(1, Math.ceil(Math.sqrt(ordered.length))));
    ordered.forEach((node, index) => levels.set(node.event_id, Math.floor(index / rows)));
  }

  const groups = new Map<number, TraceFlowNode[]>();
  ordered.forEach((node) => {
    const level = levels.get(node.event_id) || 0;
    const group = groups.get(level) || [];
    group.push(node);
    groups.set(level, group);
  });
  const maxLevel = Math.max(...groups.keys(), 0);
  const maxRows = Math.max(...[...groups.values()].map((group) => group.length), 1);
  const positioned = ordered.map((node) => {
    const level = levels.get(node.event_id) || 0;
    const row = groups.get(level)?.indexOf(node) || 0;
    return { ...node, level, x: 34 + level * (NODE_WIDTH + COLUMN_GAP), y: 38 + row * (NODE_HEIGHT + ROW_GAP), failed: isFailed(node) };
  });
  const positionedById = new Map(positioned.map((node) => [node.event_id, node]));
  const resolvedEdges = resolvedPairs.flatMap(({ edge, index, from, to }) => {
    const source = positionedById.get(from);
    const target = positionedById.get(to);
    return source && target ? [{ edge, index, from: source, to: target, loop: target.x <= source.x }] : [];
  });
  const width = Math.max(900, (maxLevel + 1) * (NODE_WIDTH + COLUMN_GAP) + 68);
  const height = Math.max(400, maxRows * (NODE_HEIGHT + ROW_GAP) + 76);
  return { positioned, resolvedEdges, width, height, unresolvedCount: edges.length - resolvedEdges.length };
}

function EdgePath({ relation, active, markerId }: { relation: ResolvedEdge; active: boolean; markerId: string }) {
  const { from, to, edge, loop } = relation;
  const startX = from.x + NODE_WIDTH;
  const startY = from.y + NODE_HEIGHT / 2;
  const endX = to.x;
  const endY = to.y + NODE_HEIGHT / 2;
  const failed = to.failed && edge.confidence !== "unknown";
  let path: string;
  if (loop) {
    const side = Math.max(startX, to.x + NODE_WIDTH) + 42;
    path = `M ${startX} ${startY} C ${side} ${startY}, ${side} ${endY}, ${endX} ${endY}`;
  } else {
    const bend = Math.max(28, (endX - startX) * 0.45);
    path = `M ${startX} ${startY} C ${startX + bend} ${startY}, ${endX - bend} ${endY}, ${endX} ${endY}`;
  }
  return <path d={path} className={`flow-edge${active ? " is-active" : ""}${failed ? " is-failed" : ""}${edge.confidence !== "observed" ? " is-uncertain" : ""}${edge.type === "handoff" ? " is-handoff" : ""}${loop ? " is-loop" : ""}`} markerEnd={`url(#${markerId})`} />;
}

function DetailPanel({ node, onClose }: { node: TraceFlowNode; onClose: () => void }) {
  return <aside className="flow-detail-panel" aria-label="Selected execution operation details">
    <div className="flow-detail-header"><div><span className="eyebrow">Selected operation</span><h3>{displayName(node)}</h3></div><button type="button" className="icon-button" onClick={onClose} aria-label="Close inspector"><X size={15} /></button></div>
    <div className="flow-detail-status"><span className={`flow-status-dot flow-status-${statusTone(node)}`} /><strong>{node.status.replaceAll("_", " ")}</strong>{node.error_type && <span className="flow-error-label">{node.error_type}</span>}</div>
    <div className="flow-detail-rows">
      <div><span>Operation</span><strong>{node.event_type.replaceAll("_", " ")}</strong></div>
      <div><span>Duration</span><strong>{formatDuration(node.duration_ms)}</strong></div>
      <div><span>Occurred</span><strong>{formatTimestamp(node.occurred_at)}</strong></div>
      {node.ended_at && <div><span>Ended</span><strong>{formatTimestamp(node.ended_at)}</strong></div>}
      <div><span>Event ID</span><strong className="mono">{shortId(node.event_id)}</strong></div>
      <div><span>Span ID</span><strong className="mono">{shortId(node.span_id)}</strong></div>
      {node.parent_span_id && <div><span>Parent span</span><strong className="mono">{shortId(node.parent_span_id)}</strong></div>}
      {node.integration && <div><span>Integration</span><strong>{node.integration}</strong></div>}
      {node.framework && <div><span>Framework</span><strong>{node.framework}</strong></div>}
    </div>
    {node.error_details && <div className="flow-error-box"><strong><CircleAlert size={14} /> Failure evidence</strong><p>{node.error_details}</p></div>}
    {node.metadata && Object.keys(node.metadata).length > 0 && <details className="flow-metadata"><summary>Captured attributes</summary><pre>{JSON.stringify(node.metadata, null, 2)}</pre></details>}
  </aside>;
}

function TimelineView({ nodes, selectedId, onSelect }: { nodes: TraceFlowNode[]; selectedId?: string; onSelect: (id: string) => void }) {
  const timed = nodes.filter((node) => node.occurred_at).sort((a, b) => (a.occurred_at || "").localeCompare(b.occurred_at || ""));
  if (!timed.length) return <div className="flow-empty-view">Timing data is unavailable for this trace.</div>;
  const start = Math.min(...timed.map((node) => Date.parse(node.occurred_at || "")));
  const end = Math.max(...timed.map((node) => Date.parse(node.occurred_at || "") + (node.duration_ms || 0)), start + 1);
  const total = Math.max(1, end - start);
  return <div className="flow-timeline-view"><div className="flow-timeline-axis"><span>Start</span><span>{formatDuration(total)} observed</span><span>End</span></div>{timed.map((node) => {
    const left = ((Date.parse(node.occurred_at || "") - start) / total) * 100;
    const width = node.duration_ms ? Math.max(1.5, (node.duration_ms / total) * 100) : 1.5;
    return <button type="button" key={node.event_id} className={`flow-timeline-row${selectedId === node.event_id ? " is-selected" : ""}`} onClick={() => onSelect(node.event_id)}><span className="flow-timeline-label">{displayName(node)}</span><span className="flow-timeline-track"><span className={`flow-timeline-bar flow-timeline-${statusTone(node)}`} style={{ left: `${left}%`, width: `${width}%` }} /><span className="flow-timeline-point" style={{ left: `${left}%` }} /></span><span className="flow-timeline-duration">{formatDuration(node.duration_ms)}</span></button>;
  })}</div>;
}

export default function TraceGraph({ nodes, edges }: { nodes: TraceFlowNode[]; edges: TraceFlowEdge[] }) {
  const [selectedId, setSelectedId] = useState<string>();
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [view, setView] = useState<"flow" | "timeline">("flow");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<Point>({ x: 24, y: 24 });
  const [search, setSearch] = useState("");
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const viewportRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const moved = useRef(false);
  const didFit = useRef(false);
  const markerId = `flow-arrow-${useId().replaceAll(":", "")}`;
  const layout = useMemo(() => layoutNodes(nodes, edges), [nodes, edges]);
  const selected = selectedId ? nodes.find((node) => node.event_id === selectedId) : undefined;
  const selectedNeighbors = useMemo(() => {
    if (!selectedId) return new Set<string>();
    const connected = new Set([selectedId]);
    layout.resolvedEdges.forEach(({ from, to }) => {
      if (from.event_id === selectedId) connected.add(to.event_id);
      if (to.event_id === selectedId) connected.add(from.event_id);
    });
    return connected;
  }, [layout.resolvedEdges, selectedId]);
  const searchMatches = useMemo(() => {
    const query = search.trim().toLowerCase();
    return query ? layout.positioned.filter((node) => `${displayName(node)} ${node.event_type} ${node.event_id}`.toLowerCase().includes(query)) : [];
  }, [layout.positioned, search]);
  const failureCount = nodes.filter(isFailed).length;

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const update = () => setViewport({ width: element.clientWidth, height: element.clientHeight });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const fitView = useCallback(() => {
    const element = viewportRef.current;
    if (!element) return;
    const width = element.clientWidth;
    const height = element.clientHeight;
    if (!width || !height) return;
    const nextZoom = Math.max(MIN_ZOOM, Math.min(1.15, (width - 48) / layout.width, (height - 48) / layout.height));
    setZoom(nextZoom);
    setPan({ x: Math.max(16, (width - layout.width * nextZoom) / 2), y: Math.max(16, (height - layout.height * nextZoom) / 2) });
    didFit.current = true;
  }, [layout.height, layout.width]);

  useEffect(() => {
    if (!didFit.current && viewport.width && viewport.height) fitView();
  }, [fitView, viewport.height, viewport.width]);

  function selectNode(id: string) {
    setSelectedId(id);
    setInspectorOpen(true);
  }

  function closeInspector() {
    setInspectorOpen(false);
    setSelectedId(undefined);
  }

  function resetView() {
    setZoom(1);
    setPan({ x: 24, y: 24 });
  }

  function jumpToNode(node: PositionedNode) {
    const element = viewportRef.current;
    selectNode(node.event_id);
    if (!element) return;
    const nextZoom = Math.max(zoom, 0.9);
    setZoom(nextZoom);
    setPan({ x: element.clientWidth / 2 - (node.x + NODE_WIDTH / 2) * nextZoom, y: element.clientHeight / 2 - (node.y + NODE_HEIGHT / 2) * nextZoom });
  }

  function handleWheel(event: ReactWheelEvent<HTMLDivElement>) {
    event.preventDefault();
    const element = viewportRef.current;
    if (!element) return;
    const bounds = element.getBoundingClientRect();
    const cursor = { x: event.clientX - bounds.left, y: event.clientY - bounds.top };
    const nextZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom * (event.deltaY > 0 ? 0.9 : 1.1)));
    const graphPoint = { x: (cursor.x - pan.x) / zoom, y: (cursor.y - pan.y) / zoom };
    setZoom(nextZoom);
    setPan({ x: cursor.x - graphPoint.x * nextZoom, y: cursor.y - graphPoint.y * nextZoom });
  }

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
    moved.current = false;
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    const dx = event.clientX - drag.current.x;
    const dy = event.clientY - drag.current.y;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) moved.current = true;
    setPan({ x: drag.current.panX + dx, y: drag.current.panY + dy });
  }

  function handlePointerUp(event: ReactPointerEvent<HTMLDivElement>) {
    if (drag.current && viewportRef.current?.hasPointerCapture(event.pointerId)) viewportRef.current.releasePointerCapture(event.pointerId);
    drag.current = null;
  }

  return <div className="flow-visualization">
    <div className="flow-toolbar">
      <div className="flow-view-toggle" role="tablist" aria-label="Execution visualization view"><button type="button" className={view === "flow" ? "is-active" : ""} onClick={() => setView("flow")} role="tab" aria-selected={view === "flow"}><Workflow size={14} /> Flow</button><button type="button" className={view === "timeline" ? "is-active" : ""} onClick={() => setView("timeline")} role="tab" aria-selected={view === "timeline"}><Clock3 size={14} /> Timeline</button></div>
      <div className="flow-toolbar-meta"><span>{nodes.length} operations</span><span>{layout.resolvedEdges.length} linked</span>{failureCount > 0 && <span className="flow-failure-count"><CircleAlert size={12} /> {failureCount} failed</span>}</div>
      {view === "flow" && <label className="flow-search"><Search size={14} aria-hidden="true" /><input aria-label="Search operations" placeholder="Search operations" value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && searchMatches[0]) jumpToNode(searchMatches[0]); }} /><span>{searchMatches.length || ""}</span></label>}
      <div className="flow-controls"><button type="button" className="icon-button" onClick={() => setZoom((value) => Math.min(MAX_ZOOM, value + 0.15))} aria-label="Zoom in" title="Zoom in"><Plus size={14} /></button><button type="button" className="icon-button" onClick={() => setZoom((value) => Math.max(MIN_ZOOM, value - 0.15))} aria-label="Zoom out" title="Zoom out"><Minus size={14} /></button><button type="button" className="icon-button" onClick={fitView} aria-label="Fit graph to view" title="Fit to view"><Crosshair size={14} /></button><button type="button" className="icon-button" onClick={resetView} aria-label="Reset graph view" title="Reset view"><RotateCcw size={14} /></button><button type="button" className={`icon-button flow-inspector-toggle${inspectorOpen ? " is-active" : ""}`} onClick={() => setInspectorOpen((value) => !value)} aria-label={inspectorOpen ? "Close inspector" : "Open inspector"} aria-expanded={inspectorOpen} title={inspectorOpen ? "Close inspector" : "Open inspector"}>{inspectorOpen ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}</button></div>
    </div>
    {view === "timeline" ? <TimelineView nodes={nodes} selectedId={selectedId} onSelect={selectNode} /> : <div className={`flow-layout${inspectorOpen ? " has-inspector" : ""}`}><div className="flow-canvas" ref={viewportRef} onWheel={handleWheel} onPointerDown={handlePointerDown} onPointerMove={handlePointerMove} onPointerUp={handlePointerUp} onPointerCancel={handlePointerUp} aria-label="Interactive execution graph" title="Drag to pan, scroll to zoom"><svg width={layout.width} height={layout.height} style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }} role="img" aria-label="Observed execution flow"><defs><marker id={markerId} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto"><path d="M 0 0 L 8 4 L 0 8 z" fill="var(--border-strong)" /></marker></defs>{layout.resolvedEdges.map((relation) => { const active = !selectedId || (selectedNeighbors.has(relation.from.event_id) && selectedNeighbors.has(relation.to.event_id)); return <EdgePath key={edgeKey(relation.edge, relation.index)} relation={relation} active={active} markerId={markerId} />; })}{layout.positioned.map((node) => { const active = !selectedId || selectedNeighbors.has(node.event_id); const tone = statusTone(node); const matched = searchMatches.some((match) => match.event_id === node.event_id); return <g key={node.event_id} className={`flow-node flow-node-${tone}${selectedId === node.event_id ? " is-selected" : ""}${active ? "" : " is-dimmed"}${matched ? " is-search-match" : ""}`} transform={`translate(${node.x} ${node.y})`} onPointerDown={(event) => event.stopPropagation()} onClick={(event) => { event.stopPropagation(); if (!moved.current) selectNode(node.event_id); }} tabIndex={0} role="button" aria-label={`${displayName(node)}, ${node.event_type}, ${node.status}`} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectNode(node.event_id); } }}><rect width={NODE_WIDTH} height={NODE_HEIGHT} rx="8" /><circle className="flow-node-indicator" cx="17" cy="16" r="4" /><text className="flow-node-type" x="28" y="19">{truncate(node.event_type.replaceAll("_", " "), 21)}</text><text className="flow-node-label" x="14" y="37">{truncate(displayName(node), 27)}</text><text className="flow-node-meta" x="14" y="50">{node.status.replaceAll("_", " ")} · {formatDuration(node.duration_ms)}</text>{node.failed && <g className="flow-node-error"><circle cx={NODE_WIDTH - 16} cy="16" r="8" /><text x={NODE_WIDTH - 19.5} y="20">!</text></g>}</g>; })}</svg><div className="flow-legend"><span><i className="legend-agent" />Agent span</span><span><i className="legend-tool" />Tool call</span><span><i className="legend-handoff" />Handoff</span><span><i className="legend-failed" />Failed</span></div><span className="flow-canvas-hint">Drag to pan · scroll to zoom</span></div>{inspectorOpen && (selected ? <DetailPanel node={selected} onClose={closeInspector} /> : <div className="flow-placeholder"><PanelRightOpen size={19} /><strong>Select an operation</strong><p>Choose a node to inspect timing, identifiers, attributes, and failure evidence.</p></div>)}</div>}
    <div className="flow-footnote"><span><Check size={12} /> Solid edges are captured parent or handoff relationships</span>{layout.resolvedEdges.length === 0 && nodes.length > 1 && <span className="flow-unresolved">No relationships were captured; nodes remain unconnected.</span>}{layout.unresolvedCount > 0 && <span className="flow-unresolved">{layout.unresolvedCount} relationship{layout.unresolvedCount === 1 ? "" : "s"} could not be resolved from captured IDs.</span>}{edges.some((edge) => edge.confidence !== "observed") && <span><span className="flow-dash-key" /> Dashed edges indicate uncertain relationships</span>}</div>
  </div>;
}


