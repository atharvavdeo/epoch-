import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api, fmt, type Issue, type Segment, type Shot } from "../api";
import { overlaps, usePlayhead } from "../store";
import { issueLabel } from "./Timeline";

const num = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? "—" : v.toFixed(d));

function ShotDetail({ runId, shot, n, issues, segments, visualPending }: {
  runId: string; shot: Shot; n: number; issues: Issue[]; segments: Segment[]; visualPending: boolean;
}) {
  const { focus } = usePlayhead();
  const m = shot.metrics;
  const len = shot.interval.end_ms - shot.interval.start_ms;
  const speech = segments.filter((s) => overlaps(s.interval, shot.interval)).map((s) => s.text).join(" ");
  const related = issues.filter((i) => overlaps(i.affected_interval, shot.interval));
  return (
    <div className="shot-detail">
      <div className="row" style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <h3>Shot {n}</h3>
        <button className="time" onClick={() => focus(shot.interval, null)}>{fmt(shot.interval.start_ms)}–{fmt(shot.interval.end_ms)}</button>
        <span className="faint">{(len / 1000).toFixed(1)} s</span>
      </div>
      {shot.thumb && <img className="shot-big" src={api.artifactUrl(runId, shot.thumb.artifact_id)}
        alt={`sampled still at ${fmt(shot.thumb.at_ms)}`} />}
      <section><h4>Measured</h4>
        <div className="kv" style={{ gridTemplateColumns: "150px 1fr", fontSize: 13 }}>
          <span className="muted">Boundaries</span><span>{shot.start_boundary_source} → {shot.end_boundary_source}</span>
          <span className="muted">Motion (mean / max)</span><span className="mono">{num(m.motion_mean, 3)} / {num(m.motion_max, 3)}</span>
          <span className="muted">Brightness (mean)</span><span className="mono">{num(m.luma_mean_mean)}</span>
          <span className="muted">Sharpness proxy</span><span className="mono">{num(m.blur_lapvar_mean, 0)}</span>
          <span className="muted">Samples measured</span><span className="mono">{m.samples ?? "—"}</span>
        </div>
      </section>
      <section><h4>Observed</h4>
        {shot.observations.length ? shot.observations.map((o) => <div key={o.observation_id} className="quote-orig">{o.statement}</div>)
          : <div className="uninspected">{visualPending ? "Not inspected yet: the visual model has not run on this video."
            : "No visual observation covers this shot."} Stills are sampled about once a second; anything between them is unseen.</div>}
      </section>
      <section><h4>Interpretation</h4>
        {speech && <div className="muted" style={{ fontSize: 13 }}><span className="faint">Said over this shot: </span>{speech.slice(0, 280)}{speech.length > 280 ? "…" : ""}</div>}
        {related.length ? related.map((i) => (
          <button key={i.issue_id} className="chip" style={{ marginTop: 6, marginRight: 6 }} onClick={() => focus(i.affected_interval, i.issue_id)}>
            {issueLabel(i.type)} · {i.severity}</button>))
          : <div className="faint" style={{ fontSize: 13, marginTop: 6 }}>No finding involves this shot. A long or static shot is not a problem by itself.</div>}
      </section>
    </div>
  );
}

/** Filmstrip of measured shots with sampled stills; selecting a tile seeks the shared playhead. */
export function ShotsView({ runId, issues, segments, visualPending }: { runId: string; issues: Issue[]; segments: Segment[]; visualPending: boolean }) {
  const q = useQuery({ queryKey: ["shots", runId], queryFn: () => api.shots(runId) });
  const { currentMs, focus, selection } = usePlayhead();
  const stripRef = useRef<HTMLDivElement>(null);
  const shots = q.data?.items ?? [];
  const idx = shots.findIndex((s) => s.interval.start_ms <= currentMs && currentMs < s.interval.end_ms);
  const selIdx = selection ? shots.findIndex((s) => overlaps(s.interval, selection) && s.interval.start_ms <= selection.start_ms + 1)
    : idx;
  const cur = selIdx >= 0 ? selIdx : Math.max(0, idx);
  useEffect(() => { document.getElementById(`shot-${cur}`)?.scrollIntoView({ block: "nearest", inline: "center" }); }, [cur]);
  if (q.isLoading) return <p className="muted">Loading shots…</p>;
  if (!shots.length) return <p className="muted">No shot data in this run.</p>;
  return (
    <div className="shots">
      <div className="strip" ref={stripRef}>
        {shots.map((s, i) => {
          const len = s.interval.end_ms - s.interval.start_ms;
          const flagged = issues.some((x) => x.review_status !== "dismissed" && overlaps(x.affected_interval, s.interval));
          return (
            <button key={s.shot_id} id={`shot-${i}`} className={`tile ${i === cur ? "sel" : ""} ${flagged ? "flag" : ""}`}
              onClick={() => focus(s.interval, null)} title={`shot ${i + 1} · ${fmt(s.interval.start_ms)} · ${(len / 1000).toFixed(1)} s`}>
              {s.thumb ? <img loading="lazy" src={api.artifactUrl(runId, s.thumb.artifact_id)} alt="" /> : <span className="noimg">no still</span>}
              <span className="cap"><span className="mono">{fmt(s.interval.start_ms).replace(/\.\d$/, "")}</span><span>{(len / 1000).toFixed(1)}s</span></span>
            </button>);
        })}
      </div>
      <ShotDetail runId={runId} shot={shots[cur]} n={cur + 1} issues={issues} segments={segments} visualPending={visualPending} />
    </div>
  );
}
