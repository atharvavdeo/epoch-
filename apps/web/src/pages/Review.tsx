import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api, fmt, type Scenario } from "../api";
import { RetentionChart, RiskChart } from "../components/Charts";
import { Dock } from "../components/Dock";
import { EditPlan } from "../components/EditPlan";
import { IssueList } from "../components/Issues";
import { Player, Transcript } from "../components/Player";
import { Timeline } from "../components/Timeline";
import { usePlayhead } from "../store";

/** Pipeline progress, honest about what has not run yet. */
function Steps({ missing }: { missing: Record<string, string> }) {
  const steps: [string, string, string][] = [
    ["Media + audio measured", "done", "probe, cuts, black/freeze, loudness, clipping"],
    ["Transcript + word timing", missing.asr || missing.align ? "off" : "done", "faster-whisper + WhisperX"],
    ["Narrative review", missing.narrative ? "off" : "done", "Cerebras, evidence-checked"],
    ["Visual analysis (Colab)", missing.visual ? "pending" : "done", missing.visual ?? "Qwen VLM on sampled frames"],
    ["On-screen text (OCR)", missing.ocr ? "off" : "done", missing.ocr ?? "OCR"],
  ];
  return (
    <div className="steps">
      {steps.map(([name, st, tip]) => (
        <span key={name} className={`step ${st}`} title={tip}><span className="dot" />{name}
          {st === "pending" && <span className="faint">· waiting</span>}{st === "off" && <span className="faint">· not run</span>}</span>))}
    </div>
  );
}

