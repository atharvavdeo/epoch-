import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, fmt, type Issue, type RiskBin, type Segment } from "../api";
import { overlaps, usePlayhead } from "../store";
import { issueLabel } from "./Timeline";

const OP: Record<string, string> = { cut: "Cut", move: "Move", rewrite: "Rewrite", insert_visual: "Add visual", adjust_audio: "Fix audio" };
const SEV_ORDER = { high: 0, medium: 1, low: 2 } as const;
const TRACKS = ["narrative", "visual", "pacing", "text", "technical"];

export const prioritise = (items: Issue[]) => [...items].sort((a, b) =>
  (a.review_status === "dismissed" ? 1 : 0) - (b.review_status === "dismissed" ? 1 : 0)
  || SEV_ORDER[a.severity] - SEV_ORDER[b.severity]
  || (a.evidence_status === "supported" ? 0 : 1) - (b.evidence_status === "supported" ? 0 : 1)
  || a.affected_interval.start_ms - b.affected_interval.start_ms);

export function originalText(segments: Segment[], iv: { start_ms: number; end_ms: number } | null) {
  if (!iv) return "";
  return segments.filter((s) => s.interval.end_ms > iv.start_ms && s.interval.start_ms < iv.end_ms).map((s) => s.text).join(" ");
}

export function Evidence({ runId, id }: { runId: string; id: string }) {
  const q = useQuery({ queryKey: ["ev", runId, id], queryFn: () => api.evidence(runId, id) });
  const { focus, seek } = usePlayhead();
  if (q.isLoading) return <div className="faint">loading evidence…</div>;
  if (q.error || !q.data) return <div className="err">evidence unavailable</div>;
  const { evidence: e, ref, frames } = q.data;
  const text = (ref?.text ?? ref?.statement ?? "") as string;
  const kind = e.kind === "signal" ? "measured" : e.kind === "observation" ? "observed (VLM)" : e.kind;
  return (
    <div className="ev">
      <div className="row">
        <span className="pill">{kind}</span>
        <button className="time" onClick={() => focus(e.interval, undefined)}>{fmt(e.interval.start_ms)}–{fmt(e.interval.end_ms)}</button>
        {e.precision !== "word" && <span className="faint" style={{ fontSize: 12 }}>{e.precision} timing</span>}
      </div>
      {/* transcript and model text are untrusted: rendered as text only */}
      {e.quote ? <div className="quote-orig">“{e.quote}”</div> : text ? <div className="quote-orig">{text}</div> : null}
      {e.kind === "signal" && ref && <div className="muted" style={{ fontSize: 13 }}>{String(ref.name).replace(/_/g, " ")}:{" "}
        <span className="mono">{JSON.stringify(ref.value).slice(0, 140)}</span> {String(ref.unit ?? "")}</div>}
      {!!frames.length && <div className="frames">{frames.slice(0, 8).map((f) => (
        <img key={f.frame_id} src={api.artifactUrl(runId, f.artifact_id)} alt={`sampled still at ${fmt(f.at_ms)}`}
          title={`sampled still at ${fmt(f.at_ms)}`} onClick={() => seek(f.at_ms)} />))}</div>}
    </div>
  );
}

function useReview(runId: string, issueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (status: string) => api.review(runId, issueId, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["issues", runId] }),
  });
}

