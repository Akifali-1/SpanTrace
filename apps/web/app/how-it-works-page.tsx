"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useRef } from "react";
import { MarketingFooter, MarketingHeader } from "./marketing-chrome";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const stages = [
  ["01", "Connect your repository", "Import source and map the workflow without running it."],
  ["02", "Understand the architecture", "See discovered agents, tools, entry points, and evidence."],
  ["03", "Run in control", "Launch a supported workflow through an isolated worker."],
  ["04", "Inspect the execution", "Follow runtime activity as a trace and execution graph."],
  ["05", "Diagnose the failure", "Separate observed evidence from likely causes."],
  ["06", "Reproduce the bug", "Turn the incident into a reviewable regression test."],
  ["07", "Verify the fix", "Run checks and the workflow again before applying a patch."],
] as const;

function WorkflowOverview() {
  return (
    <section className="how-overview" id="workflow" aria-labelledby="workflow-title">
      <div className="how-section-index"><span>00 / METHOD</span><span>SEVEN STAGES</span></div>
      <div className="how-wide how-overview-head" data-how-reveal>
        <div><p className="kicker">The complete workflow</p><h2 id="workflow-title">From source map to <em>verified change.</em></h2></div>
        <p>SpanTrace keeps repository understanding, controlled execution, runtime evidence, diagnosis, and verification connected without pretending they are the same thing.</p>
      </div>
      <nav className="how-stage-list" aria-label="How SpanTrace works">
        {stages.map(([number, title, copy], index) => (
          <a className="how-stage-link" href={`#stage-${String(index + 1).padStart(2, "0")}`} key={number} data-how-reveal>
            <span className="how-stage-number">{number}</span><span><strong>{title}</strong><small>{copy}</small></span><span className="how-stage-arrow" aria-hidden="true">↘</span>
          </a>
        ))}
      </nav>
    </section>
  );
}

function RepositoryMap() {
  return (
    <div className="how-visual how-repository-map" aria-label="Illustrative static repository analysis diagram" data-how-reveal>
      <div className="how-repo-source">
        <span className="how-visual-label">INPUT</span>
        <strong>repository.zip</strong>
        <code>src/ · tests/ · README</code>
        <span className="how-repo-status">not executed</span>
      </div>
      <div className="how-map-arrow" aria-hidden="true"><span>static analysis</span><b>→</b></div>
      <div className="how-repo-output">
        <span className="how-visual-label">SOURCE MAP</span>
        <div className="how-repo-output-row"><span className="how-map-dot" /> entry point <code>main.py</code></div>
        <div className="how-repo-output-row"><span className="how-map-dot" /> agents <code>3 found</code></div>
        <div className="how-repo-output-row"><span className="how-map-dot" /> tool calls <code>5 references</code></div>
        <div className="how-repo-output-row"><span className="how-map-dot" /> evidence <code>12 links</code></div>
      </div>
      <span className="data-label">illustrative repository analysis / static stage</span>
    </div>
  );
}

function ArchitectureMap() {
  return (
    <div className="how-visual how-architecture-map" aria-label="Illustrative agent architecture map" data-how-reveal>
      <svg viewBox="0 0 620 310" role="img" aria-labelledby="architecture-title architecture-desc">
        <title id="architecture-title">Discovered workflow relationships</title>
        <desc id="architecture-desc">An entry point connects to planner, retrieval, model, and tool nodes with source evidence labels.</desc>
        <g className="how-map-lines" aria-hidden="true">
          <line x1="95" y1="160" x2="220" y2="82" /><line x1="95" y1="160" x2="220" y2="238" /><line x1="220" y1="82" x2="370" y2="82" /><line x1="220" y1="238" x2="370" y2="238" /><line x1="370" y1="82" x2="515" y2="160" /><line x1="370" y1="238" x2="515" y2="160" />
        </g>
        <g className="how-map-node how-map-node-root"><circle cx="95" cy="160" r="28" /><text x="95" y="157" textAnchor="middle">entry</text><text x="95" y="171" textAnchor="middle">main.py</text></g>
        <g className="how-map-node"><circle cx="220" cy="82" r="24" /><text x="220" y="80" textAnchor="middle">planner</text><text x="220" y="94" textAnchor="middle">L42</text></g>
        <g className="how-map-node"><circle cx="220" cy="238" r="24" /><text x="220" y="236" textAnchor="middle">retrieval</text><text x="220" y="250" textAnchor="middle">L67</text></g>
        <g className="how-map-node"><circle cx="370" cy="82" r="24" /><text x="370" y="80" textAnchor="middle">model</text><text x="370" y="94" textAnchor="middle">L51</text></g>
        <g className="how-map-node"><circle cx="370" cy="238" r="24" /><text x="370" y="236" textAnchor="middle">tool</text><text x="370" y="250" textAnchor="middle">L88</text></g>
        <g className="how-map-node how-map-node-accent"><circle cx="515" cy="160" r="28" /><text x="515" y="157" textAnchor="middle">output</text><text x="515" y="171" textAnchor="middle">handoff</text></g>
      </svg>
      <div className="how-map-caption"><span>source evidence</span><code>file · line · symbol</code><span className="how-map-caveat">relationships shown when supported by analysis</span></div>
      <span className="data-label">illustrative architecture map / source-backed relationships</span>
    </div>
  );
}

