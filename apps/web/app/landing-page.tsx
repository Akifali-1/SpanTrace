"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
import { useRef, useState } from "react";
import { MarketingFooter, MarketingHeader } from "./marketing-chrome";
import { useTheme } from "./components/theme-provider";

gsap.registerPlugin(ScrollTrigger, useGSAP);

/* ------------------------------------------------------------------ */
/* Data                                                                */
/* ------------------------------------------------------------------ */

type Point = { x: number; y: number };
type IsoBox = { x: number; y: number; z: number; w: number; d: number; h: number };
type Tone = "neutral" | "pending" | "failure";

const events = [
  { id: "planner", agent: "planner", action: "handoff", time: "09:41:03.104", state: "observed" },
  { id: "hotel-search", agent: "hotel_search", action: "search_hotels", time: "09:41:03.421", state: "observed" },
  { id: "policy-guard", agent: "policy_guard", action: "approval.check", time: "09:41:03.806", state: "pending" },
  { id: "booking-agent", agent: "booking_agent", action: "create_reservation", time: "09:41:04.018", state: "failed" },
  { id: "regression-runner", agent: "regression_runner", action: "approval_invariant", time: "09:41:04.430", state: "passed" },
];

const constellationNodes = [
  { id: "trace_7bd2", label: "run", x: 12, y: 50, event: "travel-booking" },
  { id: "span_planner", label: "planner", x: 25, y: 26, event: "handoff" },
  { id: "span_plan_model", label: "model", x: 37, y: 14, event: "plan_ready" },
  { id: "span_search", label: "hotel_search", x: 38, y: 43, event: "search_hotels" },
  { id: "span_search_tool", label: "tool", x: 50, y: 30, event: "search_hotels" },
  { id: "span_budget", label: "budget", x: 53, y: 57, event: "within_budget" },
  { id: "span_policy", label: "policy_guard", x: 63, y: 38, event: "approval.check" },
  { id: "span_policy_state", label: "state", x: 73, y: 23, event: "pending" },
  { id: "span_booking", label: "booking_agent", x: 77, y: 54, event: "create_reservation" },
  { id: "span_booking_tool", label: "tool", x: 88, y: 43, event: "reservation_created" },
  { id: "span_response", label: "response", x: 91, y: 70, event: "handoff" },
  { id: "span_regression", label: "regression", x: 63, y: 76, event: "approval_invariant" },
  { id: "span_fix", label: "corrected", x: 43, y: 77, event: "wait_for_approval" },
  { id: "span_evidence", label: "evidence", x: 26, y: 72, event: "POL-014" },
];

const constellationEdges = [
  ["trace_7bd2", "span_planner"], ["span_planner", "span_plan_model"], ["span_planner", "span_search"],
  ["span_search", "span_search_tool"], ["span_search", "span_budget"], ["span_budget", "span_policy"],
  ["span_policy", "span_policy_state"], ["span_policy", "span_booking"], ["span_booking", "span_booking_tool"],
  ["span_booking", "span_response"], ["span_booking", "span_regression"], ["span_regression", "span_fix"],
  ["span_fix", "span_evidence"], ["span_evidence", "trace_7bd2"], ["span_search_tool", "span_policy"],
  ["span_policy_state", "span_booking_tool"], ["span_response", "span_regression"],
];
const nodeById = new Map(constellationNodes.map((node) => [node.id, node]));

const logLines = [
  { time: "09:41:03.104", text: "planner → handoff hotel-search", level: 0 },
  { time: "09:41:03.176", text: "planner.output destination=Goa nights=2", level: 1 },
  { time: "09:41:03.421", text: "hotel_search → search_hotels", level: 0 },
  { time: "09:41:03.512", text: "hotel_search.output candidate=Palm Grove", level: 1 },
  { time: "09:41:03.606", text: "hotel_search → handoff budget-validator", level: 0 },
  { time: "09:41:03.704", text: "budget_validator.output within_budget=true", level: 1 },
  { time: "09:41:03.806", text: "policy_guard → approval.check", level: 0 },
  { time: "09:41:03.842", text: "approval_state=pending", level: 1 },
  { time: "09:41:03.901", text: "policy_guard → handoff booking-agent", level: 0 },
  { time: "09:41:04.018", text: "booking_agent → create_reservation", level: 0, failure: true },
  { time: "09:41:04.019", text: "reservation_id=MOCK-1 created=true", level: 1, failure: true },
  { time: "09:41:04.105", text: "incident.detected POL-014", level: 0, failure: true },
  { time: "09:41:04.202", text: "regression_case.created travel-approval-01", level: 0 },
  { time: "09:41:04.430", text: "approval_invariant passed in 412ms", level: 0 },
];

const loopRows = [
  ["01", "Trace the system", "Follow every handoff, tool call, and policy decision in one run.", "trace_7bd2 / 5 events"],
  ["02", "Find the cause", "Locate the event that changed the outcome, not just the last thing that failed.", "POL-014 / booking_agent"],
  ["03", "Turn failures into tests", "Capture the violated invariant as a deterministic regression case.", "travel-approval-01 / assert"],
  ["04", "Verify the fix", "Replay the same path and prove the side effect is gone.", "passed / 412ms"],
];

/* ------------------------------------------------------------------ */
/* Isometric model geometry (computed once, viewBox fits the drawing)  */
/* ------------------------------------------------------------------ */

function project(x: number, y: number, z: number): Point {
  return { x: 480 + (x - y) * 1.15, y: 110 + (x + y) * 0.36 - z };
}

