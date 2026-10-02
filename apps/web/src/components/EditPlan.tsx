import { fmt, type Issue, type Segment, type Suggestion } from "../api";
import { usePlayhead } from "../store";
import { issueLabel } from "./Timeline";

const OP: Record<string, string> = { cut: "Cut", move: "Move", rewrite: "Rewrite", insert_visual: "Add visual", adjust_audio: "Fix audio" };

type Row = { issue: Issue; s: Suggestion };

function originalText(segments: Segment[], iv: { start_ms: number; end_ms: number } | null) {
  if (!iv) return "";
  return segments.filter((s) => s.interval.end_ms > iv.start_ms && s.interval.start_ms < iv.end_ms).map((s) => s.text).join(" ");
}

function download(name: string, body: string, type: string) {
  const url = URL.createObjectURL(new Blob([body], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

const csvCell = (v: string) => `"${v.replace(/"/g, '""')}"`;

/** Accepted findings turned into an ordered list of edits the creator can carry into their editor. */
export function EditPlan({ issues, segments, title }: { issues: Issue[]; segments: Segment[]; title: string }) {
  const { seek } = usePlayhead();
  const accepted = issues.filter((i) => i.review_status === "accepted");
  const rows: Row[] = accepted.flatMap((issue) => issue.suggestions.map((s) => ({ issue, s })))
    .sort((a, b) => (a.s.source_interval?.start_ms ?? 0) - (b.s.source_interval?.start_ms ?? 0));
  const noEdit = accepted.filter((i) => !i.suggestions.length);
  const cutMs = rows.filter((r) => r.s.operation === "cut" && r.s.source_interval)
    .reduce((t, r) => t + (r.s.source_interval!.end_ms - r.s.source_interval!.start_ms), 0);
  const open = issues.filter((i) => i.review_status === "open").length;

  const asText = () => [`Edit plan — ${title}`, "", ...rows.map((r, n) => {
    const iv = r.s.source_interval;
    return [`${n + 1}. ${OP[r.s.operation]} ${iv ? `${fmt(iv.start_ms)}–${fmt(iv.end_ms)}` : ""}  (${issueLabel(r.issue.type)}, ${r.issue.severity})`,
      r.s.operation === "rewrite" ? `   original: ${originalText(segments, iv)}` : "",
      r.s.proposed_text ? `   proposed: ${r.s.proposed_text}` : "",
      `   why: ${r.s.rationale}`].filter(Boolean).join("\n");
  }), "", "Effect on retention is unknown until the edited video is analysed again."].join("\n");
  const asCsv = () => ["order,operation,start,end,issue,severity,proposed_text,rationale",
    ...rows.map((r, n) => [String(n + 1), OP[r.s.operation], r.s.source_interval ? fmt(r.s.source_interval.start_ms) : "",
      r.s.source_interval ? fmt(r.s.source_interval.end_ms) : "", issueLabel(r.issue.type), r.issue.severity,
      r.s.proposed_text ?? "", r.s.rationale].map(csvCell).join(","))].join("\n");

  return (
    <div>
      <div className="stats">
        <div className="stat"><span className="v">{rows.length}</span><span className="k">edits in plan</span></div>
        <div className="stat"><span className="v num">{fmt(cutMs)}</span><span className="k">removed by cuts</span></div>
        <div className="stat"><span className="v">{open}</span><span className="k">findings still to review</span></div>
      </div>
      {!accepted.length && (
        <p className="muted">Nothing accepted yet. Accept findings in the Findings tab and their edits appear here in timeline order.</p>)}
      {rows.map((r, n) => (
        <div className="plan-row" key={r.s.suggestion_id}>
          <span className="plan-n">{n + 1}</span>
          <div>
            <div style={{ fontWeight: 600 }}>{OP[r.s.operation]}</div>
            {r.s.source_interval && <button className="time" onClick={() => seek(r.s.source_interval!.start_ms)}>
              {fmt(r.s.source_interval.start_ms)}–{fmt(r.s.source_interval.end_ms)}</button>}
          </div>
          <div>
            <div className="muted" style={{ fontSize: 13 }}>{issueLabel(r.issue.type)} · {r.issue.severity}</div>
            {r.s.operation === "rewrite" && <div className="quote-orig">{originalText(segments, r.s.source_interval)}</div>}
            {r.s.proposed_text && <div className="quote-new">{r.s.proposed_text}</div>}
            <div style={{ fontSize: 14 }}>{r.s.rationale}</div>
          </div>
        </div>))}
      {!!noEdit.length && (
        <p className="faint" style={{ fontSize: 13 }}>{noEdit.length} accepted finding(s) have no safe automatic edit:
          {" "}{noEdit.map((i) => `${issueLabel(i.type)} ${fmt(i.affected_interval.start_ms)}`).join(", ")}. Handle these by hand.</p>)}
      {!!rows.length && (
        <div className="actions">
          <button className="amber" onClick={() => download("edit-plan.txt", asText(), "text/plain")}>Download as text</button>
          <button onClick={() => download("edit-plan.csv", asCsv(), "text/csv")}>Download CSV</button>
        </div>)}
      <p className="faint" style={{ fontSize: 13, marginTop: 12 }}>
        Effect on retention is unknown until the edited video is analysed again.</p>
    </div>
  );
}
