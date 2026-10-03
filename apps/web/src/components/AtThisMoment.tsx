import { fmt, type Issue, type Prediction, type Relations, type Segment, type Signal } from "../api";
import { overlaps, usePlayhead } from "../store";
import { FEATURE_LABEL } from "./Prediction";
import { issueLabel } from "./Timeline";

const s2 = (ms: number) => fmt(ms).replace(/\.\d$/, "");
const pc = (v: number) => `${Math.round(v * 100)}%`;

/** One panel that answers "what is going on right here?" for the playhead (or the selected interval). */
export function AtThisMoment({ segments, chapters, issues, pred, rel, onOpenFinding, onAsk }: {
  segments: Segment[]; chapters: Signal[]; issues: Issue[]; pred?: Prediction; rel?: Relations;
  onOpenFinding: (id: string) => void; onAsk: () => void;
}) {
  const { currentMs, selection, focus } = usePlayhead();
  const t = currentMs;
  const chapter = chapters.find((c) => c.interval.start_ms <= t && t < c.interval.end_ms);
  const ordered = [...segments].sort((a, b) => a.interval.start_ms - b.interval.start_ms);
  const k = ordered.findIndex((s) => s.interval.start_ms <= t && t < s.interval.end_ms + 400);
  const said = k >= 0 ? ordered[k] : ordered.filter((s) => s.interval.start_ms <= t).pop();
  const next = said ? ordered[ordered.indexOf(said) + 1] : ordered[0];
  const ps = pred?.per_second[Math.min(pred.per_second.length - 1, Math.max(0, Math.floor(t / 1000)))];
  const causes = ps ? Object.entries(ps.contributions).sort((a, b) => b[1] - a[1]).slice(0, 2) : [];
  const win = { start_ms: Math.max(0, t - 1000), end_ms: t + 1000 };
  const here = issues.filter((i) => i.review_status !== "dismissed" && overlaps(i.affected_interval, selection ?? win));
  const q = rel?.questions.find((x) => Math.abs(x.question.start_ms - t) < 8000 || (x.answer && Math.abs(x.answer.start_ms - t) < 8000));
  const abstract = rel?.abstract_stretches.find((x) => x.start_ms <= t && t < x.end_ms);
  const unpunct = said && !/[.?!A-Z]/.test(said.text);

  return (
    <div className="atm" aria-live="polite">
      <div className="atm-top">
        <span className="atm-label">At this moment</span>
        <span className="atm-time mono">{s2(t)}</span>
      </div>
      {chapter && <div className="atm-chapter">{String((chapter.value as { label?: string })?.label ?? "")}</div>}

      <section>
        <h4>Being said</h4>
        {said ? <p className="atm-said">“{said.text}”</p> : <p className="faint">No speech here.</p>}
        {next && <button className="quiet atm-next" onClick={() => focus(next.interval, null)}>
          Next: <span className="faint">{next.text.slice(0, 70)}{next.text.length > 70 ? "…" : ""}</span></button>}
        {unpunct && <p className="faint" style={{ fontSize: 12, margin: 0 }}>Transcript here has no punctuation (speech recognition output).</p>}
      </section>

      {ps && <section>
        <h4>Scenario <span className="pill uncal">uncalibrated</span></h4>
        <div className="atm-big"><b>{pc(ps.retention)}</b> <span className="faint">assumed remaining ({pc(ps.lower)}–{pc(ps.upper)})</span></div>
        {causes.length > 0
          ? <p className="atm-why">Scenario drivers here: <b>{causes.map(([c]) => FEATURE_LABEL[c] ?? c).join(", ")}</b></p>
          : <p className="atm-why faint">No extra loss assumed here beyond the baseline.</p>}
        {ps.protective.length > 0 && <p className="atm-why faint">Potential protective cues: {ps.protective.map((c) => FEATURE_LABEL[c] ?? c).join(", ")}</p>}
      </section>}

      {(q || abstract) && <section>
        <h4>In the narration</h4>
        {q && <p className="atm-why">{Math.abs(q.question.start_ms - t) < 8000 ? "A question is asked here" : "This returns to a question from "}
          {Math.abs(q.question.start_ms - t) >= 8000 && <button className="link mono" onClick={() => focus({ start_ms: q.question.start_ms, end_ms: q.question.end_ms }, null)}>{s2(q.question.start_ms)}</button>}
          {Math.abs(q.question.start_ms - t) < 8000 && (q.answer
            ? <> · it is picked up at <button className="link mono" onClick={() => focus({ start_ms: q.answer!.start_ms, end_ms: q.answer!.end_ms }, null)}>{s2(q.answer.start_ms)}</button></>
            : q.kind === "framing" ? " · a framing question: the whole video answers it" : " · never returned to in words")}</p>}
        {abstract && <p className="atm-why">No concrete example for {Math.round((abstract.end_ms - abstract.start_ms) / 1000)} s here.</p>}
      </section>}

      <section>
        <h4>Findings here</h4>
        {here.length ? here.slice(0, 3).map((i) => (
          <button key={i.issue_id} className="atm-finding" onClick={() => onOpenFinding(i.issue_id)}>
            <span className={`sevdot ${i.severity}`} aria-hidden />
            <span>{issueLabel(i.type)}</span>
            <span className="faint">{i.severity} · {s2(i.affected_interval.start_ms)}</span>
            <span className="atm-go">View evidence ›</span>
          </button>))
          : <p className="faint" style={{ margin: 0 }}>None at this moment. That only means nothing was flagged, not that it was all inspected.</p>}
      </section>
      <div className="atm-actions"><button onClick={onAsk}>Ask about this moment</button></div>
    </div>
  );
}
