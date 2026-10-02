import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, fmt, type Issue, type Segment } from "../api";
import { usePlayhead } from "../store";
import { issueLabel } from "./Timeline";

const OP: Record<string, string> = { cut: "Cut", move: "Move", rewrite: "Rewrite", insert_visual: "Add visual", adjust_audio: "Fix audio" };

function originalText(segments: Segment[], iv: { start_ms: number; end_ms: number } | null) {
  if (!iv) return "";
  return segments.filter((s) => s.interval.end_ms > iv.start_ms && s.interval.start_ms < iv.end_ms).map((s) => s.text).join(" ");
}

function Evidence({ runId, id }: { runId: string; id: string }) {
  const q = useQuery({ queryKey: ["ev", runId, id], queryFn: () => api.evidence(runId, id) });
  const { seek } = usePlayhead();
  if (q.isLoading) return <div className="faint">loading evidence…</div>;
  if (q.error || !q.data) return <div className="err">evidence unavailable</div>;
  const { evidence: e, ref, frames } = q.data;
  const text = (ref?.text ?? ref?.statement ?? "") as string;
  return (
    <div className="edit">
      <div className="row">
        <span className="pill">{e.kind === "signal" ? "measured" : e.kind}</span>
        {e.precision !== "word" && <span className="pill" title="timing precision">{e.precision} timing</span>}
        <button className="time" onClick={(ev) => { ev.stopPropagation(); seek(e.interval.start_ms); }}>
          {fmt(e.interval.start_ms)}–{fmt(e.interval.end_ms)}</button>
      </div>
      {/* transcript and model text are untrusted: rendered as text only */}
      {e.quote ? <div className="quote-orig">“{e.quote}”</div> : text ? <div className="quote-orig">{text}</div> : null}
      {e.kind === "signal" && ref && <div className="muted mono">{String(ref.name)} {JSON.stringify(ref.value).slice(0, 140)} {String(ref.unit ?? "")}</div>}
      {!!frames.length && <div className="frames">{frames.slice(0, 8).map((f) => (
        <img key={f.frame_id} src={api.artifactUrl(runId, f.artifact_id)} alt={`sampled frame at ${fmt(f.at_ms)}`}
          title={`sampled still at ${fmt(f.at_ms)}`} onClick={(ev) => { ev.stopPropagation(); seek(f.at_ms); }} />))}</div>}
    </div>
  );
}