export default function Review() {
  const { runId = "" } = useParams();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId) });
  const tl = useQuery({ queryKey: ["timeline", runId], queryFn: () => api.timeline(runId) });
  const tr = useQuery({ queryKey: ["transcript", runId], queryFn: () => api.transcript(runId) });
  const issues = useQuery({ queryKey: ["issues", runId], queryFn: () => api.issues(runId) });
  const [side, setSide] = useState<"findings" | "plan">("findings");
  const [lower, setLower] = useState<"retention" | "risk" | "provenance">("retention");
  const [userScenario, setUserScenario] = useState<Scenario | null>(null);
  const { seek } = usePlayhead();

  if (run.isLoading) return <div className="shell muted">Loading run…</div>;
  if (run.error || !run.data) return <div className="shell err">Run not found. <Link to="/">Back to projects</Link></div>;
  const r = run.data;
  const duration = r.asset.duration_ms;
  const title = r.project?.title ?? r.asset.original_name;
  const items = issues.data?.items ?? [];
  const segments = tr.data?.segments ?? [];
  const scenario = userScenario ?? tl.data?.scenarios[0];
  const markers = tl.data?.markers ?? [];
  const promises = tl.data?.promises ?? [];
  const accepted = items.filter((i) => i.review_status === "accepted").length;

  return (
    <div className="shell">
      <div className="header">
        <Link to="/"><button className="back" aria-label="Back to projects">‹</button></Link>
        <div className="title">
          <h1>{title}</h1>
          <div className="sub">{r.project?.category ?? ""} · {fmt(duration).replace(/\.\d$/, "")} · {items.length} findings · run {r.run.run_id.slice(0, 8)}</div>
        </div>
        <div className="right">
          <span className={`pill ${r.package_kind === "analysis" ? "supported" : "amber"}`}>
            {r.package_kind === "analysis" ? "complete analysis" : "partial analysis"}</span>
          <span className="pill" title="visual model profile">{r.run.model_profile}</span>
        </div>
      </div>
      <Steps missing={r.missing_stages} />

      <div className="review">
        <div className="stage">
          <div className="card" style={{ padding: 14 }}>
            <Player src={r.proxy_artifact_id ? api.artifactUrl(runId, r.proxy_artifact_id) : null} />
            <div style={{ marginTop: 34 }}>
              <Timeline duration={duration} chapters={tl.data?.chapters ?? []} issues={items} risk={tl.data?.risk ?? []} />
            </div>
            <div className="actions" style={{ marginTop: 10 }}>
              {markers.map((m) => {
                const at = m.name === "time_to_substance" ? Number(m.value) : m.interval.start_ms;
                return <button key={m.signal_id} className="chip" onClick={() => seek(at)}>
                  {m.name === "hook" ? "Hook" : "First real content"} {fmt(at)}</button>;
              })}
              {promises.map((p) => {
                const begin = p.partial_interval ?? p.fulfilled_interval;
                return (
                  <button key={p.promise_id} className="chip" title={p.obligation} onClick={() => begin && seek(begin.start_ms)}>
                    Title promise: {p.status}{p.partial_interval && ` · from ${fmt(p.partial_interval.start_ms)}`}
                    {p.fulfilled_interval && ` · ${p.partial_interval ? "complete" : "delivered"} ${fmt(p.fulfilled_interval.start_ms)}`}
                  </button>);
              })}
            </div>
          </div>
          <div className="card">
            <div className="section-title"><h3>Transcript</h3><span className="sub">click a line to jump · underlined lines are inside a finding</span></div>
            <Transcript segments={segments} flagged={items.filter((i) => i.review_status !== "dismissed").map((i) => i.affected_interval)} />
          </div>
        </div>

        <div className="card">
          <div className="tabs">
            <button className={side === "findings" ? "on" : ""} onClick={() => setSide("findings")}>Findings ({items.length})</button>
            <button className={side === "plan" ? "on" : ""} onClick={() => setSide("plan")}>Edit plan ({accepted})</button>
          </div>
          {side === "findings" && (issues.data
            ? <IssueList runId={runId} issues={items} segments={segments} />
            : <p className="muted">Loading findings…</p>)}
          {side === "plan" && <EditPlan issues={items} segments={segments} title={title} />}
        </div>
      </div>

      {!!Object.keys(r.missing_stages).length && (
        <div className="banner" style={{ marginTop: 16 }}>
          <b>Not analysed yet:</b> {Object.entries(r.missing_stages).map(([k, v]) => `${k} — ${v}`).join(" · ")}.
          {" "}Those parts of the timeline are shown as unknown, never as healthy.
        </div>)}

      <div className="card" style={{ marginTop: 16 }}>
        <div className="tabs">
          {(["retention", "risk", "provenance"] as const).map((t) => (
            <button key={t} className={lower === t ? "on" : ""} onClick={() => setLower(t)}>
              {t === "retention" ? "Estimated retention" : t === "risk" ? "Risk by track" : "Provenance & coverage"}</button>))}
        </div>
        {lower === "risk" && tl.data && <RiskChart bins={tl.data.risk} duration={duration} chapters={tl.data.chapters} />}
        {lower === "retention" && <RetentionChart runId={runId} scenario={scenario} duration={duration}
          ack={!!userScenario} onScenario={setUserScenario} />}
        {lower === "provenance" && (
          <div className="kv">
            <span className="muted">Run status</span><span>{r.run.status} ({r.package_kind})</span>
            <span className="muted">Created</span><span className="mono">{r.run.created_at}</span>
            <span className="muted">Visual model profile</span><span>{r.run.model_profile}</span>
            {Object.entries(r.run.provenance).filter(([k]) => ["code_revision", "precision", "scoring_version", "external_service_model", "detector_config"].includes(k))
              .map(([k, v]) => [<span key={k} className="muted">{k.replace(/_/g, " ")}</span>,
                <span key={k + "v"} className="mono">{typeof v === "string" ? v : JSON.stringify(v)}</span>])}
            <span className="muted">Models</span>
            <span className="mono">{(r.run.provenance.models as { role: string; model_id: string; revision: string }[])
              .map((m) => `${m.role}: ${m.model_id}@${m.revision.slice(0, 8)}`).join(" · ")}</span>
            <span className="muted">Stages</span>
            <span>{r.run.stages.map((s) => `${s.name}: ${s.status}`).join(" · ")}</span>
            <span className="muted">Coverage</span>
            <span>{Object.entries(r.coverage.reduce<Record<string, number>>((acc, c) => {
              const k = `${c.modality} ${c.status}`; acc[k] = (acc[k] ?? 0) + (c.interval.end_ms - c.interval.start_ms); return acc; }, {}))
              .map(([k, v]) => `${k} ${fmt(v)}`).join(" · ")}</span>
          </div>
        )}
      </div>
      <Dock active="review" />
    </div>
  );
}
