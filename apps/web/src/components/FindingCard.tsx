import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { usePlayhead } from "../store";
import { MEASURE_LABEL, type UFinding } from "./findings";
import { Spinner } from "./Spinner";
import { clock } from "./TimeChart";

const SEV_WORD = { high: "Look first", medium: "Worth a look", low: "Minor" } as const;

export function SevTag({ sev }: { sev: "high" | "medium" | "low" }) {
  return <span className={`sevtag ${sev}`}><span className={`sevdot ${sev}`} aria-hidden />{SEV_WORD[sev]}</span>;
}

function fmtMeasure(k: string, v: unknown): string {
  if (v === null || v === undefined) return "Not measured";
  if (Array.isArray(v)) return v.length ? v.slice(0, 12).join(", ") + (v.length > 12 ? ` +${v.length - 12} more` : "") : "none";
  if (typeof v === "number") return k.endsWith("_ms") ? clock(v) : Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === "object") return JSON.stringify(v).slice(0, 120);
  return String(v);
}

/** One finding, always in the same order: title → what happens → why it may lose viewers → what to do → keep this → evidence. */
export function FindingCard({ f, runId, n, onEvidence, selected }: { f: UFinding; runId: string; n?: number; onEvidence?: (issueId: string) => void; selected?: boolean }) {
  const focus = usePlayhead((s) => s.focus);
  const qc = useQueryClient();
  const [more, setMore] = useState(false);
  const review = useMutation({
    mutationFn: (status: string) => api.review(runId, f.issue!.issue_id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["issues", runId] }),
  });
  const iv = { start_ms: f.start_ms, end_ms: f.end_ms };
  const go = () => focus(iv, f.issue?.issue_id ?? null);
  const long = f.quote.length > 260;
  const quote = !long || more ? f.quote : f.quote.slice(0, 240).replace(/\s+\S*$/, "") + "…";
  const measures = Object.entries(f.measurements).filter(([, v]) => v !== undefined);
  const status = f.issue?.review_status;
  return (
    <article className={`fcard ${f.severity} ${selected ? "selected" : ""}`} id={`f-${f.id}`}>
      <header className="fcard-head">
        {n !== undefined && <span className="fcard-n num" aria-hidden>{n}</span>}
        <div className="fcard-title">
          <h4>{f.title}</h4>
          <div className="fcard-meta"><SevTag sev={f.severity} /><span className="dotsep" />{f.groupLabel}
            {status && status !== "open" && <><span className="dotsep" /><span className="pill ok">{status === "accepted" ? "In edit plan" : status}</span></>}</div>
        </div>
        <button className="time" onClick={go} title="Jump the video here">{clock(f.start_ms)}–{clock(f.end_ms)}</button>
      </header>
      <dl className="fcard-body">
        <div><dt>What happens</dt><dd>
          {f.quote ? <blockquote>“{quote}”{long && <button className="link more" onClick={() => setMore(!more)}>{more ? "Show less" : "Show all"}</button>}</blockquote>
            : <span className="faint">No transcript text in this interval.</span>}
          {f.earlierQuote && <p className="earlier"><span className="faint">Said earlier{f.earlierStartMs !== undefined ? <> at <button className="link num" onClick={() => focus({ start_ms: f.earlierStartMs!, end_ms: f.earlierStartMs! + 5000 }, null)}>{clock(f.earlierStartMs)}</button></> : ""}:</span> “{f.earlierQuote}”</p>}
        </dd></div>
        {f.mechanism && <div><dt>Why it may lose viewers</dt><dd>{f.mechanism}</dd></div>}
        {f.suggestion && <div><dt>What to do</dt><dd>{f.suggestion}</dd></div>}
        {f.preserve && <div className="keep"><dt>Keep this</dt><dd>{f.preserve}</dd></div>}
      </dl>
      <details className="fcard-ev">
        <summary>Evidence &amp; alternative explanation</summary>
        <div className="fcard-ev-body">
          <p><span className="faint">Evidence strength:</span> {f.strength}{f.needsReanalysis ? " · the effect of an edit is unknown until the edited video is analysed again" : ""}</p>
          {f.counter && <p><span className="faint">Another explanation:</span> {f.counter}</p>}
          {measures.length > 0 && <table className="kv-table"><tbody>{measures.map(([k, v]) => <tr key={k}><th>{MEASURE_LABEL[k] ?? k.replace(/_/g, " ")}</th><td className="num">{fmtMeasure(k, v)}</td></tr>)}</tbody></table>}
          {f.source === "model" && <p className="faint">A rule-based candidate from the transcript. It points to a passage worth reviewing; it doesn't prove viewers leave.</p>}
        </div>
      </details>
      {f.issue && <div className="fcard-actions">
        {onEvidence && <button onClick={() => onEvidence(f.issue!.issue_id)}>View evidence</button>}
        {status !== "accepted"
          ? <button className="soft" disabled={review.isPending} onClick={() => review.mutate("accepted")}>{review.isPending && review.variables === "accepted" && <Spinner />}{f.issue.suggestions.length ? "Add to edit plan" : "Accept"}</button>
          : <button className="quiet" disabled={review.isPending} onClick={() => review.mutate("open")}>{review.isPending && <Spinner />}Remove from plan</button>}
        {status !== "dismissed" && <button className="quiet" disabled={review.isPending} onClick={() => review.mutate("dismissed")}>{review.isPending && review.variables === "dismissed" && <Spinner />}Dismiss</button>}
        {review.error && <span className="err">{(review.error as Error).message}</span>}
      </div>}
    </article>
  );
}
