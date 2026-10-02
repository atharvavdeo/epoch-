import { useMemo, useRef, useState } from "react";
import { fmt, type Coverage, type Interval, type Issue, type Prediction, type RiskBin, type Scenario, type Segment, type Signal } from "../api";
import { FEATURE_LABEL } from "./Prediction";
import { usePlayhead } from "../store";

const LABEL: Record<string, string> = {
  delayed_payoff: "Delayed payoff", slow_intro: "Slow intro", unnecessary_repetition: "Repetition", tangent: "Tangent",
  unresolved_promise: "Unresolved promise", dead_air: "Dead air", rushed_delivery: "Rushed delivery",
  visual_stagnation: "Visual stagnation", technical_visual_fault: "Visual fault", technical_audio_fault: "Audio fault",
  disruptive_cta: "Disruptive CTA",
};
export const issueLabel = (t: string) => LABEL[t] ?? t;
const TRACKS = ["narrative", "visual", "pacing", "text", "technical"];

type ShotLite = { shot_id: string; interval: Interval; metrics: Record<string, number | null> };
const pctFmt = (v: number) => `${(v * 100).toFixed(v < 0.1 ? 1 : 0)}%`;

/** Full-width shared timeline (Review spec): every lane seeks the same playhead and sets the same selection. */
export function Timeline({ duration, chapters, issues, risk, scenario, scenarioAck, shots, segments, coverage, pred }: {
  duration: number; chapters: Signal[]; issues: Issue[]; risk: RiskBin[]; scenario?: Scenario; scenarioAck: boolean; pred?: Prediction;
  shots: ShotLite[]; segments: Segment[]; coverage: Coverage[];
}) {
  const { currentMs, focus, selectedIssue, selection } = usePlayhead();
  const ref = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ ms: number; x: number } | null>(null);
  const pct = (ms: number) => `${(100 * ms) / duration}%`;
  const w = (a: number, b: number) => `${(100 * Math.max(0, b - a)) / duration}%`;
  const at = (e: React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect();
    return { ms: Math.max(0, Math.min(duration - 1, Math.round(((e.clientX - r.left) / r.width) * duration))), x: e.clientX - r.left };
  };
  const binAt = (ms: number) => risk.find((b) => b.interval.start_ms <= ms && ms < b.interval.end_ms);
  const step = duration > 20 * 60_000 ? 300_000 : duration > 6 * 60_000 ? 60_000 : 15_000;
  const ticks = Array.from({ length: Math.floor(duration / step) + 1 }, (_, i) => i * step).filter((t) => t < duration * 0.97);
  const byId = Object.fromEntries(issues.map((i) => [i.issue_id, i]));
  const textUnknown = !coverage.some((c) => c.modality === "text" && c.status === "observed");
  const clickBin = (e: React.MouseEvent) => {
    const { ms } = at(e);
    const b = binAt(ms);
    focus(b ? b.interval : { start_ms: ms, end_ms: Math.min(duration, ms + 5000) }, null);
  };

  const lanes = useMemo(() => {
    const out: Issue[][] = [];
    [...issues].sort((a, b) => a.affected_interval.start_ms - b.affected_interval.start_ms).forEach((i) => {
      const lane = out.find((l) => l[l.length - 1].affected_interval.end_ms <= i.affected_interval.start_ms);
      if (lane) lane.push(i); else out.push([i]);
    });
    return out.length ? out : [[]];
  }, [issues]);

  // retention mini-chart path (0..1 → 0..36 px), band between lower and upper
  const H = 36;
  const retPath = useMemo(() => {
    if (pred) {  // text retention model: predicted curve + sensitivity band
      const ps = pred.per_second, n = ps.length;
      const x = (t: number) => (1000 * (t + 1)) / n;
      const y = (v: number) => H - v * H;
      const up = ps.map((p) => `${x(p.t)},${y(p.upper)}`).join(" ");
      const lo = [...ps].reverse().map((p) => `${x(p.t)},${y(p.lower)}`).join(" ");
      return { band: `0,${y(1)} ${up} ${lo} 0,${y(1)}`, base: `0,${y(1)} ${ps.map((p) => `${x(p.t)},${y(p.neutral)}`).join(" ")}`,
        line: `0,${y(1)} ${ps.map((p) => `${x(p.t)},${y(p.retention)}`).join(" ")}` as string | null };
    }
    if (!scenario) return null;
    const pts = scenario.bins;
    const x = (ms: number) => (1000 * ms) / duration;
    const y = (v: number) => H - v * H;
    const up = pts.map((b) => `${x(b.end_ms)},${y(b.retention_end.upper)}`).join(" ");
    const lo = [...pts].reverse().map((b) => `${x(b.end_ms)},${y(b.retention_end.lower)}`).join(" ");
    const base = pts.map((b) => `${x(b.end_ms)},${y(b.baseline_end)}`).join(" ");
    return { band: `0,${y(1)} ${up} ${lo} 0,${y(1)}`, base: `0,${y(1)} ${base}`, line: null as string | null };
  }, [scenario, duration, pred]);

  const hv = hover ? (() => {
    const b = binAt(hover.ms);
    const sb = scenario?.bins.find((x) => x.start_ms <= hover.ms && hover.ms < x.end_ms);
    const dom = b?.contributing_issue_ids.map((id) => byId[id]).filter(Boolean)
      .sort((p, q) => ["high", "medium", "low"].indexOf(p.severity) - ["high", "medium", "low"].indexOf(q.severity))[0];
    const inspected = b ? TRACKS.filter((t) => (b.track_values[t]?.coverage ?? 0) >= 0.999) : [];
    const notInspected = b ? TRACKS.filter((t) => (b.track_values[t]?.coverage ?? 0) < 0.999) : TRACKS;
    const ps = pred?.per_second[Math.min(pred.per_second.length - 1, Math.floor(hover.ms / 1000))];
    return { b, sb, dom, inspected, notInspected, ps };
  })() : null;

  return (
    <div className="tl2">
      <div className="tl2-labels">
        <span style={{ height: 22 }} />
        <span>Chapters</span><span style={{ height: H }}>{pred ? "Predicted" : "Retention"}</span><span>Risk</span>
        {lanes.map((_, i) => <span key={i}>{i === 0 ? "Findings" : ""}</span>)}
        <span>Shots</span><span>Speech</span><span>On-screen text</span>
      </div>
      <div className="tl2-area" ref={ref} onMouseMove={(e) => setHover(at(e))} onMouseLeave={() => setHover(null)}>
        <div className="tl2-row ruler" onClick={clickBin}>
          {ticks.map((t) => <span key={t} className="tl-tick" style={{ left: pct(t) }}>{fmt(t).replace(/\.\d$/, "")}</span>)}
        </div>
        <div className="tl2-row">
          {chapters.map((c) => {
            const label = String((c.value as { label?: string })?.label ?? "");
            const wide = (c.interval.end_ms - c.interval.start_ms) / duration > 0.07;
            return <button key={c.signal_id} className="tl-band" title={`${label} · ${fmt(c.interval.start_ms)}`}
              style={{ left: pct(c.interval.start_ms), width: `calc(${w(c.interval.start_ms, c.interval.end_ms)} - 2px)` }}
              onClick={() => focus(c.interval, null)}>{wide ? label : ""}</button>;
          })}
        </div>
        <div className="tl2-row" style={{ height: H }} onClick={clickBin} title={pred ? pred.label : "Estimated retention — uncalibrated scenario"}>
          {retPath ? (
            <svg viewBox={`0 0 1000 ${H}`} preserveAspectRatio="none" width="100%" height={H} style={{ display: "block", opacity: pred || scenarioAck ? 1 : 0.5 }}>
              <polygon points={retPath.band} fill="rgba(217,138,30,.35)" />
              <polyline points={retPath.base} fill="none" stroke="#a9a5a0" strokeDasharray="4 3" strokeWidth={1} vectorEffect="non-scaling-stroke" />
              {retPath.line && <polyline points={retPath.line} fill="none" stroke="var(--amber-300)" strokeWidth={1.6} vectorEffect="non-scaling-stroke" />}
            </svg>) : <span className="faint" style={{ fontSize: 12 }}>no scenario</span>}
        </div>
        <div className="tl2-row" onClick={clickBin}>
          {risk.map((b) => {
            const known = b.display_value !== null;
            const v = known ? b.display_value! : b.combined_lower;
            return <span key={b.interval.start_ms} className={`tl-risk ${known ? "" : "tl-unknown"}`}
              style={{ left: pct(b.interval.start_ms), width: w(b.interval.start_ms, b.interval.end_ms),
                background: known ? `rgba(232,80,106,${0.1 + v * 0.9})` : undefined,
                boxShadow: !known && v > 0 ? `inset 0 -${Math.round(4 + v * 18)}px 0 rgba(232,80,106,.8)` : undefined }} />;
          })}
        </div>
        {lanes.map((lane, li) => (
          <div key={li} className="tl2-row">
            {lane.map((i) => (
              <button key={i.issue_id} aria-label={`${issueLabel(i.type)} ${fmt(i.affected_interval.start_ms)}`}
                title={`${issueLabel(i.type)} · ${i.severity} · ${i.evidence_status} · ${fmt(i.affected_interval.start_ms)}–${fmt(i.affected_interval.end_ms)}`}
                className={`tl-mark ${i.severity} ${i.evidence_status} ${i.review_status === "dismissed" ? "dismissed" : ""} ${selectedIssue === i.issue_id ? "sel" : ""}`}
                style={{ left: pct(i.affected_interval.start_ms), width: w(i.affected_interval.start_ms, i.affected_interval.end_ms) }}
                onClick={() => focus(i.affected_interval, i.issue_id)}>
                <span className="tl-mark-label">{issueLabel(i.type)}</span></button>))}
          </div>))}
        <div className="tl2-row">
          {shots.map((s, k) => {
            const len = s.interval.end_ms - s.interval.start_ms;
            const still = len >= 15_000 && (s.metrics.motion_mean ?? 1) < 0.02;
            return <button key={s.shot_id} className={`tl-shot ${k % 2 ? "odd" : ""} ${still ? "long" : ""}`}
              title={`shot ${k + 1}: ${fmt(s.interval.start_ms)}–${fmt(s.interval.end_ms)} (${(len / 1000).toFixed(1)} s)${still ? " · long, low motion" : ""}`}
              style={{ left: pct(s.interval.start_ms), width: w(s.interval.start_ms, s.interval.end_ms) }}
              onClick={() => focus(s.interval, null)} />;
          })}
        </div>
        <div className="tl2-row">
          {segments.map((s) => <button key={s.segment_id} className={`tl-speech ${s.precision !== "word" ? "approx" : ""}`}
            title={`${fmt(s.interval.start_ms)} ${s.text.slice(0, 80)}`}
            style={{ left: pct(s.interval.start_ms), width: w(s.interval.start_ms, s.interval.end_ms) }}
            onClick={() => focus(s.interval, null)} />)}
        </div>
        <div className="tl2-row">
          {textUnknown
            ? <span className="tl-risk tl-unknown" style={{ left: 0, width: "100%" }} title="not inspected: OCR off, visual analysis pending">
                <span className="tl-lane-note">not inspected yet</span></span>
            : coverage.filter((c) => c.modality === "text").map((c, i) => (
              <span key={i} className={`tl-risk ${c.status === "observed" ? "" : "tl-unknown"}`}
                style={{ left: pct(c.interval.start_ms), width: w(c.interval.start_ms, c.interval.end_ms),
                  background: c.status === "observed" ? "#2f3a33" : undefined }} />))}
        </div>
        {selection && <div className="tl-selection" style={{ left: pct(selection.start_ms), width: w(selection.start_ms, selection.end_ms) }} />}
        <div className="tl-playhead" style={{ left: pct(currentMs) }} />
        {hover && hv && (
          <div className="tl-tip" style={{ left: Math.min(hover.x + 14, (ref.current?.clientWidth ?? 600) - 290) }}>
            <div className="mono" style={{ color: "var(--text-primary)" }}>{fmt(hover.ms)}</div>
            {hv.ps && <div>Predicted still watching: <b>{pctFmt(hv.ps.retention)}</b> <span className="faint">({pctFmt(hv.ps.lower)}–{pctFmt(hv.ps.upper)})</span>
              {Object.keys(hv.ps.contributions).length > 0 && <div>Why viewers leave here: <b>{Object.entries(hv.ps.contributions).sort((p, q) => q[1] - p[1])
                .slice(0, 2).map(([k]) => FEATURE_LABEL[k] ?? k).join(", ")}</b></div>}
              {hv.ps.protective.length > 0 && <div className="faint">Holding viewers: {hv.ps.protective.map((k) => FEATURE_LABEL[k] ?? k).join(", ")}</div>}
              <div className="faint">rule-based text model, uncalibrated</div></div>}
            {!pred && hv.sb && (scenarioAck
              ? <div>Est. viewers remaining: <b>{hv.sb.retention_end.central !== null ? pctFmt(hv.sb.retention_end.central)
                  : `${pctFmt(hv.sb.retention_end.lower)}–${pctFmt(hv.sb.retention_end.upper)}`}</b>
                  {hv.sb.absolute_drop && <> · loss this 5 s: {hv.sb.absolute_drop.central !== null ? pctFmt(hv.sb.absolute_drop.central)
                    : `${pctFmt(hv.sb.absolute_drop.lower)}–${pctFmt(hv.sb.absolute_drop.upper)}`} of starting viewers</>}
                  <div className="faint">uncalibrated scenario, assumed audience</div></div>
              : <div className="faint">Confirm the retention assumptions to see estimated viewers.</div>)}
            {hv.b && <div>Risk {hv.b.display_value !== null ? Math.round(hv.b.display_value * 100)
              : `≥ ${Math.round(hv.b.combined_lower * 100)} (partly unknown)`} <span className="faint">heuristic 0–100</span></div>}
            {hv.dom ? <div>Main finding: <b>{issueLabel(hv.dom.type)}</b> ({hv.dom.severity})</div> : <div className="faint">No finding here.</div>}
            <div className="faint">Inspected: {hv.inspected.join(", ") || "nothing"}{hv.notInspected.length ? ` · not inspected: ${hv.notInspected.join(", ")}` : ""}</div>
          </div>)}
      </div>
    </div>
  );
}