/** Five questions, in the order an editor asks them. */
export function FindingDetail({ runId, issue, segments, risk }: { runId: string; issue: Issue | undefined; segments: Segment[]; risk: RiskBin[] }) {
  const { focus } = usePlayhead();
  const review = useReview(runId, issue?.issue_id ?? "");
  if (!issue) return <p className="muted">Select a finding on the timeline or in the list.</p>;
  const iv = issue.affected_interval;
  const bins = risk.filter((b) => overlaps(b.interval, iv));
  const notInspected = TRACKS.filter((t) => bins.some((b) => (b.track_values[t]?.coverage ?? 0) < 0.999));
  return (
    <div className="fd">
      <div className="row" style={{ gap: 8 }}>
        <h2 style={{ marginRight: "auto" }}>{issueLabel(issue.type)}</h2>
        <span className={`pill ${issue.severity}`}>{issue.severity}</span>
        <span className={`pill ${issue.evidence_status}`} title="Supported: measured or quoted evidence. Provisional: weaker evidence.">
          {issue.evidence_status === "supported" ? "Supported" : "Provisional"}</span>
        {issue.review_status !== "open" && <span className="pill amber">{issue.review_status}</span>}
      </div>
      <section><h4>What happened?</h4><p>{issue.explanation}</p></section>
      <section><h4>Where?</h4>
        <div className="row">
          <button className="time" onClick={() => focus(iv, issue.issue_id)}>{fmt(iv.start_ms)}–{fmt(iv.end_ms)}</button>
          <span className="faint">{((iv.end_ms - iv.start_ms) / 1000).toFixed(1)} s · {issue.risk_track} track</span>
          {issue.comparison_intervals?.map((c, k) => (
            <button key={k} className="time" title="the earlier passage it is compared with" onClick={() => focus(c, issue.issue_id)}>
              compare {fmt(c.start_ms)}–{fmt(c.end_ms)}</button>))}
        </div>
        {!!notInspected.length && <div className="uninspected">Uninspected here: {notInspected.join(", ")}. This finding does not
          say those parts are fine.</div>}
      </section>
      <section><h4>What supports this?</h4>
        {issue.evidence_ids.map((id) => <Evidence key={id} runId={runId} id={id} />)}
      </section>
      <section><h4>What might explain it?</h4><p className="muted">{issue.counter_explanation}</p></section>
      <section><h4>What edit is proposed?</h4>
        {!issue.suggestions.length && <div className="edit none">No safe edit proposed: the model's edit would have removed points,
          examples or the hook, so it was discarded. Judge this one by hand.</div>}
        {issue.suggestions.map((s) => (
          <div className="edit" key={s.suggestion_id}>
            <div className="row"><b>{OP[s.operation]}</b>
              {s.source_interval && <button className="time" onClick={() => focus(s.source_interval!, issue.issue_id)}>
                {fmt(s.source_interval.start_ms)}–{fmt(s.source_interval.end_ms)}</button>}
              {s.destination_ms !== null && s.operation === "move" && <span className="mono muted">→ {fmt(s.destination_ms)}</span>}
              {s.requires_reanalysis && <span className="pill" title="effect unknown until the edited video is analysed again">needs reanalysis</span>}
            </div>
            {(s.operation === "rewrite" || s.operation === "cut") && s.source_interval &&
              <div className="quote-orig"><span className="faint">{s.operation === "cut" ? "removes: " : "original: "}</span>{originalText(segments, s.source_interval)}</div>}
            {s.proposed_text && <div className="quote-new"><span className="pill amber" style={{ marginRight: 6 }}>proposed text</span>{s.proposed_text}</div>}
            <div className="muted" style={{ fontSize: 13 }}>{s.rationale}</div>
          </div>))}
        <div className="actions">
          {issue.review_status !== "accepted"
            ? <button className="amber" onClick={() => review.mutate("accepted")} disabled={review.isPending}>
                {issue.suggestions.length ? "Add to edit plan" : "Accept finding"}</button>
            : <button onClick={() => review.mutate("open")}>Remove from plan</button>}
          {issue.review_status !== "dismissed"
            ? <button onClick={() => review.mutate("dismissed")}>Dismiss</button>
            : <button onClick={() => review.mutate("open")}>Restore</button>}
        </div>
      </section>
    </div>
  );
}

const SEV = ["all", "high", "medium", "low"] as const;
const STATUS = ["all", "open", "accepted", "dismissed"] as const;

/** Compact ranked list; selecting a row moves the shared playhead/selection. */
export function FindingsList({ issues }: { issues: Issue[] }) {
  const { focus, selectedIssue } = usePlayhead();
  const [sev, setSev] = useState<(typeof SEV)[number]>("all");
  const [status, setStatus] = useState<(typeof STATUS)[number]>("all");
  const shown = prioritise(issues).filter((i) => (sev === "all" || i.severity === sev) && (status === "all" || i.review_status === status));
  return (
    <div>
      <div className="filters">
        {SEV.map((s) => <button key={s} className={`chip ${sev === s ? "on" : ""}`} onClick={() => setSev(s)}>{s}</button>)}
        <span style={{ width: 6 }} />
        {STATUS.map((s) => <button key={s} className={`chip ${status === s ? "on" : ""}`} onClick={() => setStatus(s)}>{s}</button>)}
      </div>
      {!issues.length && <p className="muted">No accepted issues. That is not proof the video is flawless: check what was inspected.</p>}
      {!!issues.length && !shown.length && <p className="muted">No findings match these filters.</p>}
      <div className="flist">
        {shown.map((i) => (
          <button key={i.issue_id} className={`frow ${i.severity} ${selectedIssue === i.issue_id ? "sel" : ""} ${i.review_status}`}
            onClick={() => focus(i.affected_interval, i.issue_id)}>
            <span className="fsev" />
            <span className="ftitle">{issueLabel(i.type)}</span>
            <span className="mono faint">{fmt(i.affected_interval.start_ms)}</span>
            <span className={`pill ${i.evidence_status}`}>{i.evidence_status === "supported" ? "Supported" : "Provisional"}</span>
            {i.review_status !== "open" && <span className="pill amber">{i.review_status === "accepted" ? "in plan" : "dismissed"}</span>}
          </button>))}
      </div>
    </div>
  );
}
