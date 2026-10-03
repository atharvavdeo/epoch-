import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, fmt, type Issue, type Prediction, type Scenario } from "../api";
import { AtThisMoment } from "../components/AtThisMoment";
import { RetentionChart, RiskChart } from "../components/Charts";
import { ChatPanel } from "../components/Chat";
import { Dock } from "../components/Dock";
import { Drawer } from "../components/Drawer";
import { FindingDetail, FindingsList, prioritise } from "../components/Issues";
import { Player } from "../components/Player";
import { PredictionView } from "../components/Prediction";
import { RelationsView } from "../components/Relations";
import { ShotsView } from "../components/Shots";
import { issueLabel, Timeline } from "../components/Timeline";
import { TranscriptPanel } from "../components/TranscriptPanel";
import { usePlayhead } from "../store";

function download(name: string, body: string, type: string) {
  const url = URL.createObjectURL(new Blob([body], { type }));
  Object.assign(document.createElement("a"), { href: url, download: name }).click();
  URL.revokeObjectURL(url);
}

type Panel = { kind: "finding"; id: string } | { kind: "all" } | { kind: "chat" } | null;
type Lower = "retention" | "transcript" | "relations" | "shots" | "method";
const s2 = (ms: number) => fmt(ms).replace(/\.\d$/, "");

function PriorityCard({ issue, onOpen }: { issue: Issue; onOpen: () => void }) {
  const { focus, selectedIssue } = usePlayhead();
  const sel = selectedIssue === issue.issue_id;
  return (
    <div className={`pcard ${sel ? "selected" : ""}`}>
      <div className="pcard-top">
        <span className={`sevtag ${issue.severity}`}><span className={`sevdot ${issue.severity}`} aria-hidden />{issue.severity}</span>
        <button className="time" onClick={() => focus(issue.affected_interval, issue.issue_id)}>{s2(issue.affected_interval.start_ms)}</button>
      </div>
      <h4>{issueLabel(issue.type)}</h4>
      <p className="muted pcard-text">{issue.explanation}</p>
      <div className="pcard-actions">
        <button onClick={onOpen}>View evidence</button>
        {issue.review_status !== "open" && <span className="pill">{issue.review_status === "accepted" ? "in edit plan" : "dismissed"}</span>}
      </div>
    </div>
  );
}

