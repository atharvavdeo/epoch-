import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, fmt, type Issue, type Segment, type Shot } from "../api";
import { overlaps, usePlayhead } from "../store";
import { issueLabel } from "./Timeline";

const num = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? "—" : v.toFixed(d));
const s2 = (ms: number) => fmt(ms).replace(/\.\d$/, "");

/** Plain-language reasons this shot is worth a look (or that nothing stands out). Measured facts only. */
function whyItMatters(shot: Shot, all: Shot[], related: Issue[]): string[] {
  const len = (shot.interval.end_ms - shot.interval.start_ms) / 1000;
  const lens = all.map((s) => (s.interval.end_ms - s.interval.start_ms) / 1000).sort((a, b) => a - b);
  const med = lens[Math.floor(lens.length / 2)] || 0;
  const out: string[] = [];
  if (related.length) out.push(`${related.length} finding${related.length > 1 ? "s" : ""} overlap this shot.`);
  if (med && len > 3 * med && len > 8) out.push(`It runs ${len.toFixed(0)} s, over three times this video's typical shot (${med.toFixed(1)} s).`);
  const mot = shot.metrics.motion_mean;
  const mots = all.map((s) => s.metrics.motion_mean).filter((v): v is number => typeof v === "number").sort((a, b) => a - b);
  if (typeof mot === "number" && mots.length > 5 && mot <= mots[Math.floor(mots.length * 0.1)] && len > 5)
    out.push("It is among the stillest 10% of shots in this video.");
  if (!out.length) out.push("Nothing measured stands out here. A long or static shot is not a problem by itself.");
  return out;
}

function ShotInspector({ runId, shot, n, all, issues, segments, visualPending }: {
  runId: string; shot: Shot; n: number; all: Shot[]; issues: Issue[]; segments: Segment[]; visualPending: boolean;
}) {
  const { focus } = usePlayhead();
  const [tab, setTab] = useState<"measured" | "frames">("measured");
  const m = shot.metrics;
  const len = shot.interval.end_ms - shot.interval.start_ms;
  const speech = segments.filter((s) => overlaps(s.interval, shot.interval)).map((s) => s.text).join(" ");
  const related = issues.filter((i) => i.review_status !== "dismissed" && overlaps(i.affected_interval, shot.interval));
  return (
    <div className="shot-inspector">
      <div className="si-head">
        <h3>Shot {n}</h3>
        <button className="time" onClick={() => focus(shot.interval, null)}>{s2(shot.interval.start_ms)}–{s2(shot.interval.end_ms)}</button>
        <span className="faint">{(len / 1000).toFixed(1)} s</span>
      </div>
      <div className="si-grid">
        {shot.thumb ? <img className="shot-big" src={api.artifactUrl(runId, shot.thumb.artifact_id)} alt={`sampled still at ${fmt(shot.thumb.at_ms)}`} />
          : <div className="shot-big noimg">no still</div>}
        <div>
          <h4>Why this shot matters</h4>
          <ul className="si-why">{whyItMatters(shot, all, related).map((w) => <li key={w}>{w}</li>)}</ul>
          {related.map((i) => (
            <button key={i.issue_id} className="chip" style={{ marginRight: 6, marginBottom: 6 }} onClick={() => focus(i.affected_interval, i.issue_id)}>
              {issueLabel(i.type)} · {i.severity}</button>))}
          {speech && <p className="muted" style={{ fontSize: 14 }}><span className="faint">Said over this shot: </span>“{speech.slice(0, 260)}{speech.length > 260 ? "…" : ""}”</p>}
        </div>
      </div>
      <div className="tabs" style={{ marginTop: 16 }}>
        <button className={tab === "measured" ? "on" : ""} onClick={() => setTab("measured")}>Measurements</button>
        <button className={tab === "frames" ? "on" : ""} onClick={() => setTab("frames")}>Sampled frames &amp; observations</button>
      </div>
      {tab === "measured" ? (
        <div className="kv" style={{ gridTemplateColumns: "180px 1fr", fontSize: 14 }}>
          <span className="muted">Boundaries</span><span>{shot.start_boundary_source} → {shot.end_boundary_source}</span>
          <span className="muted">Motion (mean / max)</span><span className="mono">{num(m.motion_mean, 3)} / {num(m.motion_max, 3)}</span>
          <span className="muted">Brightness (mean)</span><span className="mono">{num(m.luma_mean_mean)}</span>
          <span className="muted">Sharpness proxy</span><span className="mono">{num(m.blur_lapvar_mean, 0)}</span>
          <span className="muted">Samples measured</span><span className="mono">{m.samples ?? "—"}</span>
        </div>
      ) : (
        <div>
          {shot.thumb && <p className="faint" style={{ fontSize: 13 }}>Still at {fmt(shot.thumb.at_ms)}{shot.thumb.inside_shot ? "" : " (nearest still; none falls inside this shot)"}.
            Stills are sampled about once a second; anything between them is unseen.</p>}
          {shot.observations.length ? shot.observations.map((o) => <div key={o.observation_id} className="quote-orig">{o.statement}</div>)
            : <div className="uninspected">{visualPending ? "Not inspected: visual analysis is on hold for this video." : "No visual observation covers this shot."}</div>}
        </div>
      )}
    </div>
  );
}

/** Horizontal filmstrip, then one inspector for the selected shot. */
export function ShotsView({ runId, issues, segments, visualPending }: { runId: string; issues: Issue[]; segments: Segment[]; visualPending: boolean }) {
  const q = useQuery({ queryKey: ["shots", runId], queryFn: () => api.shots(runId) });
  const { currentMs, focus, selection } = usePlayhead();
  const shots = q.data?.items ?? [];
  const idx = shots.findIndex((s) => s.interval.start_ms <= currentMs && currentMs < s.interval.end_ms);
  const selIdx = selection ? shots.findIndex((s) => overlaps(s.interval, selection) && s.interval.start_ms <= selection.start_ms + 1) : idx;
  const cur = selIdx >= 0 ? selIdx : Math.max(0, idx);
  useEffect(() => { document.getElementById(`shot-${cur}`)?.scrollIntoView({ block: "nearest", inline: "center" }); }, [cur]);
  if (q.isLoading) return <p className="muted">Loading shots…</p>;
  if (!shots.length) return <p className="muted">No shot data in this run.</p>;
  return (
    <div className="shots">
      <div className="strip">
        {shots.map((s, i) => {
          const len = s.interval.end_ms - s.interval.start_ms;
          const flagged = issues.some((x) => x.review_status !== "dismissed" && overlaps(x.affected_interval, s.interval));
          return (
            <button key={s.shot_id} id={`shot-${i}`} className={`tile ${i === cur ? "sel" : ""}`} aria-pressed={i === cur}
              onClick={() => focus(s.interval, null)} title={`shot ${i + 1} · ${s2(s.interval.start_ms)} · ${(len / 1000).toFixed(1)} s${flagged ? " · has a finding" : ""}`}>
              {s.thumb ? <img loading="lazy" src={api.artifactUrl(runId, s.thumb.artifact_id)} alt="" /> : <span className="noimg">no still</span>}
              <span className="cap"><span className="mono">{s2(s.interval.start_ms)}</span><span>{(len / 1000).toFixed(1)}s{flagged ? " ·●" : ""}</span></span>
            </button>);
        })}
      </div>
      <ShotInspector runId={runId} shot={shots[cur]} n={cur + 1} all={shots} issues={issues} segments={segments} visualPending={visualPending} />
    </div>
  );
}
