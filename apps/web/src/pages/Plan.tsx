import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api, fmt, type Bound } from "../api";
import { Dock } from "../components/Dock";
import { EditPlan } from "../components/EditPlan";
import { issueLabel } from "../components/Timeline";
import { IconBack } from "../components/Icons";
import { Spinner, SkeletonBlock } from "../components/Spinner";
import { overlaps } from "../store";

const b = (x: Bound | null, unit: string, d = 0) =>
  !x ? "—" : x.central !== null ? `${x.central.toFixed(d)}${unit}` : `${x.lower.toFixed(d)}–${x.upper.toFixed(d)}${unit}`;

export default function Plan() {
  const { runId = "" } = useParams();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId) });
  const issues = useQuery({ queryKey: ["issues", runId], queryFn: () => api.issues(runId) });
  const tr = useQuery({ queryKey: ["transcript", runId], queryFn: () => api.transcript(runId) });
  const tl = useQuery({ queryKey: ["timeline", runId], queryFn: () => api.timeline(runId) });
  const [a30, setA30] = useState(0.8);
  const [aEnd, setAEnd] = useState(0.45);
  const [ack, setAck] = useState(false);
  const [resolved, setResolved] = useState<string[]>([]);
  const hyp = useMutation({ mutationFn: () => api.hypothetical(runId, { retention_at_30s: a30, retention_at_end: aEnd, kappa: 1,
    acknowledged: true, assumed_resolved_issue_ids: resolved }) });

  if (run.isLoading || issues.isLoading) return <div className="shell"><SkeletonBlock lines={5} /></div>;
  if (!run.data) return <div className="shell err">Run not found. <Link to="/">Back</Link></div>;
  const items = issues.data?.items ?? [];
  const title = run.data.project?.title ?? run.data.asset.original_name;
  const accepted = items.filter((i) => i.review_status === "accepted");
  const edits = accepted.flatMap((i) => i.suggestions.map((s) => ({ i, s }))).filter((x) => x.s.source_interval);
  // conflicts: two staged edits touching the same time, or a cut removing what another edit relies on
  const conflicts = edits.flatMap((x, k) => edits.slice(k + 1).filter((y) => overlaps(x.s.source_interval!, y.s.source_interval!))
    .map((y) => `${issueLabel(x.i.type)} (${x.s.operation}) and ${issueLabel(y.i.type)} (${y.s.operation}) both change ${fmt(Math.max(x.s.source_interval!.start_ms, y.s.source_interval!.start_ms))}`));
  const cuts = edits.filter((x) => x.s.operation === "cut").map((x) => x.s.source_interval!);
  const before = (ms: number) => cuts.reduce((t, c) => t + Math.max(0, Math.min(ms, c.end_ms) - c.start_ms), 0);
  const payoff = (tl.data?.promises ?? []).map((p) => (p.partial_interval ?? p.fulfilled_interval)?.start_ms)
    .filter((x): x is number => x !== undefined).sort((p, q) => p - q)[0];
  const open = items.filter((i) => i.review_status === "open").length;
  const res = hyp.data;

  return (
    <div className="shell">
      <div className="header">
        <Link to={`/runs/${runId}`} className="icon-btn icon-lg" aria-label="Back to review" title="Back to review"><IconBack /></Link>
        <div className="title"><h1>Edit plan</h1><div className="sub">{title}</div></div>
        <span />
      </div>
      <div className="summary">
        <span className="item">duration <b>{fmt(run.data.asset.duration_ms)}</b> → <b>{fmt(run.data.asset.duration_ms - before(10 ** 12))}</b></span>
        <span className="item">title payoff starts <b>{payoff !== undefined ? `${fmt(payoff)} → ${fmt(payoff - before(payoff))}` : "not found"}</b></span>
        <span className="item">unresolved findings <b>{open}</b></span>
        <span className="item">visual coverage <b>{"visual" in run.data.missing_stages ? "not inspected" : "see review"}</b></span>
      </div>
      {!!conflicts.length && <div className="banner">Conflicts to resolve: {conflicts.join(" · ")}</div>}
      <div className="bottom" style={{ marginTop: 0 }}>
        <div className="card">
          <div className="section-title"><h3>Queue</h3></div>
          <EditPlan issues={items} segments={tr.data?.segments ?? []} title={title} />
        </div>
        <div className="card">
          <div className="section-title"><h3>Compare</h3></div>
          <h4 className="fdh">Hypothetical (this plan, assumed audience)</h4>
          <p className="muted" style={{ fontSize: 14 }}>Applies the accepted <b>cuts</b> to the timeline and recomputes the uncalibrated
            scenario with the same assumptions. Moves, rewrites and added visuals are not modelled: they need a reanalysed video.</p>
          <div className="row" style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <label>at 30 s <input type="number" step="0.05" min="0.05" max="1" value={a30} onChange={(e) => setA30(+e.target.value)} style={{ width: 80 }} /></label>
            <label>at end <input type="number" step="0.05" min="0.05" max="1" value={aEnd} onChange={(e) => setAEnd(+e.target.value)} style={{ width: 80 }} /></label>
            <label><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> These are assumptions</label>
          </div>
          <details style={{ marginTop: 10 }}>
            <summary className="muted" style={{ cursor: "pointer" }}>Also assume some concerns are resolved ({resolved.length})</summary>
            <p className="faint" style={{ fontSize: 13 }}>Separate from review status: this only changes the hypothetical, never the findings.</p>
            {items.filter((i) => i.review_status !== "dismissed").map((i) => (
              <label key={i.issue_id} style={{ display: "block", fontSize: 14, margin: "4px 0" }}>
                <input type="checkbox" checked={resolved.includes(i.issue_id)}
                  onChange={(e) => setResolved(e.target.checked ? [...resolved, i.issue_id] : resolved.filter((x) => x !== i.issue_id))} />
                {" "}{issueLabel(i.type)} {fmt(i.affected_interval.start_ms)} ({i.severity})</label>))}
          </details>
          <div className="actions">
            <button className="soft" disabled={!ack || !(aEnd > 0 && aEnd <= a30 && a30 <= 1) || hyp.isPending} onClick={() => hyp.mutate()}>
              {hyp.isPending && <Spinner />}Compute what-if</button>
          </div>
          {hyp.error && <p className="err">{(hyp.error as Error).message}</p>}
          {res && res.status !== "hypothetical" && <p className="muted">Not comparable: {res.reason}</p>}
          {res && res.status === "hypothetical" && (
            <div style={{ marginTop: 12 }}>
              <div className="pill">{res.label}</div>
              <table className="cmp">
                <thead><tr><th /><th>Current</th><th>With this plan</th></tr></thead>
                <tbody>
                  <tr><td>Duration</td><td>{fmt(res.before.duration_ms)}</td><td>{fmt(res.after.duration_ms)}</td></tr>
                  <tr><td>Assumed avg. watch time</td><td>{b(res.before.assumed_avd_seconds, " s")}</td><td>{b(res.after.assumed_avd_seconds, " s")}</td></tr>
                  <tr><td>Assumed % viewed</td><td>{b(res.before.assumed_apv_pct, "%", 1)}</td><td>{b(res.after.assumed_apv_pct, "%", 1)}</td></tr>
                  <tr><td>Assumed still watching at end</td><td>{b(res.before.assumed_end_pct, "%", 1)}</td><td>{b(res.after.assumed_end_pct, "%", 1)}</td></tr>
                </tbody>
              </table>
              <p className="faint" style={{ fontSize: 13 }}>{res.note} Removed {fmt(res.removed_ms)} via {res.cuts.length} cut(s);
                {" "}{res.removed_by_cut_issue_ids.length} finding(s) fall entirely inside cuts. {res.not_modelled}.</p>
            </div>)}
          <h4 className="fdh" style={{ marginTop: 20 }}>Reanalysed video</h4>
          <p className="muted" style={{ fontSize: 14 }}>Export the edit plan, make the edits, then analyse the edited file as a new run
            of this project. Its runs appear in the run selector on the Review screen for side-by-side review.</p>
        </div>
      </div>
      <Dock active="plan" runId={runId} />
    </div>
  );
}
