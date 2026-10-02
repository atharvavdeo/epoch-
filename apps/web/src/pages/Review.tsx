import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api, fmt, type Scenario } from "../api";
import { RetentionChart, RiskChart } from "../components/Charts";
import { IssueList } from "../components/Issues";
import { Player, Transcript } from "../components/Player";
import { usePlayhead } from "../store";

export default function Review() {
  const { runId = "" } = useParams();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId) });
  const tl = useQuery({ queryKey: ["timeline", runId], queryFn: () => api.timeline(runId) });
  const tr = useQuery({ queryKey: ["transcript", runId], queryFn: () => api.transcript(runId) });
  const issues = useQuery({ queryKey: ["issues", runId], queryFn: () => api.issues(runId) });
  const [tab, setTab] = useState<"risk" | "retention" | "provenance">("risk");
  const [userScenario, setUserScenario] = useState<Scenario | null>(null);
  const { seek } = usePlayhead();

  if (run.isLoading) return <div className="shell muted">Loading run…</div>;
  if (run.error || !run.data) return <div className="shell err">Run not found. <Link to="/">Back</Link></div>;
  const r = run.data;
  const duration = r.asset.duration_ms;
  const missing = Object.entries(r.missing_stages);
  const scenario = userScenario ?? tl.data?.scenarios[0];
  const markers = tl.data?.markers ?? [];
  const promises = tl.data?.promises ?? [];

  return (
    <div className="shell">
      <div className="topbar">
        <Link to="/">← Projects</Link>
        <h1 className="grow">{r.asset.original_name}</h1>
        <span className={`pill ${r.package_kind === "analysis" ? "" : "warn"}`}>{r.package_kind === "analysis" ? "complete analysis" : "partial analysis"}</span>
        <span className="pill">{r.run.model_profile}</span>
        <span className="pill mono">run {r.run.run_id.slice(0, 8)}</span>
      </div>
      {!!missing.length && (
        <div className="banner" style={{ marginBottom: 12 }}>
          <b>Missing or substituted analysis:</b> {missing.map(([k, v]) => `${k}: ${v}`).join(" · ")}. Missing tracks are shown as unknown, never as healthy.
        </div>
      )}
      <div className="grid">
        <div className="card">
          <Player src={r.proxy_artifact_id ? api.artifactUrl(runId, r.proxy_artifact_id) : null} />
          <div className="legend" style={{ marginTop: 8 }}>
            {markers.map((m) => (
              <button key={m.signal_id} onClick={() => seek(m.name === "time_to_substance" ? Number(m.value) : m.interval.start_ms)}>
                {m.name === "hook" ? "Hook" : "First substance"} {fmt(m.name === "time_to_substance" ? Number(m.value) : m.interval.start_ms)}
              </button>))}
            {promises.map((p) => {
              // delivery start first: a promise answered progressively is not a late payoff
              const begin = p.partial_interval ?? p.fulfilled_interval;
              return (
                <button key={p.promise_id} title={p.obligation} onClick={() => begin && seek(begin.start_ms)}>
                  Promise “{p.title_quote}”: {p.status}
                  {p.partial_interval && ` · delivery from ${fmt(p.partial_interval.start_ms)}`}
                  {p.fulfilled_interval && ` · ${p.partial_interval ? "complete" : "delivered"} ${fmt(p.fulfilled_interval.start_ms)}`}
                </button>);
            })}
          </div>
          <Transcript segments={tr.data?.segments ?? []} />
        </div>
        <div className="card">
          <h2 style={{ marginBottom: 8 }}>Findings <span className="muted" style={{ fontSize: 13 }}>ranked by severity and evidence</span></h2>
          {issues.data ? <IssueList runId={runId} issues={issues.data.items} segments={tr.data?.segments ?? []} />
            : <p className="muted">Loading findings…</p>}
        </div>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <div className="tabs">
          {(["risk", "retention", "provenance"] as const).map((t) => (
            <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
              {t === "risk" ? "Risk by track" : t === "retention" ? "Estimated retention" : "Provenance & coverage"}</button>))}
        </div>
        {tab === "risk" && tl.data && <RiskChart bins={tl.data.risk} duration={duration} chapters={tl.data.chapters} />}
        {tab === "retention" && <RetentionChart runId={runId} scenario={scenario} duration={duration}
          ack={!!userScenario} onScenario={setUserScenario} />}
        {tab === "provenance" && (
          <div className="kv">
            <span className="muted">Run status</span><span>{r.run.status} ({r.package_kind})</span>
            <span className="muted">Created</span><span className="mono">{r.run.created_at}</span>
            <span className="muted">Visual model profile</span><span>{r.run.model_profile}</span>
            {Object.entries(r.run.provenance).filter(([k]) => ["code_revision", "precision", "scoring_version", "external_service_model", "detector_config"].includes(k))
              .map(([k, v]) => [<span key={k} className="muted">{k}</span>, <span key={k + "v"} className="mono">{typeof v === "string" ? v : JSON.stringify(v)}</span>])}
            <span className="muted">Models</span>
            <span className="mono">{(r.run.provenance.models as { role: string; model_id: string; revision: string }[]).map((m) => `${m.role}: ${m.model_id}@${m.revision.slice(0, 8)}`).join(" · ")}</span>
            <span className="muted">Stages</span>
            <span>{r.run.stages.map((s) => `${s.name}: ${s.status}`).join(" · ")}</span>
            <span className="muted">Coverage</span>
            <span>{Object.entries(r.coverage.reduce<Record<string, number>>((acc, c) => {
              const k = `${c.modality} ${c.status}`; acc[k] = (acc[k] ?? 0) + (c.interval.end_ms - c.interval.start_ms); return acc; }, {}))
              .map(([k, v]) => `${k} ${fmt(v)}`).join(" · ")}</span>
          </div>
        )}
      </div>
    </div>
  );
}