export function IssueCard({ runId, issue, segments }: { runId: string; issue: Issue; segments: Segment[] }) {
  const { seek, select, selectedIssue } = usePlayhead();
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const ref = useRef<HTMLDivElement>(null);
  const review = useMutation({
    mutationFn: (status: string) => api.review(runId, issue.issue_id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["issues", runId] }),
  });
  const selected = selectedIssue === issue.issue_id;
  useEffect(() => { if (selected) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [selected]);
  const iv = issue.affected_interval;
  const stop = (f: () => void) => (e: React.MouseEvent) => { e.stopPropagation(); f(); };
  return (
    <div ref={ref} className={`issue ${issue.severity} ${selected ? "selected" : ""} ${issue.review_status === "dismissed" ? "dismissed" : ""}`}
      onClick={() => select(issue.issue_id)}>
      <div className="row">
        <h3 style={{ marginRight: "auto" }}>{issueLabel(issue.type)}</h3>
        <span className={`pill ${issue.severity}`}>{issue.severity}</span>
        <span className={`pill ${issue.evidence_status}`} title="evidence status">{issue.evidence_status}</span>
        {issue.review_status !== "open" && <span className="pill amber">{issue.review_status}</span>}
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button className="time" onClick={stop(() => seek(iv.start_ms))}>{fmt(iv.start_ms)}–{fmt(iv.end_ms)}</button>
        {issue.comparison_intervals?.map((c, i) => (
          <button key={i} className="time" title="earlier occurrence" onClick={stop(() => seek(c.start_ms))}>vs {fmt(c.start_ms)}</button>))}
        <span className="faint" style={{ fontSize: 13 }}>{issue.risk_track} track</span>
      </div>
      <p>{issue.explanation}</p>
      <p className="muted"><b>Why it might be fine:</b> {issue.counter_explanation}</p>
      {!issue.suggestions.length && (
        <div className="edit none">No safe edit proposed: the model's edit would have removed points or the hook, so it was discarded. Judge this one by hand.</div>)}
      {issue.suggestions.map((s) => (
        <div className="edit" key={s.suggestion_id}>
          <div className="row"><b>{OP[s.operation]}</b>
            {s.source_interval && <button className="time" onClick={stop(() => seek(s.source_interval!.start_ms))}>
              {fmt(s.source_interval.start_ms)}–{fmt(s.source_interval.end_ms)}</button>}
            {s.destination_ms !== null && s.operation === "move" && <span className="mono muted">→ {fmt(s.destination_ms)}</span>}
            {s.requires_reanalysis && <span className="pill" title="effect unknown until the edited video is reanalysed">needs reanalysis</span>}
          </div>
          {(s.operation === "rewrite" || s.operation === "cut") && s.source_interval &&
            <div className="quote-orig"><span className="faint">{s.operation === "cut" ? "removes: " : "original: "}</span>{originalText(segments, s.source_interval)}</div>}
          {s.proposed_text && <div className="quote-new"><span className="faint">proposed: </span>{s.proposed_text}</div>}
          <div className="muted" style={{ fontSize: 13 }}>{s.rationale}</div>
        </div>
      ))}
      <div className="actions">
        <button className="ghost" onClick={stop(() => setOpen(!open))}>{open ? "Hide" : "Show"} evidence ({issue.evidence_ids.length})</button>
        <span style={{ flex: 1 }} />
        {issue.review_status !== "accepted"
          ? <button className="amber" onClick={stop(() => review.mutate("accepted"))}>Accept</button>
          : <button onClick={stop(() => review.mutate("open"))}>Undo accept</button>}
        {issue.review_status !== "dismissed"
          ? <button onClick={stop(() => review.mutate("dismissed"))}>Dismiss</button>
          : <button onClick={stop(() => review.mutate("open"))}>Restore</button>}
      </div>
      {open && issue.evidence_ids.map((id) => <Evidence key={id} runId={runId} id={id} />)}
    </div>
  );
}

const SEV = ["all", "high", "medium", "low"] as const;
const STATUS = ["all", "open", "accepted", "dismissed"] as const;

export function IssueList({ runId, issues, segments }: { runId: string; issues: Issue[]; segments: Segment[] }) {
  const [sev, setSev] = useState<(typeof SEV)[number]>("all");
  const [status, setStatus] = useState<(typeof STATUS)[number]>("all");
  const [track, setTrack] = useState("all");
  const tracks = ["all", ...Array.from(new Set(issues.map((i) => i.risk_track)))];
  const shown = issues.filter((i) => (sev === "all" || i.severity === sev) && (status === "all" || i.review_status === status)
    && (track === "all" || i.risk_track === track));
  return (
    <div>
      <div className="filters">
        {SEV.map((s) => <button key={s} className={`chip ${sev === s ? "on" : ""}`} onClick={() => setSev(s)}>{s}</button>)}
        <span style={{ width: 8 }} />
        {STATUS.map((s) => <button key={s} className={`chip ${status === s ? "on" : ""}`} onClick={() => setStatus(s)}>{s}</button>)}
        <select value={track} onChange={(e) => setTrack(e.target.value)} style={{ padding: "4px 10px", fontSize: 13 }} aria-label="Track">
          {tracks.map((t) => <option key={t} value={t}>{t === "all" ? "all tracks" : `${t} track`}</option>)}
        </select>
      </div>
      <div className="issues">
        {!issues.length && <p className="muted">No accepted issues. That is not proof the video is flawless: check coverage below.</p>}
        {!!issues.length && !shown.length && <p className="muted">No findings match these filters.</p>}
        {shown.map((i) => <IssueCard key={i.issue_id} runId={runId} issue={i} segments={segments} />)}
      </div>
    </div>
  );
}