function pointsToString(points: Point[]) {
  return points.map((point) => `${point.x},${point.y}`).join(" ");
}

function isoBox(box: IsoBox) {
  const top = [
    project(box.x, box.y, box.z + box.h),
    project(box.x + box.w, box.y, box.z + box.h),
    project(box.x + box.w, box.y + box.d, box.z + box.h),
    project(box.x, box.y + box.d, box.z + box.h),
  ];
  const left = [top[0], top[3], project(box.x, box.y + box.d, box.z), project(box.x, box.y, box.z)];
  const right = [top[1], top[2], project(box.x + box.w, box.y + box.d, box.z), project(box.x + box.w, box.y, box.z)];
  return { top, left, right };
}

// Already ordered back to front (x + y ascending).
const slabs: (IsoBox & { label: string; tone: Tone })[] = [
  { x: 40, y: 8, z: 0, w: 120, d: 66, h: 30, label: "planner", tone: "neutral" },
  { x: 188, y: 48, z: 0, w: 122, d: 66, h: 30, label: "search", tone: "neutral" },
  { x: 340, y: 88, z: 0, w: 126, d: 66, h: 30, label: "policy guard", tone: "pending" },
  { x: 496, y: 128, z: 0, w: 132, d: 66, h: 30, label: "booking", tone: "failure" },
  { x: 656, y: 168, z: 0, w: 130, d: 66, h: 30, label: "response", tone: "neutral" },
];

const SHADOW = { x: 8, y: 12 };
const slabFaces = slabs.map(isoBox);
const slabCenters = slabs.map((slab) => project(slab.x + slab.w / 2, slab.y + slab.d / 2, slab.z + slab.h));
const connectors = slabs.slice(0, -1).map((slab, index) => {
  const next = slabs[index + 1];
  return {
    a: project(slab.x + slab.w, slab.y + slab.d / 2, slab.z + slab.h),
    b: project(next.x, next.y + next.d / 2, next.z + next.h),
  };
});

const hull = slabFaces.flatMap((face) => [...face.top, ...face.left, ...face.right]);
const hullXs = hull.map((point) => point.x);
const hullYs = hull.map((point) => point.y);
const VB_PAD = 26;
const vbMinX = Math.min(...hullXs) - VB_PAD;
const vbMinY = Math.min(...hullYs) - VB_PAD;
const vbWidth = Math.max(...hullXs) + SHADOW.x + VB_PAD - vbMinX;
const vbHeight = Math.max(...hullYs) + SHADOW.y + VB_PAD - vbMinY;
const VIEWBOX = `${Math.floor(vbMinX)} ${Math.floor(vbMinY)} ${Math.ceil(vbWidth)} ${Math.ceil(vbHeight)}`;

/* ------------------------------------------------------------------ */
/* Components                                                          */
/* ------------------------------------------------------------------ */

function TraceModel({ variant }: { variant: "hero" | "verify" }) {
  const verified = variant === "verify";
  const titleId = `${variant}-model-title`;
  const descId = `${variant}-model-desc`;
  return (
    <div className={`trace-model ${verified ? "trace-model-verified" : ""}`} data-span="trace-model" data-model={variant}>
      <svg viewBox={VIEWBOX} role="img" aria-labelledby={`${titleId} ${descId}`} preserveAspectRatio="xMidYMid meet">
        <title id={titleId}>Isometric trace replay</title>
        <desc id={descId}>Five connected slabs show a planner handoff, hotel search, policy check, booking attempt, and response.</desc>
        <g className="model-lines" aria-hidden="true">
          {connectors.map(({ a, b }, index) => (
            <g key={index}>
              <line className="model-line" x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
              <rect className="model-tick" x={(a.x + b.x) / 2 - 4} y={(a.y + b.y) / 2 - 4} width="8" height="8" />
            </g>
          ))}
        </g>
        {slabs.map((slab, index) => {
          const faces = slabFaces[index];
          const tone = slab.tone === "failure" ? (verified ? "verified" : "neutral") : slab.tone;
          return (
            <g className={`model-slab model-slab-${tone}`} data-slab={slab.label} key={slab.label}>
              <polygon className="model-shadow" points={pointsToString(faces.top.map((point) => ({ x: point.x + SHADOW.x, y: point.y + SHADOW.y })))} />
              <g className="slab-body">
                <polygon className="model-face model-face-left" points={pointsToString(faces.left)} />
                <polygon className="model-face model-face-right" points={pointsToString(faces.right)} />
                <polygon className="model-face model-face-top" points={pointsToString(faces.top)} />
                <text className="model-label" x={faces.top[0].x + 23} y={faces.top[0].y + 21}>{slab.label}</text>
                {slab.tone === "failure" && <text className="model-mark" x={faces.top[1].x - 16} y={faces.top[1].y + 19}>!</text>}
                {slab.tone === "failure" && verified && <text className="model-check" x={faces.top[1].x - 18} y={faces.top[1].y + 20}>✓</text>}
              </g>
            </g>
          );
        })}
        <rect className="model-packet" x={slabCenters[0].x - 5} y={slabCenters[0].y - 5} width="10" height="10" aria-hidden="true" />
      </svg>
      <p className="model-note">Five recorded spans. One responsible event.</p>
    </div>
  );
}

function SceneIndex({ code, label }: { code: string; label: string }) {
  return <div className="scene-index"><span>{code}</span><span>{label}</span></div>;
}