function ExecutionStatus() {
  return (
    <div className="how-visual how-execution-status" aria-label="Illustrative controlled execution status" data-how-reveal>
      <div className="how-worker-head"><span className="how-visual-label">CONTROLLED EXECUTION</span><code>trace_7bd2</code></div>
      <div className="how-status-track"><span className="how-status-line" /><span className="how-status-step is-done"><b>✓</b><strong>queued</strong><small>accepted</small></span><span className="how-status-step is-done"><b>✓</b><strong>running</strong><small>worker active</small></span><span className="how-status-step is-failed"><b>!</b><strong>failed</strong><small>trace retained</small></span></div>
      <div className="how-worker-footer"><span>Docker worker / resource limits applied</span><span>outbound telemetry retained</span></div>
      <span className="data-label">illustrative status transition / execution is separate from static analysis</span>
    </div>
  );
}

const graphNodes = [
  ["entry", "workflow", 8, 50, "ok"],
  ["planner", "planner", 25, 27, "ok"],
  ["search", "hotel_search", 43, 51, "ok"],
  ["policy", "policy_guard", 61, 28, "pending"],
  ["booking", "booking_agent", 77, 53, "failed"],
  ["tool", "reservation_tool", 92, 30, "failed"],
] as const;

function ExecutionGraph() {
  return (
    <div className="how-visual how-execution-graph" aria-label="Illustrative execution graph with a failed booking operation" data-how-reveal>
      <div className="how-graph-canvas">
        <svg viewBox="0 0 100 80" aria-hidden="true" preserveAspectRatio="none">
          <line x1="8" y1="50" x2="25" y2="27" /><line x1="25" y1="27" x2="43" y2="51" /><line x1="43" y1="51" x2="61" y2="28" /><line className="is-failure" x1="61" y1="28" x2="77" y2="53" /><line className="is-failure" x1="77" y1="53" x2="92" y2="30" />
        </svg>
        {graphNodes.map(([id, label, x, y, tone]) => <span className={`how-graph-node how-graph-node-${tone}`} style={{ left: `${x}%`, top: `${y}%` }} key={id}><i />{label}</span>)}
        <span className="how-graph-time">09:41:04.018</span>
      </div>
      <aside className="how-event-inspector"><span className="how-visual-label">SELECTED EVENT</span><strong>booking_agent</strong><code>create_reservation</code><div className="how-inspector-row"><span>status</span><b className="how-red-text">failed</b></div><div className="how-inspector-row"><span>duration</span><b>42ms</b></div><div className="how-inspector-row"><span>trace</span><b>trace_7bd2</b></div><p>approval_state=pending</p></aside>
      <span className="data-label">illustrative runtime trace / captured relationships only</span>
    </div>
  );
}

function EvidenceDiagnosis() {
  return (
    <div className="how-visual how-diagnosis" aria-label="Illustrative evidence-backed diagnosis" data-how-reveal>
      <div className="how-diagnosis-event"><span className="how-visual-label">OBSERVED EVENT</span><strong>booking_agent</strong><code>create_reservation</code><span className="how-failure-pill">POL-014</span></div>
      <div className="how-diagnosis-connector" aria-hidden="true">→</div>
      <div className="how-source-evidence"><span className="how-visual-label">SOURCE EVIDENCE</span><pre><code><span className="how-code-muted"># agents/booking.py:88</span>{`\n`}if approval_state == <span className="how-code-string">"pending"</span>:{`\n`}    create_reservation()</code></pre><span className="how-hypothesis">likely cause / missing guard before side effect</span></div>
      <div className="how-evidence-key"><span><i className="how-key-observed" /> observed</span><span><i className="how-key-hypothesis" /> hypothesis to review</span></div>
      <span className="data-label">illustrative diagnosis / evidence and hypothesis remain distinct</span>
    </div>
  );
}

