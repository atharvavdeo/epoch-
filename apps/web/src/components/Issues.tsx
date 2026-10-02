import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, fmt, type Issue, type Segment } from "../api";
import { usePlayhead } from "../store";

const LABEL: Record<string, string> = {
  delayed_payoff: "Delayed payoff", slow_intro: "Slow intro", unnecessary_repetition: "Repetition", tangent: "Tangent",
  unresolved_promise: "Unresolved title promise", dead_air: "Dead air", rushed_delivery: "Rushed delivery",
  visual_stagnation: "Visual stagnation", technical_visual_fault: "Visual fault", technical_audio_fault: "Audio fault",
  disruptive_cta: "Disruptive CTA", visual_speech_mismatch: "Visual/speech mismatch", unreadable_text: "Unreadable text",
  visual_overload: "Visual overload", weak_transition: "Weak transition",
};
const OP: Record<string, string> = { cut: "Cut", move: "Move", rewrite: "Rewrite", insert_visual: "Add visual", adjust_audio: "Fix audio" };

function originalText(segments: Segment[], iv: { start_ms: number; end_ms: number } | null) {
  if (!iv) return "";
  return segments.filter((s) => s.interval.end_ms > iv.start_ms && s.interval.start_ms < iv.end_ms).map((s) => s.text).join(" ");
}

function Evidence({ runId, id }: { runId: string; id: string }) {
  const q = useQuery({ queryKey: ["ev", runId, id], queryFn: () => api.evidence(runId, id) });
  const { seek } = usePlayhead();
  if (q.isLoading) return <div className="muted">loading evidence…</div>;
  if (q.error || !q.data) return <div className="err">evidence unavailable</div>;
  const { evidence: e, ref, frames } = q.data;
  const text = (ref?.text ?? ref?.statement ?? "") as string;
  return (
    <div className="edit">
      <div className="row"><span className="pill">{e.kind}</span><span className="pill">{e.precision}</span>
        <button onClick={() => seek(e.interval.start_ms)} className="mono">{fmt(e.interval.start_ms)}–{fmt(e.interval.end_ms)}</button></div>
      {e.quote && <div className="quote-orig">“{e.quote}”</div>}
      {!e.quote && text && <div className="quote-orig">{text}</div>}
      {e.kind === "signal" && ref && <div className="muted mono">{String(ref.name)}: {JSON.stringify(ref.value).slice(0, 120)} {String(ref.unit ?? "")}</div>}
      {!!frames.length && <div className="frames">{frames.slice(0, 8).map((f) => (
        <img key={f.frame_id} src={api.artifactUrl(runId, f.artifact_id)} alt={`sampled frame at ${fmt(f.at_ms)}`}
          title={`frame at ${fmt(f.at_ms)} (sampled still)`} onClick={() => seek(f.at_ms)} />))}</div>}
    </div>
  );
}

export function IssueCard({ runId, issue, segments }: { runId: string; issue: Issue; segments: Segment[] }) {
  const { seek, select, selectedIssue } = usePlayhead();
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const review = useMutation({
    mutationFn: (status: string) => api.review(runId, issue.issue_id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["issues", runId] }),
  });
  const iv = issue.affected_interval;
  return (
    <div className={`card issue ${issue.severity} ${selectedIssue === issue.issue_id ? "selected" : ""}`}
      onClick={() => select(issue.issue_id)}>
      <div className="row">
        <h3 style={{ marginRight: "auto" }}>{LABEL[issue.type] ?? issue.type}</h3>
        <span className={`pill ${issue.severity}`}>{issue.severity}</span>
        <span className={`pill ${issue.evidence_status}`} title="evidence status">{issue.evidence_status}</span>
      </div>
      <div className="row" style={{ marginTop: 4 }}>
        <button className="mono" onClick={() => seek(iv.start_ms)}>{fmt(iv.start_ms)}–{fmt(iv.end_ms)}</button>
        {issue.comparison_intervals?.map((c, i) => (
          <button key={i} className="mono" title="earlier occurrence" onClick={() => seek(c.start_ms)}>vs {fmt(c.start_ms)}</button>))}
        {issue.modality_tags.map((m) => <span key={m} className="pill">{m}</span>)}
        {issue.review_status !== "open" && <span className="pill warn">{issue.review_status}</span>}
      </div>
      <p style={{ margin: "8px 0 4px" }}>{issue.explanation}</p>
      <p className="muted" style={{ margin: 0 }}><b>Why it might be fine:</b> {issue.counter_explanation}</p>
      {issue.suggestions.map((s) => (
        <div className="edit" key={s.suggestion_id}>
          <div className="row"><b>{OP[s.operation]}</b>
            {s.source_interval && <span className="mono muted">{fmt(s.source_interval.start_ms)}–{fmt(s.source_interval.end_ms)}</span>}
            {s.destination_ms !== null && s.operation === "move" && <span className="mono muted">→ {fmt(s.destination_ms)}</span>}
            {s.requires_reanalysis && <span className="pill" title="effect unknown until the edited video is reanalysed">needs reanalysis</span>}
          </div>
          {s.operation === "rewrite" && <div className="quote-orig"><span className="muted">original: </span>{originalText(segments, s.source_interval)}</div>}
          {s.proposed_text && <div className="quote-new"><span className="muted">proposed: </span>{s.proposed_text}</div>}
          <div className="muted">{s.rationale}</div>
        </div>
      ))}
      <div className="row" style={{ marginTop: 8 }}>
        <button onClick={(e) => { e.stopPropagation(); setOpen(!open); }}>{open ? "Hide" : "Show"} evidence ({issue.evidence_ids.length})</button>
        <button onClick={(e) => { e.stopPropagation(); review.mutate("accepted"); }}>Accept</button>
        <button onClick={(e) => { e.stopPropagation(); review.mutate("dismissed"); }}>Dismiss</button>
      </div>
      {open && issue.evidence_ids.map((id) => <Evidence key={id} runId={runId} id={id} />)}
    </div>
  );
}

export function IssueList({ runId, issues, segments }: { runId: string; issues: Issue[]; segments: Segment[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? issues : issues.slice(0, 5);
  return (
    <div className="issues">
      {!issues.length && <p className="muted">No accepted issues. This is not proof the video is flawless: check coverage below.</p>}
      {shown.map((i) => <IssueCard key={i.issue_id} runId={runId} issue={i} segments={segments} />)}
      {issues.length > 5 && <button onClick={() => setAll(!all)}>{all ? "Show top 5" : `Show all ${issues.length} findings`}</button>}
    </div>
  );
}