function EventRail({ highlight = "" }: { highlight?: string }) {
  return (
    <div className="event-rail" aria-label="Illustrative trace data">
      {events.map((event) => (
        <div className={`event-row ${event.id === highlight ? "is-highlighted" : ""} ${event.state === "failed" ? "is-failure" : ""} ${event.state === "passed" ? "is-passed" : ""}`} key={event.id} data-span={event.id}>
          <span className="event-dot" aria-hidden="true" />
          <span className="event-agent">{event.agent}</span>
          <span className="event-action">{event.action}</span>
          <span className="event-time">{event.time}</span>
          <span className="event-state">{event.state}</span>
        </div>
      ))}
      <span className="data-label">illustrative trace data</span>
    </div>
  );
}

function Constellation() {
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const active = activeNode ? nodeById.get(activeNode) : null;
  return (
    <div className="constellation" data-span="constellation">
      <svg viewBox="0 0 100 100" role="img" aria-labelledby="constellation-title constellation-desc">
        <title id="constellation-title">One run. Many agents.</title>
        <desc id="constellation-desc">Fourteen illustrative trace nodes connected across planners, tools, policies, and regression evidence.</desc>
        <g className="constellation-edges" aria-hidden="true">
          {constellationEdges.map(([fromId, toId]) => {
            const from = nodeById.get(fromId);
            const to = nodeById.get(toId);
            if (!from || !to) return null;
            const isActive = activeNode === fromId || activeNode === toId;
            return <line className={isActive ? "is-active" : ""} key={`${fromId}-${toId}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} />;
          })}
        </g>
        <g className="constellation-nodes">
          {constellationNodes.map((node) => (
            <g
              className={`constellation-node ${activeNode && activeNode !== node.id ? "is-dimmed" : ""} ${activeNode === node.id ? "is-active" : ""}`}
              key={node.id}
              tabIndex={0}
              role="button"
              aria-label={`${node.label}, ${node.event}, ${node.id}`}
              onMouseEnter={() => setActiveNode(node.id)}
              onMouseLeave={() => setActiveNode(null)}
              onFocus={() => setActiveNode(node.id)}
              onBlur={() => setActiveNode(null)}
              onKeyDown={(event) => { if (event.key === "Escape") setActiveNode(null); }}
            >
              <circle cx={node.x} cy={node.y} r={node.label === "run" ? 2.4 : 1.6} />
              <text x={node.x + 2.8} y={node.y - 2}>{node.label}</text>
            </g>
          ))}
        </g>
      </svg>
      <div className={`constellation-tooltip ${activeNode ? "is-visible" : ""}`} aria-live="polite">
        {active ? <><span>{active.id}</span><strong>{active.event}</strong></> : <span>Hover or focus a node to inspect the path.</span>}
      </div>
      <p className="data-label">illustrative trace data / 14 observed nodes</p>
    </div>
  );
}

function LogReplay() {
  return (
    <div className="log-replay" data-span="log-replay">
      {logLines.map((line) => (
        <div className={`log-line ${line.failure ? "is-failure" : ""}`} data-log-level={line.level} key={`${line.time}-${line.text}`}>
          <span>{line.time}</span>
          <code>{line.level === 1 && <i className="log-branch" aria-hidden="true">↳ </i>}{line.text}</code>
        </div>
      ))}
      <span className="data-label">illustrative trace data / captured log stream</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

type Stop = { st: ScrollTrigger; tc: [number, number] };

// Start state for "draw this line": the far end sits on the near end.
const collapseLine = {
  x2: (_index: number, target: Element) => target.getAttribute("x1") ?? "0",
  y2: (_index: number, target: Element) => target.getAttribute("y1") ?? "0",
};

export default function LandingPage() {
  const root = useRef<HTMLDivElement>(null);
  const timecode = useRef<HTMLElement>(null);
  const cursor = useRef<HTMLDivElement>(null);
  const cursorLabel = useRef<HTMLSpanElement>(null);
  const { preference } = useTheme();

  useGSAP(() => {
    const el = root.current;
    const timecodeElement = timecode.current;
    if (!el || !timecodeElement) return;

    const styles = getComputedStyle(document.documentElement);
    const color = (name: string) => styles.getPropertyValue(name).trim();
    const colors = {
      bg: color("--landing-bg"),
      surface1: color("--landing-surface-1"),
      danger: color("--landing-danger"),
      dangerTint: color("--landing-danger-tint"),
      dangerWash: color("--landing-danger-wash"),
      success: color("--landing-success"),
      text: color("--landing-text"),
      modelTop: color("--landing-model-top"),
      successModel: color("--landing-success"),
      failureTint: color("--landing-failure-tint"),
    };

    ScrollTrigger.config({ ignoreMobileResize: true });

    const all = <T extends Element = HTMLElement>(selector: string) => gsap.utils.toArray<T>(selector, el);
    const one = <T extends Element = HTMLElement>(selector: string) => el.querySelector<T>(selector);
    const scene = (name: string) => one<HTMLElement>(`[data-scene="${name}"]`);

    /* ---------- timecode (pure function of scroll position) ---------- */
    let lastTimecode = "";
    const setTimecode = (value: number) => {
      const total = Math.round(value * 1000);
      const text = `09:41:${String(Math.floor(total / 1000)).padStart(2, "0")}.${String(total % 1000).padStart(3, "0")}`;
      if (text === lastTimecode) return;
      lastTimecode = text;
      timecodeElement.textContent = text;
    };

    /* ---------- cursor inspector ---------- */
    const fine = window.matchMedia("(pointer: fine)").matches;
    const cursorElement = cursor.current;
    const labelElement = cursorLabel.current;
    let cleanupCursor = () => {};
    if (fine && cursorElement && labelElement) {
      const xTo = gsap.quickTo(cursorElement, "x", { duration: 0.18, ease: "power2.out" });
      const yTo = gsap.quickTo(cursorElement, "y", { duration: 0.18, ease: "power2.out" });
      let px = 0;
      let py = 0;
      let idle = 0;
      const labelFor = (target: Element | null) => {
        const span = target?.closest<HTMLElement>("[data-span]")?.dataset.span;
        labelElement.textContent = span && !span.startsWith("scene-") ? span : "pointer / idle";
      };
      const onMove = (event: PointerEvent) => {
        px = event.clientX;
        py = event.clientY;
        cursorElement.classList.add("is-active");
        xTo(px);
        yTo(py);
        labelFor(event.target as Element | null);
      };
      const onScrollHide = () => {
        cursorElement.classList.add("is-scrolling");
        window.clearTimeout(idle);
        idle = window.setTimeout(() => {
          cursorElement.classList.remove("is-scrolling");
          labelFor(document.elementFromPoint(px, py));
        }, 160);
      };
      const onLeave = () => cursorElement.classList.remove("is-active");
      window.addEventListener("pointermove", onMove, { passive: true });
      window.addEventListener("scroll", onScrollHide, { passive: true });
      document.documentElement.addEventListener("pointerleave", onLeave);
      cleanupCursor = () => {
        window.clearTimeout(idle);
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("scroll", onScrollHide);
        document.documentElement.removeEventListener("pointerleave", onLeave);
      };
    }

    /* ---------- motion ---------- */
    const mm = gsap.matchMedia();
    mm.add(
      {
        desk: "(min-width: 900px) and (min-height: 700px) and (prefers-reduced-motion: no-preference)",
        flow: "(prefers-reduced-motion: no-preference) and ((max-width: 899px) or (max-height: 699px))",
        reduce: "(prefers-reduced-motion: reduce)",
      },
      (ctx) => {
        const conditions = ctx.conditions as { desk: boolean; flow: boolean; reduce: boolean };
        if (conditions.reduce) {
          el.dataset.anim = "off";
          setTimecode(4.43);
          return;
        }

        const pinned = conditions.desk;
        el.dataset.anim = "on";

        /* ----- smooth scroll (one Lenis, driven by the GSAP ticker) ----- */
        let lenis: Lenis | null = null;
        let tick: ((time: number) => void) | null = null;
        if (fine) {
          const instance = new Lenis({ lerp: 0.1, smoothWheel: true });
          lenis = instance;
          instance.on("scroll", ScrollTrigger.update);
          tick = (time: number) => instance.raf(time * 1000);
          gsap.ticker.add(tick);
          gsap.ticker.lagSmoothing(0);
        }

        const onAnchorClick = (event: MouseEvent) => {
          const link = (event.target as Element).closest<HTMLAnchorElement>('a[href^="#"]');
          if (!link) return;
          const id = link.getAttribute("href")?.slice(1) ?? "";
          const target = id ? document.getElementById(id) : null;
          if (!target) return;
          event.preventDefault();
          const trigger = ScrollTrigger.getById(id);
          const y = id === "trace" ? 0 : trigger ? trigger.start + 2 : target.getBoundingClientRect().top + window.scrollY;
          if (lenis) lenis.scrollTo(y, { duration: 1.3 });
          else window.scrollTo({ top: y, behavior: "smooth" });
          window.history.replaceState(null, "", `#${id}`);
        };
        el.addEventListener("click", onAnchorClick);

        /* ----- fit: a pinned scene must never be taller than the screen ----- */
        const fitTargets = all("[data-fit]");
        const fit = () => {
          if (!pinned) return;
          fitTargets.forEach((node) => {
            const section = node.closest<HTMLElement>("section");
            if (!section) return;
            const style = getComputedStyle(section);
            const available = window.innerHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
            node.style.setProperty("--fit", String(Math.min(1, available / Math.max(1, node.offsetHeight))));
          });
        };
        fit();
        if (pinned) ScrollTrigger.addEventListener("refreshInit", fit);

        /* ----- scene timelines: always created in DOM order ----- */
        const stops: Stop[] = [];
        const sceneTL = (name: string, dist: number, tc: [number, number]) => {
          const trigger = scene(name);
          if (!trigger) return null;
          const tl = gsap.timeline({
            defaults: { ease: "none" },
            scrollTrigger: pinned
              ? { id: name, trigger, start: "top top", end: () => `+=${Math.round(window.innerHeight * dist)}`, pin: true, scrub: true, invalidateOnRefresh: true }
              : { id: name, trigger, start: "top 72%", end: "top 12%", scrub: true },
          });
          tl.to({}, { duration: 0 }, 1); // timeline length is always exactly 1
          if (tl.scrollTrigger) stops.push({ st: tl.scrollTrigger, tc });
          return tl;
        };

        const lift = (tl: gsap.core.Timeline, body: Element, at: number) => {
          tl.to(body, { y: -9, duration: 0.05 }, Math.max(0, at - 0.05)).to(body, { y: 0, duration: 0.07 }, at + 0.02);
        };
        const runPacket = (tl: gsap.core.Timeline, scope: string, legs: { to: number; at: number; dur: number }[]) => {
          const packet = one(`${scope} .model-packet`);
          const bodies = all(`${scope} .slab-body`);
          if (!packet || bodies.length < slabCenters.length) return;
          const c0 = slabCenters[0];
          tl.fromTo(packet, { opacity: 0 }, { opacity: 1, duration: 0.03 }, 0.01);
          lift(tl, bodies[0], 0.05);
          legs.forEach(({ to, at, dur }) => {
            tl.to(packet, { x: slabCenters[to].x - c0.x, y: slabCenters[to].y - c0.y, duration: dur }, at);
            lift(tl, bodies[to], at + dur);
          });
        };

        /* E-01 TRACE: intro on load, packet walks the trace on scroll, booking breaks */
        const intro = gsap.timeline({ defaults: { ease: "power3.out" } });
        intro
          .from(all(".hero-line"), { y: 46, opacity: 0, duration: 1, stagger: 0.09, ease: "power4.out" }, 0)
          .from(all(".hero-copy .kicker, .hero-sub, .hero-actions, .microcopy"), { y: 16, opacity: 0, duration: 0.8, stagger: 0.08 }, 0.35)
          .from(all(".hero-inner .model-slab"), { y: 26, opacity: 0, duration: 0.8, stagger: 0.08 }, 0.25)
          .from(all(".hero-inner .model-line"), { attr: collapseLine, duration: 0.6, stagger: 0.08 }, 0.7)
          .from(all(".hero-inner .model-tick, .hero-inner .model-note"), { opacity: 0, duration: 0.5, stagger: 0.05 }, 0.9);

        const trace = sceneTL("trace", 1, [3.104, 4.018]);
        if (trace) {
          runPacket(trace, ".hero-inner", [
            { to: 1, at: 0.08, dur: 0.16 },
            { to: 2, at: 0.26, dur: 0.16 },
            { to: 3, at: 0.44, dur: 0.16 },
          ]);
          const faces = all<SVGElement>('.hero-inner [data-slab="booking"] .model-face');
          const label = one<SVGElement>('.hero-inner [data-slab="booking"] .model-label');
          const mark = one<SVGElement>(".hero-inner .model-mark");
           trace.to(faces, { fill: colors.danger, stroke: colors.danger, duration: 0.05, ease: "steps(2)" }, 0.62);
           if (label) trace.to(label, { fill: colors.bg, duration: 0.02 }, 0.62);
          if (mark) trace.fromTo(mark, { opacity: 0 }, { opacity: 1, duration: 0.03, ease: "steps(1)" }, 0.64);
          trace.to(all(".hero-copy"), { y: -22, opacity: 0.55, duration: 0.2 }, 0.8);
        }

        /* E-02 FAILURE: rows light up, policy waits, booking hard-cuts */
        const failure = sceneTL("failure", 1.2, [4.018, 4.018]);
        const failureScene = scene("failure");
        if (failure && failureScene) {
          const rows = all(".scene-failure .event-row");
          const shake = all(".scene-failure .failure-copy, .scene-failure .event-rail");
          rows.forEach((row, index) => {
            if (index === 3) {
              failure.fromTo(row, { x: -28, opacity: 0.2 }, { x: 0, opacity: 1, duration: 0.06, ease: "steps(3)" }, 0.52);
            } else {
              failure.fromTo(row, { opacity: 0.2 }, { opacity: 1, duration: 0.08 }, index === 4 ? 0.72 : 0.06 + index * 0.14);
            }
          });
          failure
             .fromTo(failureScene, { backgroundColor: colors.surface1 }, { backgroundColor: colors.failureTint, duration: 0.06, ease: "steps(3)" }, 0.52)
            .fromTo(all(".scene-failure .failure-tag"), { opacity: 0, x: -14 }, { opacity: 1, x: 0, duration: 0.06, ease: "steps(3)" }, 0.56)
            .fromTo(shake, { x: 0 }, { x: 5, duration: 0.02, ease: "steps(1)" }, 0.52)
            .to(shake, { x: -4, duration: 0.02, ease: "steps(1)" }, 0.54)
            .to(shake, { x: 0, duration: 0.02, ease: "steps(1)" }, 0.56);
        }

        /* E-03 INVESTIGATE: the report assembles itself */
        const investigate = sceneTL("investigate", 1.1, [4.018, 4.018]);
        if (investigate) {
          investigate.fromTo(all(".incident-report"), { y: 60, opacity: 0.35 }, { y: 0, opacity: 1, duration: 0.2 }, 0);
          const parts: [string, number][] = [
            [".report-header", 0.1], [".report-meta", 0.22], [".report-grid > div:first-child", 0.32],
            [".report-grid > div:last-child", 0.4], [".report-path", 0.52], [".payload-block", 0.64], [".report-footer", 0.8],
          ];
          parts.forEach(([selector, at]) => investigate.fromTo(all(`.incident-report ${selector}`), { opacity: 0.1, y: 14 }, { opacity: 1, y: 0, duration: 0.1 }, at));
          investigate.fromTo(all(".report-path span"), { opacity: 0 }, { opacity: 1, duration: 0.04, stagger: 0.04 }, 0.56);
          investigate.fromTo(all(".report-stamp"), { scale: 1.8, rotation: -10, opacity: 0 }, { scale: 1, rotation: 2, opacity: 1, duration: 0.08, ease: "steps(3)" }, 0.74);
        }

        /* E-LOGS: log lines arrive, indent into a tree, then the loop rows */
        const logs = sceneTL("logs", 1.4, [4.018, 4.018]);
        if (logs) {
          const lines = all(".log-line");
          lines.forEach((line, index) => logs.fromTo(line, { opacity: 0.14 }, { opacity: 1, duration: 0.05 }, 0.02 + index * 0.026));
          logs
             .fromTo(all(".log-line.is-failure"), { backgroundColor: "transparent" }, { backgroundColor: colors.dangerTint, duration: 0.05 }, 0.44)
            .fromTo(lines.filter((line) => line.dataset.logLevel === "1"), { x: -22 }, { x: 0, duration: 0.14 }, 0.5)
            .fromTo(all(".log-branch"), { opacity: 0 }, { opacity: 1, duration: 0.1 }, 0.56);
          all(".loop-row").forEach((row, index) => logs.fromTo(row, { opacity: 0.12, y: 14 }, { opacity: 1, y: 0, duration: 0.08 }, 0.66 + index * 0.08));
        }

        /* E-04 REPRODUCE: the incident becomes a test */
        const reproduce = sceneTL("reproduce", 1, [4.018, 3.104]);
        if (reproduce) {
          reproduce.fromTo(all(".test-card"), { x: 90, opacity: 0.25 }, { x: 0, opacity: 1, duration: 0.22 }, 0);
          all(".test-code .code-line").forEach((line, index) => reproduce.fromTo(line, { opacity: 0, x: -10 }, { opacity: 1, x: 0, duration: 0.06 }, 0.26 + index * 0.09));
          reproduce
             .fromTo(all(".test-code-accent"), { backgroundColor: "transparent" }, { backgroundColor: colors.dangerWash, duration: 0.06 }, 0.56)
            .fromTo(all(".test-details"), { opacity: 0.1 }, { opacity: 1, duration: 0.1 }, 0.66)
            .fromTo(all(".rewind-mark"), { opacity: 0.2 }, { opacity: 1, duration: 0.06 }, 0.76)
            .fromTo(all(".rewind-glyph"), { rotation: 0 }, { rotation: -360, duration: 0.2 }, 0.76);
        }

        /* E-05 VERIFY: same path, booking now waits for approval */
        const verify = sceneTL("verify", 1.1, [3.104, 4.43]);
        if (verify) {
          runPacket(verify, ".verify-model", [
            { to: 1, at: 0.06, dur: 0.12 },
            { to: 2, at: 0.2, dur: 0.12 },
            { to: 3, at: 0.5, dur: 0.12 },
            { to: 4, at: 0.68, dur: 0.12 },
          ]);
          const faces = all<SVGElement>('.verify-model [data-slab="booking"] .model-face');
          const label = one<SVGElement>('.verify-model [data-slab="booking"] .model-label');
          const policy = one<SVGElement>('.verify-model [data-slab="policy guard"] .model-face-top');
           if (policy) verify.fromTo(policy, { fill: colors.modelTop }, { fill: colors.successModel, duration: 0.06 }, 0.34);
           verify.fromTo(faces, { fill: colors.danger, stroke: colors.danger }, { fill: colors.success, stroke: colors.text, duration: 0.08, ease: "steps(2)" }, 0.62);
           if (label) verify.fromTo(label, { fill: colors.bg }, { fill: colors.text, duration: 0.02 }, 0.62);
          verify
            .fromTo(all(".verify-model .model-mark"), { opacity: 1 }, { opacity: 0, duration: 0.04, ease: "steps(1)" }, 0.62)
            .fromTo(all(".verify-model .model-check"), { opacity: 0 }, { opacity: 1, duration: 0.06, ease: "steps(1)" }, 0.66)
            .fromTo(all(".verify-result"), { opacity: 0.15, x: -14 }, { opacity: 1, x: 0, duration: 0.1 }, 0.7)
            .fromTo(all(".checkmark"), { scale: 0.4 }, { scale: 1, duration: 0.08, ease: "steps(3)" }, 0.72)
            .fromTo(all(".verify-time"), { opacity: 0 }, { opacity: 1, duration: 0.08 }, 0.84);
        }

        /* ----- non-pinned pieces: created after all pins ----- */
        const constellation = scene("constellation");
        if (constellation) {
          const tl = gsap.timeline({ defaults: { ease: "none" }, scrollTrigger: { trigger: constellation, start: "top 70%", end: "center 50%", scrub: true } });
          tl.from(all(".constellation-edges line"), { attr: collapseLine, duration: 0.5, stagger: 0.03 }, 0)
            .from(all(".constellation-node circle"), { attr: { r: 0 }, duration: 0.2, stagger: 0.04 }, 0.05)
            .from(all(".constellation-node text"), { opacity: 0, duration: 0.2, stagger: 0.04 }, 0.1);
        }

        all("[data-reveal]").forEach((node) => {
          gsap.from(node, { y: 40, opacity: 0, duration: 1, ease: "power3.out", scrollTrigger: { trigger: node, start: "top 88%", once: true } });
        });

        const updateTimecode = () => {
          const y = window.scrollY;
          let value = 3.104;
          for (const { st, tc } of stops) {
            if (y < st.start) break;
            const p = Math.min(1, Math.max(0, (y - st.start) / Math.max(1, st.end - st.start)));
            value = tc[0] + (tc[1] - tc[0]) * p;
          }
          setTimecode(value);
        };
        ScrollTrigger.create({ start: 0, end: "max", onUpdate: updateTimecode, onRefresh: updateTimecode });
        updateTimecode();

        let cancelled = false;
         const onThemeChange = () => ScrollTrigger.refresh();
         window.addEventListener("spantrace-theme-change", onThemeChange);
         document.fonts.ready.then(() => { if (!cancelled) ScrollTrigger.refresh(); });

        return () => {
           cancelled = true;
           window.removeEventListener("spantrace-theme-change", onThemeChange);
          el.removeEventListener("click", onAnchorClick);
          ScrollTrigger.removeEventListener("refreshInit", fit);
          fitTargets.forEach((node) => node.style.removeProperty("--fit"));
          if (tick) gsap.ticker.remove(tick);
          lenis?.destroy();
        };
      }
    );

    return () => {
      cleanupCursor();
      mm.revert();
    };
  }, { scope: root, dependencies: [preference], revertOnUpdate: true });

  return (
    <div className="landing-page" data-landing="true" data-anim="pending" ref={root} suppressHydrationWarning>
      <noscript><style>{`.landing-page[data-anim="pending"] * { opacity: 1 !important; }`}</style></noscript>
      <a className="skip-link" href="#main-content">Skip to incident replay</a>
      <MarketingHeader current="landing" />
      <div className="timecode" data-span="timecode" aria-label="Current replay time"><span className="timecode-label">RUN / trace_7bd2</span><strong ref={timecode} data-timecode>09:41:03.104</strong></div>
      <div className="cursor-inspector" ref={cursor} aria-hidden="true"><span className="cursor-inspector-label" ref={cursorLabel}>pointer / idle</span></div>

      <main id="main-content">
        <section className="scene scene-trace" id="trace" data-scene="trace" data-span="scene-trace">
          <SceneIndex code="E-01" label="TRACE" />
          <div className="scene-inner hero-inner" data-fit>
            <div className="hero-copy">
              <p className="kicker">A replayable incident / POL-014</p>
              <h1>
                <span className="hero-line">Every</span>{" "}
                <span className="hero-line">failure</span>{" "}
                <span className="hero-line"><em>has a</em></span>{" "}
                <span className="hero-line"><em>cause.</em></span>
              </h1>
              <p className="hero-sub">SpanTrace traces multi-agent runs, finds the event that broke them, and turns the failure into a test that proves the fix.</p>
              <div className="hero-actions">
                <a className="button button-solid" href="#failure" data-span="cta-incident">See the incident <span>↓</span></a>
                <a className="button button-line" href="#sdk" data-span="cta-sdk">Read the SDK guide <span>↗</span></a>
              </div>
              <p className="microcopy">Scroll to replay one travel-booking run from first handoff to verified fix.</p>
            </div>
            <TraceModel variant="hero" />
          </div>
          <div className="scene-foot"><span>SCROLL POSITION = TIME</span><span>01 / 05</span></div>
        </section>

        <section className="band band-constellation" id="constellation" data-scene="constellation" data-span="scene-constellation">
          <div className="band-index"><span>01 / NETWORK</span><span>illustrative trace data</span></div>
          <div className="band-inner constellation-inner">
            <div className="band-copy"><p className="kicker" data-reveal>One run / many agents</p><h2 data-reveal>Context is the connective tissue.</h2><p data-reveal>Real systems are not a single chain. SpanTrace follows every handoff across planners, tools and policies, so a failure keeps its context.</p></div>
            <Constellation />
          </div>
        </section>

        <section className="scene scene-failure" id="failure" data-scene="failure" data-span="scene-failure">
          <SceneIndex code="E-02" label="FAILURE" />
          <div className="scene-inner split-scene" data-fit>
            <div className="failure-copy">
              <p className="kicker failure-kicker">Hard cut / responsible event</p>
              <h2>It did exactly what it was allowed to do.</h2>
              <p>The policy guard recorded <code>approval_state=pending</code>. The booking agent still called the reservation tool.</p>
              <div className="failure-tag" data-span="incident-tag"><span>POL-014</span><small>HIGH SEVERITY</small></div>
            </div>
            <EventRail highlight="booking-agent" />
          </div>
          <div className="scene-foot"><span>THE BREAK IS NOT THE WHOLE STORY</span><span>02 / 05</span></div>
        </section>

        <section className="scene scene-investigate" id="investigate" data-scene="investigate" data-span="scene-investigate">
          <SceneIndex code="E-03" label="INVESTIGATE" />
          <div className="scene-inner report-wrap" data-fit>
            <article className="incident-report" data-span="incident-report">
              <header className="report-header"><div><p className="report-kicker">SpanTrace / incident report</p><h2>POL-014</h2></div><span className="report-stamp">INCIDENT<br />OPENED</span></header>
              <div className="report-meta"><span><b>severity</b> high</span><span><b>trace</b> trace_7bd2</span><span><b>test case</b> travel-approval-01</span></div>
              <div className="report-grid">
                <div><p className="report-label">responsible event</p><p className="report-value"><strong>booking_agent</strong><br />create_reservation<br /><code>09:41:04.018</code></p></div>
                <div><p className="report-label">cause</p><p className="report-value">reservation created while <code>approval_state=pending</code></p></div>
              </div>
              <div className="report-path"><p className="report-label">observed path</p><p>planner <span>›</span> hotel_search <span>›</span> policy_guard <span>›</span> booking_agent</p></div>
              <div className="payload-block"><p className="report-label">captured payload / illustrative trace data</p><pre>{`approval_state: "pending"\napproval_required: true\nhotel: { name: "Palm Grove", nightly_price_inr: 4200 }\nreservation: { created: true, reservation_id: "MOCK-1" }`}</pre></div>
              <footer className="report-footer"><span>evidence over guesswork</span><span>source: trace_7bd2</span></footer>
            </article>
          </div>
          <div className="scene-foot"><span>SELECTABLE EVIDENCE / NO BLACK BOX</span><span>03 / 05</span></div>
        </section>

        <section className="paper-band logs-band" id="logs" data-scene="logs" data-span="scene-logs">
          <div className="paper-band-index"><span>02 / EVIDENCE</span><span>LOG → TRACE</span></div>
          <div className="paper-band-inner logs-inner" data-fit>
            <div className="paper-copy">
              <p className="paper-kicker">The shape of a cause</p>
              <h2>Logs tell you it happened. <em>Traces tell you why.</em></h2>
              <p>One column of captured events becomes a path you can inspect, replay, and test. The failing line is not a guess; it is the evidence.</p>
              <div className="loop-summary"><p className="paper-kicker">Built to close the loop</p><p className="loop-summary-copy">Trace it. Find the cause. Turn it into a test. Verify the fix.</p></div>
            </div>
            <div className="evidence-stack">
              <LogReplay />
              <div className="loop-list">{loopRows.map(([number, title, copy, preview]) => <div className="loop-row" data-span={`loop-${number}`} key={number}><span className="loop-number">{number}</span><div><h3>{title}</h3><p>{copy}</p></div><code>{preview}</code></div>)}</div>
            </div>
          </div>
        </section>

        <section className="scene scene-reproduce" id="reproduce" data-scene="reproduce" data-span="scene-reproduce">
          <SceneIndex code="E-04" label="REPRODUCE" />
          <div className="scene-inner split-scene reproduce-inner" data-fit>
            <div>
              <p className="kicker">Turn the cause into a boundary</p>
              <h2>Make the failure impossible to forget.</h2>
              <p>SpanTrace turns the exact incident into a deterministic regression case. The replay rewinds, then pins the rule that was missing.</p>
            </div>
            <div className="test-card" data-span="regression-case">
              <div className="test-card-top"><span>REGRESSION CASE</span><code>travel-approval-01</code></div>
              <pre className="test-code"><code>
                <span className="code-line code-dim">case travel-approval-01</span>
                <span className="code-line">input trace_7bd2</span>
                <span className="code-line code-gap" />
                <span className="code-line test-code-accent">assert approval_state == &quot;approved&quot;</span>
                <span className="code-line">assert reservation_created == false</span>
              </code></pre>
              <div className="test-details"><span>input</span><code>trace_7bd2</code><span>expected</span><strong>no reservation side effect</strong></div>
              <div className="rewind-mark"><b className="rewind-glyph" aria-hidden="true">↶</b> <span>replay from 09:41:03.104</span></div>
            </div>
          </div>
          <div className="scene-foot"><span>THE INCIDENT IS NOW A TEST</span><span>04 / 05</span></div>
        </section>

        <section className="scene scene-verify" id="verify" data-scene="verify" data-span="scene-verify">
          <SceneIndex code="E-05" label="VERIFY" />
          <div className="scene-inner split-scene verify-inner" data-fit>
            <div className="verify-copy">
              <p className="kicker verify-kicker">Re-run / corrected path</p>
              <h2>The trace ends where confidence begins.</h2>
              <p>Approval is checked before booking. The same path replays with the fix, and the regression runner confirms the invariant.</p>
              <div className="verify-result"><span className="checkmark">✓</span><div><strong>passed in 412ms</strong><span>no side effect · approval invariant</span></div></div>
            </div>
            <div className="verify-model"><TraceModel variant="verify" /><p className="verify-time">09:41:04.430 / regression_runner / passed</p></div>
          </div>
          <div className="scene-foot"><span>VERIFIED STATE</span><span>05 / 05</span></div>
        </section>
      </main>

      <section className="cta-band" id="sdk" data-span="sdk-cta">
        <div data-reveal><p className="kicker">Bring your own failure</p><h2>Replay your own failure.</h2><p>Instrument one workflow, then follow the evidence from event to verified fix.</p></div>
        <a className="button button-paper" href="#sdk-code" data-reveal>Read the SDK guide <span>↗</span></a>
      </section>
      <section className="sdk-section" id="sdk-code" aria-labelledby="sdk-title">
        <div data-reveal><p className="kicker">SDK / Python</p><h2 id="sdk-title">One trace. Every handoff.</h2><p>Use the same public SDK path to capture spans, tool calls, payloads, and handoffs.</p></div>
        <pre className="sdk-code" data-span="sdk-code" data-reveal><code><span className="code-key">from</span> spantrace <span className="code-key">import</span> SpanTrace{`\n\n`}scope = SpanTrace.from_env(){`\n`}provider, adapter = scope.instrument_opentelemetry({`\n`}    service_name=<span className="code-string">&quot;my-workflow&quot;</span>, framework=<span className="code-string">&quot;my-framework&quot;</span>{`\n`}){`\n`}tracer = provider.get_tracer(<span className="code-string">&quot;my-app&quot;</span>){`\n`}<span className="code-key">with</span> tracer.start_as_current_span(<span className="code-string">&quot;planner&quot;</span>):{`\n`}    run_planner()<span className="code-caret" aria-hidden="true" /></code></pre>
        <div className="sdk-closing" data-reveal><p className="kicker">Final handoff</p><h2>Make every failure <em>explain itself.</em></h2><a className="text-link" href="#trace">Start at the first event <span>↗</span></a></div>
      </section>
      <MarketingFooter backHref="#trace" />
    </div>
  );
}