function RegressionTest() {
  return (
    <div className="how-visual how-regression" aria-label="Illustrative regression test generated from a failure" data-how-reveal>
      <div className="how-regression-failure"><span className="how-visual-label">ORIGINAL TRACE</span><strong>reservation_created = true</strong><small>approval_state = pending</small><b>failed</b></div>
      <div className="how-regression-arrow" aria-hidden="true">→</div>
      <pre className="how-regression-code"><span className="how-visual-label">REGRESSION CASE</span><code><span>case travel-approval-01</span>{`\n`}input trace_7bd2{`\n\n`}<mark>assert reservation_created == false</mark>{`\n`}assert approval_state == <i>"approved"</i></code></pre>
      <div className="how-regression-result"><span>reproduction</span><strong>reviewable test</strong><small>may be inconclusive when inputs or environment cannot be recovered</small></div>
      <span className="data-label">illustrative regression generation / expected behavior must be reviewed</span>
    </div>
  );
}

function VerificationFlow() {
  return (
    <div className="how-visual how-verification" aria-label="Illustrative before and after fix verification" data-how-reveal>
      <div className="how-verify-column how-verify-before"><span className="how-visual-label">BEFORE</span><strong>booking_agent</strong><code>approval_state=pending</code><span className="how-verify-result is-failed">✕ side effect created</span></div>
      <div className="how-verify-patch"><span>reviewable patch</span><pre><code><span className="how-code-muted">+ if approval_state != "approved":</span>{`\n`}<span className="how-code-string">+     return blocked</span></code></pre><small>human review before application</small></div>
      <div className="how-verify-column how-verify-after"><span className="how-visual-label">AFTER / ILLUSTRATIVE</span><strong>regression_runner</strong><code>travel-approval-01</code><span className="how-verify-result is-passed">✓ checks passed</span></div>
      <div className="how-verify-footer"><span>existing checks</span><span>regression test</span><span>supported workflow rerun</span><b>→ confidence</b></div>
      <span className="data-label">illustrative verification path / a patch is not verified until required checks pass</span>
    </div>
  );
}

function Stage({ number, title, eyebrow, copy, visual, tone = "dark" }: { number: string; title: string; eyebrow: string; copy: React.ReactNode; visual: React.ReactNode; tone?: "dark" | "paper" }) {
  return (
    <section className={`how-stage how-stage-${tone}`} id={`stage-${number}`} aria-labelledby={`stage-${number}-title`}>
      <div className="how-section-index"><span>{number} / 07</span><span>WORKFLOW</span></div>
      <div className="how-wide how-stage-grid">
        <div className="how-stage-copy" data-how-reveal><p className="kicker">{eyebrow}</p><h2 id={`stage-${number}-title`}>{title}</h2><div className="how-stage-prose">{copy}</div></div>
        {visual}
      </div>
    </section>
  );
}

