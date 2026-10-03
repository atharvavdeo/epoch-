import type { Prediction, Relations, Segment, Signal } from "../api";
import { usePlayhead } from "../store";
import { SevTag } from "./FindingCard";
import type { UFinding } from "./findings";
import { IconArrow, IconChat } from "./Icons";
import { featureLabel } from "./labels";
import { clock, EstimateBadge } from "./TimeChart";

const pc = (v: number) => `${Math.round(v * 100)}%`;

/** "What is going on right here?" for the playhead (or the selected interval). */
export function AtThisMoment({ segments, chapters, findings, pred, rel, onOpenFinding, onAsk }: {
  segments: Segment[]; chapters: Signal[]; findings: UFinding[]; pred?: Prediction; rel?: Relations;
  onOpenFinding: (f: UFinding) => void; onAsk: () => void;
}) {
  const { currentMs: t, selection, focus } = usePlayhead();
  const chapter = chapters.find((c) => c.interval.start_ms <= t && t < c.interval.end_ms);
  const ordered = segments;
  const k = ordered.findIndex((s) => s.interval.start_ms <= t && t < s.interval.end_ms + 400);
  const said = k >= 0 ? ordered[k] : [...ordered].reverse().find((s) => s.interval.start_ms <= t);
  const next = said ? ordered[ordered.indexOf(said) + 1] : ordered[0];
  const ps = pred?.per_second[Math.min(pred.per_second.length - 1, Math.max(0, Math.floor(t / 1000)))];
  const causes = ps ? Object.entries(ps.contributions).sort((a, b) => b[1] - a[1]).slice(0, 2) : [];
  const win = selection ?? { start_ms: Math.max(0, t - 1000), end_ms: t + 1000 };
  const here = findings.filter((f) => f.start_ms < win.end_ms && win.start_ms < f.end_ms).slice(0, 3);
  const q = rel?.questions.find((x) => Math.abs(x.question.start_ms - t) < 8000);
  return (
    <div className="atm" aria-live="polite">
      <div className="atm-top">
        <span className="kicker">At this moment</span>
        <span className="atm-time num">{clock(t)}</span>
      </div>
      {chapter && <div className="atm-chapter">{String((chapter.value as { label?: string })?.label ?? "")}</div>}
      <section>
        {said ? <p className="atm-said">“{said.text}”</p> : <p className="faint">No speech here.</p>}
        {next && <button className="link atm-next" onClick={() => focus(next.interval, null)}>Next: {next.text.slice(0, 60)}{next.text.length > 60 ? "…" : ""}</button>}
      </section>
      {ps && <section className="atm-est">
        <div className="atm-big"><b className="num">{pc(ps.retention)}</b><span>still watching <EstimateBadge /></span></div>
        {causes.length > 0 && <p className="atm-why">Why: <b>{causes.map(([c]) => featureLabel(c)).join(", ")}</b></p>}
        {q && <p className="atm-why faint">A question is asked here{q.answer ? <> · picked up at <button className="link num" onClick={() => focus({ start_ms: q.answer!.start_ms, end_ms: q.answer!.end_ms }, null)}>{clock(q.answer.start_ms)}</button></> : ""}</p>}
      </section>}
      <section>
        {here.length ? here.map((f) => (
          <button key={f.id} className="atm-finding" onClick={() => onOpenFinding(f)}>
            <span className="atm-f-main"><b>{f.title}</b><SevTag sev={f.severity} /></span><IconArrow size={16} />
          </button>))
          : <p className="faint atm-none">Nothing flagged here.</p>}
      </section>
      <button className="atm-ask" onClick={onAsk}><IconChat size={17} />Ask about this moment</button>
    </div>
  );
}
