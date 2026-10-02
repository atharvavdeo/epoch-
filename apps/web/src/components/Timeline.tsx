import { useRef, useState } from "react";
import { fmt, type Issue, type RiskBin, type Signal } from "../api";
import { usePlayhead } from "../store";

const LABEL: Record<string, string> = {
  delayed_payoff: "Delayed payoff", slow_intro: "Slow intro", unnecessary_repetition: "Repetition", tangent: "Tangent",
  unresolved_promise: "Unresolved promise", dead_air: "Dead air", rushed_delivery: "Rushed delivery",
  visual_stagnation: "Visual stagnation", technical_visual_fault: "Visual fault", technical_audio_fault: "Audio fault",
  disruptive_cta: "Disruptive CTA",
};
export const issueLabel = (t: string) => LABEL[t] ?? t;

/** Full-width time axis under the player: chapters, findings, combined risk, playhead. */
export function Timeline({ duration, chapters, issues, risk }:
  { duration: number; chapters: Signal[]; issues: Issue[]; risk: RiskBin[] }) {
  const { currentMs, seek, select, selectedIssue } = usePlayhead();
  const ref = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const pct = (ms: number) => `${(100 * ms) / duration}%`;
  const w = (a: number, b: number) => `${(100 * Math.max(0, b - a)) / duration}%`;
  const at = (e: React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect();
    return Math.max(0, Math.min(duration, Math.round(((e.clientX - r.left) / r.width) * duration)));
  };
  const step = duration > 20 * 60_000 ? 300_000 : duration > 6 * 60_000 ? 60_000 : 15_000;
  const ticks = Array.from({ length: Math.floor(duration / step) + 1 }, (_, i) => i * step).filter((t) => t < duration * 0.97);
  const current = chapters.find((c) => c.interval.start_ms <= currentMs && currentMs < c.interval.end_ms);
  const chapterLabel = (c: Signal) => String((c.value as { label?: string })?.label ?? "");
  // stack overlapping findings into lanes so none hides another
  const lanes: Issue[][] = [];
  [...issues].sort((a, b) => a.affected_interval.start_ms - b.affected_interval.start_ms).forEach((i) => {
    const lane = lanes.find((l) => l[l.length - 1].affected_interval.end_ms <= i.affected_interval.start_ms);
    if (lane) lane.push(i); else lanes.push([i]);
  });

  return (
    <div className="tl" ref={ref} onMouseMove={(e) => setHover(at(e))} onMouseLeave={() => setHover(null)}>
      <div className="tl-row tl-ruler" onClick={(e) => seek(at(e))} style={{ cursor: "pointer" }}>
        {ticks.map((t) => <span key={t} className="tl-tick" style={{ left: pct(t) }}>{fmt(t).replace(/\.\d$/, "")}</span>)}
      </div>
      <div className="tl-row" aria-label="Chapters">
        {chapters.map((c) => {
          const label = chapterLabel(c);
          const wide = (c.interval.end_ms - c.interval.start_ms) / duration > 0.07;  // narrow bands: tooltip only
          return (
            <button key={c.signal_id} className="tl-band" title={`${label} · ${fmt(c.interval.start_ms)}`}
              style={{ left: pct(c.interval.start_ms), width: `calc(${w(c.interval.start_ms, c.interval.end_ms)} - 2px)` }}
              onClick={() => seek(c.interval.start_ms)}>{wide ? label : ""}</button>);
        })}
      </div>
      {(lanes.length ? lanes : [[]]).map((lane, li) => (
        <div key={li} className="tl-row" aria-label="Findings">
          {lane.map((i) => (
            <button key={i.issue_id} aria-label={`${issueLabel(i.type)} ${fmt(i.affected_interval.start_ms)}`}
              title={`${issueLabel(i.type)} · ${i.severity} · ${fmt(i.affected_interval.start_ms)}–${fmt(i.affected_interval.end_ms)}`}
              className={`tl-mark ${i.severity} ${i.review_status === "dismissed" ? "dismissed" : ""} ${selectedIssue === i.issue_id ? "sel" : ""}`}
              style={{ left: pct(i.affected_interval.start_ms), width: w(i.affected_interval.start_ms, i.affected_interval.end_ms) }}
              onClick={() => { select(i.issue_id); seek(i.affected_interval.start_ms); }} />))}
        </div>
      ))}
      <div className="tl-row" aria-label="Combined risk" style={{ height: 14 }}>
        {risk.map((b) => {
          const known = b.display_value !== null;
          const v = known ? b.display_value! : b.combined_lower;
          return (
            <span key={b.interval.start_ms} className={`tl-risk ${known ? "" : "tl-unknown"}`}
              title={known ? `risk ${Math.round(v * 100)}` : `risk ≥ ${Math.round(b.combined_lower * 100)} (part of this window not inspected)`}
              style={{ left: pct(b.interval.start_ms), width: w(b.interval.start_ms, b.interval.end_ms),
                background: known ? `rgba(232,80,106,${0.12 + v * 0.88})` : undefined }} />);
        })}
      </div>
      <div className="tl-playhead" style={{ left: pct(currentMs) }} />
      {hover !== null && <div className="tl-hover mono" style={{ left: pct(hover) }}>{fmt(hover)}</div>}
      <div className="tl-now">
        <span className="faint">Chapter</span> <b>{current ? chapterLabel(current) : "—"}</b>
        {current && <span className="faint mono"> {fmt(current.interval.start_ms)}–{fmt(current.interval.end_ms)}</span>}
      </div>
      <div className="legend" style={{ marginTop: 6 }}>
        <span><span className="swatch" style={{ background: "var(--sev-high)" }} />high</span>
        <span><span className="swatch" style={{ background: "var(--sev-medium)" }} />medium</span>
        <span><span className="swatch" style={{ background: "#a9a5a0" }} />low</span>
        <span><span className="swatch tl-unknown" />not inspected yet (unknown, not healthy)</span>
        <span className="faint">bottom strip: combined heuristic risk</span>
      </div>
    </div>
  );
}