export default function HowItWorksPage() {
  const root = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    const mm = gsap.matchMedia();
    mm.add({ motion: "(prefers-reduced-motion: no-preference)", reduced: "(prefers-reduced-motion: reduce)" }, (context) => {
      const conditions = context.conditions as { motion?: boolean; reduced?: boolean };
      if (conditions.reduced) {
        gsap.set("[data-how-reveal]", { opacity: 1, y: 0 });
        return;
      }
      gsap.utils.toArray<HTMLElement>("[data-how-reveal]").forEach((node, index) => {
        gsap.fromTo(node, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: .65, delay: Math.min(index % 3, 2) * .06, ease: "power3.out", scrollTrigger: { trigger: node, start: "top 88%", once: true } });
      });
      gsap.fromTo(".how-hero-proof", { opacity: 0, x: 28 }, { opacity: 1, x: 0, duration: .9, delay: .25, ease: "power3.out" });
    }, root);
    return () => mm.revert();
  }, { scope: root, dependencies: [] });

  return (
    <div className="landing-page how-page" ref={root}>
      <a className="skip-link" href="#how-main">Skip to workflow</a>
      <MarketingHeader current="how-it-works" />
      <main id="how-main">
        <section className="how-hero">
          <div className="how-wide how-hero-grid">
            <div className="how-hero-copy" data-how-reveal><p className="kicker">HOW IT WORKS / EVIDENCE → FIX</p><h1>From agent failure <em>to verified fix.</em></h1><p className="how-hero-lede">SpanTrace helps developers understand multi-agent execution, locate a failure using trace and source evidence, reproduce the bug, and verify a proposed fix before it reaches the original repository.</p><div className="hero-actions"><a className="button button-solid" href="#workflow">Explore the workflow <span>↓</span></a><a className="button button-line" href="/v1">Open the dashboard <span>↗</span></a></div><p className="microcopy">Seven stages. One evidence trail. No black-box certainty claims.</p></div>
            <div className="how-hero-proof" aria-label="Illustrative workflow outcome"><div className="how-proof-head"><span className="how-visual-label">OUTCOME</span><code>trace_7bd2 / POL-014</code></div><div className="how-proof-path"><span>failure</span><i>→</i><span>evidence</span><i>→</i><span>test</span><i>→</i><strong>verified</strong></div><div className="how-proof-rule" /><div className="how-proof-row"><span>observed</span><code>booking_agent → tool</code></div><div className="how-proof-row"><span>reproduced</span><code>travel-approval-01</code></div><div className="how-proof-row"><span>reviewed</span><code>human approval required</code></div><div className="how-proof-result"><b>✓</b><span><strong>confidence, with evidence</strong><small>illustrative product workflow</small></span></div></div>
          </div>
          <div className="how-hero-foot"><span>SCROLL TO FOLLOW THE METHOD</span><span>SPANTRACE / HOW IT WORKS</span></div>
        </section>

        <WorkflowOverview />

        <Stage number="01" eyebrow="Connect / static first" title="Start with the repository, not a runtime guess." copy={<><p>Import a supported public GitHub repository or upload a ZIP archive. SpanTrace analyzes the source statically to discover relevant entry points, agents, tools, model calls, workflow structure, and source evidence.</p><p className="how-note"><b>Important boundary</b> Repository analysis does not execute the project. It maps what the source supports before a controlled run begins.</p></>} visual={<RepositoryMap />} />

        <Stage number="02" eyebrow="Architecture / source evidence" title="See how the workflow is put together." copy={<><p>The analysis presents discovered agents, tools, entry points, and relationships that the source supports. Selectable evidence points back to files, lines, and symbols so you can see where an assumption came from.</p><p className="how-note">The map also shows where instrumentation or configuration may be needed. Discovery is evidence-backed, not a promise that every framework relationship is visible.</p></>} visual={<ArchitectureMap />} tone="paper" />

        <Stage number="03" eyebrow="Execute / controlled environment" title="Run the supported path with its context attached." copy={<><p>When a workflow is ready, the controlled execution system launches it through an isolated Docker worker with resource limits, status tracking, and an associated trace.</p><p className="how-note"><b>Accurate by design</b> The worker keeps outbound connectivity available for telemetry. Isolation and limits make the run inspectable; they do not imply that the process has no network access.</p></>} visual={<ExecutionStatus />} />

        <Stage number="04" eyebrow="Inspect / runtime evidence" title="Follow the operation that changed the outcome." copy={<><p>Captured activity becomes a trace and execution-flow view: entry point, agent and tool operations, relationships supported by telemetry, timing, identifiers, status, and error evidence.</p><p className="how-note">Select an event to inspect what was captured. Unseen operations stay unseen; the graph does not invent certainty where telemetry is missing.</p></>} visual={<ExecutionGraph />} tone="paper" />

        <Stage number="05" eyebrow="Diagnose / evidence over guesswork" title="Connect the failed node to a likely cause." copy={<><p>SpanTrace correlates runtime evidence with repository source evidence to propose likely root-cause candidates. The useful distinction is visible: what the trace observed, and what the source suggests you should review next.</p><p className="how-note"><b>Observed</b> is not the same as <b>proven</b>. A candidate cause still needs developer judgment and a reproducible check.</p></>} visual={<EvidenceDiagnosis />} />

        <Stage number="06" eyebrow="Reproduce / regression boundary" title="Turn the incident into expected behavior." copy={<><p>Use the available execution context to attempt reproduction and generate a reviewable regression test. The original trace supplies the input and the failed invariant becomes an explicit expectation.</p><p className="how-note">Reproduction can be inconclusive when required inputs, external systems, or environmental conditions cannot be recovered. The page should make that uncertainty visible.</p></>} visual={<RegressionTest />} tone="paper" />

        <Stage number="07" eyebrow="Verify / reviewable change" title="Only call it fixed after the checks pass." copy={<><p>SpanTrace can propose a reviewable patch, test it in an isolated workspace, run the regression and relevant existing checks, and rerun the supported workflow when appropriate.</p><p className="how-note"><b>Human review stays in the loop.</b> A generated patch is not verified until the required checks pass, and it is not applied to the original repository without approval.</p></>} visual={<VerificationFlow />} />

        <section className="how-cta" data-how-reveal><div><p className="kicker">Make the loop visible</p><h2>Make every failure <em>explain itself.</em></h2><p>Understand the execution, investigate the evidence, reproduce the problem, and verify the fix with a trail you can review.</p></div><a className="button button-paper" href="/v1">Open the dashboard <span>↗</span></a></section>
      </main>
      <MarketingFooter />
    </div>
  );
}
