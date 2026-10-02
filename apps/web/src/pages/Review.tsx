import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, fmt, type Scenario } from "../api";
import { RetentionChart, RiskChart } from "../components/Charts";
import { Dock } from "../components/Dock";
import { FindingDetail, FindingsList, prioritise } from "../components/Issues";
import { Player } from "../components/Player";
import { ShotsView } from "../components/Shots";
import { Timeline } from "../components/Timeline";
import { TranscriptPanel } from "../components/TranscriptPanel";
import { usePlayhead } from "../store";

function download(name: string, body: string, type: string) {
  const url = URL.createObjectURL(new Blob([body], { type }));
  Object.assign(document.createElement("a"), { href: url, download: name }).click();
  URL.revokeObjectURL(url);
}

export default function Review() {
  const { runId = "" } = useParams();
  const nav = useNavigate();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId) });
  const tl = useQuery({ queryKey: ["timeline", runId], queryFn: () => api.timeline(runId) });
  const tr = useQuery({ queryKey: ["transcript", runId], queryFn: () => api.transcript(runId) });
  const issues = useQuery({ queryKey: ["issues", runId], queryFn: () => api.issues(runId) });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [lower, setLower] = useState<"retention" | "risk" | "shots" | "provenance">("retention");
  const [userScenario, setUserScenario] = useState<Scenario | null>(null);
  const { focus, selectedIssue } = usePlayhead();
  const items = issues.data?.items ?? [];

  // land on the highest-priority supported finding (spec: "open at the highest-priority supported finding")
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
  const selected = items.find((i) => i.issue_id === selectedIssue);

  const high = items.filter((i) => i.review_status !== "dismissed" && i.severity === "high").length;
  const med = items.filter((i) => i.review_status !== "dismissed" && i.severity === "medium").length;
  const payoff = promises.map((p) => (p.partial_interval ?? p.fulfilled_interval)?.start_ms).filter((x): x is number => x !== undefined)
    .sort((a, b) => a - b)[0];
  const covered = (mod: string) => r.coverage.filter((c) => c.modality === mod && c.status === "observed")
    .reduce((t, c) => t + c.interval.end_ms - c.interval.start_ms, 0) / duration;
  const visualPending = "visual" in r.missing_stages;

  const exportFindings = () => download(`findings-${runId.slice(0, 8)}.csv`, ["type,severity,evidence,status,start,end,explanation",
    ...prioritise(items).map((i) => [i.type, i.severity, i.evidence_status, i.review_status, fmt(i.affected_interval.start_ms),
      fmt(i.affected_interval.end_ms), i.explanation].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","))].join("\n"), "text/csv");

  return (
    <div className="shell">
      <div className="header">
        <Link to="/"><button className="back" aria-label="Back to projects">‹</button></Link>
        <div className="title">
          <h1>{title}</h1>
          <div className="sub">{r.project?.category ?? ""} · {fmt(duration).replace(/\.\d$/, "")} ·{" "}
            <select aria-label="Run" value={runId} onChange={(e) => nav(`/runs/${e.target.value}`)}
              style={{ padding: "2px 8px", fontSize: 13, background: "transparent", boxShadow: "none" }}>
              {(runs.length ? runs : [{ run_id: runId, created_at: r.run.created_at, package_kind: r.package_kind, status: "" }]).map((x) => (
                <option key={x.run_id} value={x.run_id}>run {x.run_id.slice(0, 8)} · {x.created_at.slice(0, 16).replace("T", " ")} · {x.package_kind}</option>))}
            </select></div>
        </div>
        <div className="right">
          <span className={`pill ${r.package_kind === "analysis" ? "supported" : "amber"}`}>
            {r.package_kind === "analysis" ? "complete analysis" : visualPending ? "visual analysis incomplete" : "partial analysis"}</span>
          <button onClick={exportFindings}>Export findings</button>
          <Link to={`/runs/${runId}/plan`}><button>Edit plan</button></Link>
        </div>
      </div>

      <div className="summary">
        <span className="item"><b>{high + med}</b> high/medium-priority findings</span>
        <span className="item">earliest title payoff <b>{payoff !== undefined ? fmt(payoff) : "not found"}</b></span>
        <span className="item">speech coverage <b>{Math.round(covered("speech") * 100)}%</b></span>
        <span className="item">visual coverage <b>{visualPending ? "not inspected yet" : `${Math.round(covered("visual") * 100)}%`}</b></span>
        <span className="item">on-screen text <b>{covered("text") ? `${Math.round(covered("text") * 100)}%` : "not inspected"}</b></span>
      </div>

      <div className="ws">
        <div className="card" style={{ padding: 14 }}>
          <Player src={r.proxy_artifact_id ? api.artifactUrl(runId, r.proxy_artifact_id) : null} />
        </div>
        <div className="card">
          <TranscriptPanel segments={segments} words={tr.data?.words ?? []} issues={items}
            spans={tl.data?.structure_spans ?? []} markers={tl.data?.markers ?? []} promises={promises} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <Timeline duration={duration} chapters={tl.data?.chapters ?? []} issues={items} risk={tl.data?.risk ?? []}
          scenario={scenario} scenarioAck={scenarioAck} shots={tl.data?.shots ?? []} segments={segments} coverage={tl.data?.coverage ?? []} />
        <div className="legend">
          <span><span className="swatch" style={{ background: "var(--sev-high)" }} />high</span>
          <span><span className="swatch" style={{ background: "var(--sev-medium)" }} />medium</span>
          <span><span className="swatch" style={{ background: "#a9a5a0" }} />low</span>
          <span><span className="swatch" style={{ background: "repeating-linear-gradient(45deg,#a9a5a0 0 3px,#555 3px 6px)" }} />provisional</span>
          <span><span className="swatch tl-unknown" />not inspected (unknown, never "healthy")</span>
          <span><span className="swatch" style={{ background: "var(--amber-800)" }} />long, low-motion shot</span>
          <span className="faint">Retention lane: estimated, uncalibrated scenario · Risk: heuristic 0–100</span>
        </div>
      </div>

      <div className="bottom">
        <div className="card">
          <div className="section-title"><h3>Findings</h3><span className="sub">ranked by severity and evidence</span></div>
          {issues.data ? <FindingsList issues={items} /> : <p className="muted">Loading findings…</p>}
        </div>
        <div className="card"><FindingDetail runId={runId} issue={selected} segments={segments} risk={tl.data?.risk ?? []} /></div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="tabs">
          {(["retention", "risk", "shots", "provenance"] as const).map((t) => (
            <button key={t} className={lower === t ? "on" : ""} onClick={() => setLower(t)}>
              {t === "retention" ? "Estimated retention" : t === "risk" ? "Risk by track" : t === "shots" ? "Shots" : "What was analysed"}</button>))}
        </div>
        {lower === "risk" && tl.data && <RiskChart bins={tl.data.risk} duration={duration} chapters={tl.data.chapters} />}
        {lower === "retention" && <RetentionChart runId={runId} scenario={scenario} duration={duration}
          ack={!!userScenario} onScenario={setUserScenario} />}
        {lower === "shots" && <ShotsView runId={runId} issues={items} segments={segments} visualPending={visualPending} />}
        {lower === "provenance" && (
          <div className="kv">
            <span className="muted">Not analysed</span>
            <span>{Object.entries(r.missing_stages).map(([k, v]) => `${k} — ${v}`).join(" · ") || "nothing missing"}</span>
            <span className="muted">Run</span><span>{r.run.status} ({r.package_kind}) · <span className="mono">{r.run.created_at}</span></span>
            <span className="muted">Visual model profile</span><span>{r.run.model_profile}</span>
            {Object.entries(r.run.provenance).filter(([k]) => ["code_revision", "precision", "scoring_version", "external_service_model", "detector_config"].includes(k))
              .map(([k, v]) => [<span key={k} className="muted">{k.replace(/_/g, " ")}</span>,
                <span key={k + "v"} className="mono">{typeof v === "string" ? v : JSON.stringify(v)}</span>])}
            <span className="muted">Models</span>
            <span className="mono">{(r.run.provenance.models as { role: string; model_id: string; revision: string }[])
              .map((m) => `${m.role}: ${m.model_id}@${m.revision.slice(0, 8)}`).join(" · ")}</span>
            <span className="muted">Stages</span>
            <span>{r.run.stages.map((s) => `${s.name}: ${s.status}`).join(" · ")}</span>
          </div>
        )}
      </div>
      <Dock active="review" runId={runId} />
    </div>
  );
}