export default function Review() {
  const { runId = "" } = useParams();
  const nav = useNavigate();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId) });
  const tl = useQuery({ queryKey: ["timeline", runId], queryFn: () => api.timeline(runId) });
  const tr = useQuery({ queryKey: ["transcript", runId], queryFn: () => api.transcript(runId) });
  const issues = useQuery({ queryKey: ["issues", runId], queryFn: () => api.issues(runId) });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const predQ = useQuery({ queryKey: ["prediction", runId], queryFn: () => api.prediction(runId), retry: false });
  const relQ = useQuery({ queryKey: ["relations", runId], queryFn: () => api.relations(runId) });
  const [userPred, setUserPred] = useState<Prediction | null>(null);
  const [userScenario, setUserScenario] = useState<Scenario | null>(null);
  const [panel, setPanel] = useState<Panel>(null);   // evidence / all findings / assistant: one at a time, closed by default
  const [lower, setLower] = useState<Lower>("retention");
  const { focus, selectedIssue } = usePlayhead();
  const items = issues.data?.items ?? [];
  const close = useCallback(() => setPanel(null), []);

  // land on the highest-priority supported finding's moment (the drawer stays closed)
  useEffect(() => {
    if (!items.length || selectedIssue && items.some((i) => i.issue_id === selectedIssue)) return;
    const top = prioritise(items).find((i) => i.evidence_status === "supported") ?? prioritise(items)[0];
    focus(top.affected_interval, top.issue_id);
  }, [items, selectedIssue, focus]);

  if (run.isLoading) return <div className="shell muted">Loading run…</div>;
  if (run.error || !run.data) return <div className="shell err">Run not found. <Link to="/">Back to projects</Link></div>;
  const r = run.data;
  const duration = r.asset.duration_ms;
  const title = r.project?.title ?? r.asset.original_name;
  const segments = tr.data?.segments ?? [];
  const scenario = userScenario ?? tl.data?.scenarios[0];
  const scenarioAck = !!userScenario || !!scenario?.assumptions.acknowledged;
  const promises = tl.data?.promises ?? [];
  const runs = projects.data?.items.find((p) => p.project_id === r.project?.project_id)?.runs ?? [];
  const visualPending = "visual" in r.missing_stages;
  const pred = userPred ?? predQ.data ?? undefined;
  const ranked = prioritise(items).filter((i) => i.review_status !== "dismissed");
  const top3 = ranked.slice(0, 3);
  const openFinding = (id: string) => {
    const i = items.find((x) => x.issue_id === id);
    if (i) focus(i.affected_interval, i.issue_id);
    setPanel({ kind: "finding", id });
  };
  const drawerIssue = panel?.kind === "finding" ? items.find((i) => i.issue_id === panel.id) : undefined;

  const exportFindings = () => download(`findings-${runId.slice(0, 8)}.csv`, ["type,severity,evidence,status,start,end,explanation",
    ...prioritise(items).map((i) => [i.type, i.severity, i.evidence_status, i.review_status, fmt(i.affected_interval.start_ms),
      fmt(i.affected_interval.end_ms), i.explanation].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","))].join("\n"), "text/csv");

  return (
    <div className="shell review">
      <div className="header">
        <Link to="/"><button className="ghost back" aria-label="Back to projects" title="Back to projects">‹</button></Link>
        <div className="title">
          <h1>{title}</h1>
          <div className="sub">{r.project?.category ?? ""} · {s2(duration)} ·{" "}
            <select aria-label="Run" className="bare" value={runId} onChange={(e) => nav(`/runs/${e.target.value}`)}>
              {(runs.length ? runs : [{ run_id: runId, created_at: r.run.created_at, package_kind: r.package_kind, status: "" }]).map((x) => (
                <option key={x.run_id} value={x.run_id}>run {x.run_id.slice(0, 8)} · {x.created_at.slice(0, 16).replace("T", " ")}</option>))}
            </select>
            {" · "}<span className={visualPending ? "warn-text" : ""}>{r.package_kind === "analysis" ? "complete analysis" : visualPending ? "visuals not inspected" : "partial analysis"}</span>
          </div>
        </div>
        <div className="right">
          <button onClick={() => setPanel(panel?.kind === "chat" ? null : { kind: "chat" })} aria-pressed={panel?.kind === "chat"}>Ask about this video</button>
          <Link to={`/runs/${runId}/plan`}><button className="hero">Open edit plan</button></Link>
        </div>
      </div>

      <div className="summary three">
        {pred && <span className="item"><b>{pred.summary.apv_pct.central.toFixed(0)}%</b> estimated viewed <span className="faint">(uncalibrated)</span></span>}
        <span className="item"><b>{ranked.filter((i) => i.severity !== "low").length}</b> findings to look at first</span>
        <span className="item">title payoff starts <b>{(() => {
          const p = promises.map((x) => (x.partial_interval ?? x.fulfilled_interval)?.start_ms).filter((v): v is number => v !== undefined).sort((a, b) => a - b)[0];
          return p !== undefined ? s2(p) : "not found";
        })()}</b></span>
      </div>

      <div className="ws2">
        <div className="card video-card"><Player src={r.proxy_artifact_id ? api.artifactUrl(runId, r.proxy_artifact_id) : null} /></div>
        <div className="card"><AtThisMoment segments={segments} chapters={tl.data?.chapters ?? []} issues={items} pred={pred} rel={relQ.data}
          onOpenFinding={openFinding} onAsk={() => setPanel({ kind: "chat" })} /></div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <Timeline duration={duration} chapters={tl.data?.chapters ?? []} issues={items} risk={tl.data?.risk ?? []}
          scenario={scenario} scenarioAck={scenarioAck} shots={tl.data?.shots ?? []} segments={segments} coverage={tl.data?.coverage ?? []}
          pred={pred} />
      </div>

      <div className="section-title" style={{ marginTop: 28 }}>
        <h2>Look at these first</h2>
        <span className="sub">ranked by severity, then evidence</span>
        <button className="quiet" style={{ marginLeft: "auto" }} onClick={() => setPanel({ kind: "all" })}>See all {items.length} findings ›</button>
      </div>
      {issues.isLoading ? <p className="muted">Loading findings…</p> : top3.length ? (
        <div className="pcards">{top3.map((i) => <PriorityCard key={i.issue_id} issue={i} onOpen={() => openFinding(i.issue_id)} />)}</div>
      ) : <p className="muted">No open findings. That is not proof the video is flawless: check “Method and data” for what was inspected.</p>}

      <div className="card" style={{ marginTop: 28 }}>
        <div className="tabs">
          {([["retention", "Retention"], ["transcript", "Transcript"], ["relations", "Transcript relations"], ["shots", "Shots"], ["method", "Method and data"]] as const).map(([k, l]) => (
            <button key={k} className={lower === k ? "on" : ""} aria-selected={lower === k} role="tab" onClick={() => setLower(k)}>{l}</button>))}
        </div>
        {lower === "retention" && (pred ? <PredictionView runId={runId} pred={pred} onPred={setUserPred} />
          : <p className="muted">{predQ.isLoading ? "Loading prediction…" : "This package was built before the text retention model. Re-run finish and import the new package."}</p>)}
        {lower === "transcript" && <div className="transcript-wide">
          <div className="row" style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginBottom: 8 }}>
            <span className="faint" style={{ marginRight: "auto", fontSize: 13 }}>Click any word to jump there. Download:</span>
            {(["srt", "vtt", "txt"] as const).map((f) => <a key={f} href={api.transcriptUrl(runId, f)}><button className="quiet">{f.toUpperCase()}</button></a>)}
          </div>
          <TranscriptPanel segments={segments} words={tr.data?.words ?? []} issues={items}
            spans={tl.data?.structure_spans ?? []} markers={tl.data?.markers ?? []} promises={promises} />
        </div>}
        {lower === "relations" && (relQ.data ? <RelationsView rel={relQ.data} /> : <p className="muted">{relQ.error ? (relQ.error as Error).message : "Measuring the transcript…"}</p>)}
        {lower === "shots" && <ShotsView runId={runId} issues={items} segments={segments} visualPending={visualPending} />}
        {lower === "method" && <div className="method-tab">
          <h3>What was analysed</h3>
          <div className="kv">
            <span className="muted">Not analysed</span>
            <span>{Object.entries(r.missing_stages).map(([k, v]) => `${k} — ${v}`).join(" · ") || "nothing missing"}</span>
            <span className="muted">Coverage</span>
            <span>speech {Math.round(r.coverage.filter((c) => c.modality === "speech" && c.status === "observed").reduce((t, c) => t + c.interval.end_ms - c.interval.start_ms, 0) / duration * 100)}%
              {" · "}visuals {visualPending ? "not inspected" : "see shots"} · on-screen text not inspected</span>
            <span className="muted">Run</span><span>{r.run.status} ({r.package_kind}) · <span className="mono">{r.run.created_at}</span></span>
            {Object.entries(r.run.provenance).filter(([k]) => ["code_revision", "precision", "scoring_version", "external_service_model"].includes(k))
              .map(([k, v]) => [<span key={k} className="muted">{k.replace(/_/g, " ")}</span>,
                <span key={k + "v"} className="mono">{typeof v === "string" ? v : JSON.stringify(v)}</span>])}
            <span className="muted">Models</span>
            <span className="mono">{(r.run.provenance.models as { role: string; model_id: string; revision: string }[])
              .map((m) => `${m.role}: ${m.model_id}@${m.revision.slice(0, 8)}`).join(" · ")}</span>
            <span className="muted">Stages</span><span>{r.run.stages.map((s) => `${s.name}: ${s.status}`).join(" · ")}</span>
          </div>
          <div className="row" style={{ display: "flex", gap: 8, margin: "12px 0 24px" }}>
            <button onClick={exportFindings}>Export findings (CSV)</button>
          </div>
          <h3>Risk by track <span className="faint" style={{ fontSize: 13, fontWeight: 400 }}>heuristic 0–100; hatched = not inspected</span></h3>
          {tl.data && <RiskChart bins={tl.data.risk} duration={duration} chapters={tl.data.chapters} />}
          <h3 style={{ marginTop: 24 }}>Findings-based scenario <span className="faint" style={{ fontSize: 13, fontWeight: 400 }}>older assumption-driven curve, kept for comparison</span></h3>
          <RetentionChart runId={runId} scenario={scenario} duration={duration} ack={!!userScenario} onScenario={setUserScenario} />
        </div>}
      </div>

      {panel?.kind === "finding" && <Drawer title={drawerIssue ? issueLabel(drawerIssue.type) : "Finding"} kicker="EVIDENCE" onClose={close} wide>
        <FindingDetail runId={runId} issue={drawerIssue} segments={segments} risk={tl.data?.risk ?? []} />
      </Drawer>}
      {panel?.kind === "all" && <Drawer title={`All findings (${items.length})`} kicker="FINDINGS" onClose={close}>
        <FindingsList issues={items} />
        {selectedIssue && <div style={{ marginTop: 12 }}><button onClick={() => setPanel({ kind: "finding", id: selectedIssue })}>View evidence for the selected finding ›</button></div>}
      </Drawer>}
      {panel?.kind === "chat" && <ChatPanel runId={runId} onClose={close} />}
      <Dock active="review" runId={runId} />
    </div>
  );
}
