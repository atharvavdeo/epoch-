import { useEffect, useMemo, useRef, useState } from "react";
import { fmt, type Coverage, type Interval, type Prediction, type RiskBin, type Scenario, type Segment, type Signal } from "../api";
import { usePlayhead } from "../store";
import type { UBin, UFinding } from "./findings";
import { IconFit, IconZoomIn, IconZoomOut } from "./Icons";
import { featureLabel } from "./labels";

const LABEL: Record<string, string> = {
  delayed_payoff: "Delayed payoff", slow_intro: "Slow intro", unnecessary_repetition: "Repetition", tangent: "Tangent",
  unresolved_promise: "Unresolved promise", dead_air: "Dead air", rushed_delivery: "Rushed delivery",
  visual_stagnation: "Visual stagnation", technical_visual_fault: "Visual fault", technical_audio_fault: "Audio fault",
  disruptive_cta: "Disruptive CTA",
};
export const issueLabel = (t: string) => LABEL[t] ?? t;

type ShotLite = { shot_id: string; interval: Interval; metrics: Record<string, number | null> };
const clock = (ms: number) => fmt(ms).replace(/\.\d$/, "");
const pctFmt = (v: number) => `${(v * 100).toFixed(v < 0.1 ? 1 : 0)}%`;
const MAX_ZOOM = 40;

/** Shared, zoomable timeline. Wheel+Ctrl / pinch or the buttons zoom, drag pans, drag on the ruler selects a range,
 *  the minimap shows the whole video. Every lane seeks the same playhead and sets the same selection. */
export function Timeline({ duration, chapters, findings, risk, bins, scenario, scenarioAck, shots, segments, coverage, pred }: {
  duration: number; chapters: Signal[]; findings: UFinding[]; risk: RiskBin[]; bins: UBin[]; scenario?: Scenario; scenarioAck: boolean;
  pred?: Prediction; shots: ShotLite[]; segments: Segment[]; coverage: Coverage[];
}) {
  const { currentMs, focus, selectedIssue, selection } = usePlayhead();
  const D = Math.max(1, duration);
  const [zoom, setZoom] = useState(1);
  const [start, setStart] = useState(0);
  const span = D / zoom;
  const clampStart = (s: number, z = zoom) => Math.max(0, Math.min(D - D / z, s));
  const vp = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; start: number; moved: boolean; mode: "pan" | "range"; ms: number } | null>(null);
  const [range, setRange] = useState<Interval | null>(null);
  const dragged = useRef(false);
  const [vpW, setVpW] = useState(800);
  useEffect(() => {
    const el = vp.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setVpW(e.contentRect.width || 800));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const [hover, setHover] = useState<{ ms: number; x: number } | null>(null);

  const msAtX = (clientX: number) => {
    const r = vp.current!.getBoundingClientRect();
    return { ms: Math.max(0, Math.min(D, start + ((clientX - r.left) / r.width) * span)), x: clientX - r.left };
  };
  const zoomTo = (z: number, anchorMs = start + span / 2, anchorFrac = 0.5) => {
    const nz = Math.max(1, Math.min(MAX_ZOOM, z));
    setZoom(nz);
    setStart(Math.max(0, Math.min(D - D / nz, anchorMs - (D / nz) * anchorFrac)));
  };

  // Ctrl/⌘ + wheel (and trackpad pinch) zooms around the cursor; horizontal wheel pans. Needs a non-passive listener.
  useEffect(() => {
    const el = vp.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      const r = el.getBoundingClientRect();
      const frac = (e.clientX - r.left) / r.width;
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const anchor = start + frac * span;
        zoomTo(zoom * Math.exp(-e.deltaY * 0.004), anchor, frac);
      } else if (zoom > 1 && Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        e.preventDefault();
        setStart((s) => clampStart(s + (e.deltaX / r.width) * span));
      }
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  });

  // keep the playhead in view while the video plays
  useEffect(() => {
    if (zoom <= 1 || drag.current) return;
    if (currentMs < start || currentMs > start + span) setStart(clampStart(currentMs - span * 0.15));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentMs]);

  const onDown = (e: React.PointerEvent, mode: "pan" | "range") => {
    if (e.button !== 0) return;
    dragged.current = false;
    drag.current = { x: e.clientX, start, moved: false, mode, ms: msAtX(e.clientX).ms };
  };
  const onMove = (e: React.PointerEvent) => {
    setHover(msAtX(e.clientX));
    const d = drag.current;
    if (!d) return;
    if (!d.moved && Math.abs(e.clientX - d.x) > 4) { d.moved = true; dragged.current = true; (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId); }
    if (!d.moved) return;
    if (d.mode === "pan" && zoom > 1) {
      const w = vp.current!.getBoundingClientRect().width;
      setStart(clampStart(d.start - ((e.clientX - d.x) / w) * span));
    } else if (d.mode === "range") {
      const ms = msAtX(e.clientX).ms;
      setRange({ start_ms: Math.min(d.ms, ms), end_ms: Math.max(d.ms, ms) });
    }
  };
  const onUp = (e: React.PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (d.mode === "range") {
      if (d.moved && range && range.end_ms - range.start_ms > 300) focus({ start_ms: Math.round(range.start_ms), end_ms: Math.round(range.end_ms) }, null);
      else if (!d.moved) { const ms = msAtX(e.clientX).ms; focus({ start_ms: Math.round(ms), end_ms: Math.min(D, Math.round(ms) + 5000) }, null); }
      setRange(null);
    }
  };
  // a drag must not also count as a click on whatever is under the pointer
  const swallowDragClick = (e: React.MouseEvent) => { if (dragged.current) { e.stopPropagation(); e.preventDefault(); } };

  const pct = (ms: number) => `${(100 * ms) / D}%`;
  const w = (a: number, b: number) => `${(100 * Math.max(0, b - a)) / D}%`;
  const stepMs = [1e3, 2e3, 5e3, 10e3, 15e3, 30e3, 60e3, 120e3, 300e3, 600e3].find((s) => span / s <= Math.max(2, Math.min(10, Math.floor(vpW / 64)))) ?? 900e3;
  const ticks = Array.from({ length: Math.floor(D / stepMs) + 1 }, (_, i) => i * stepMs).filter((t) => t < D);
  const textUnknown = !coverage.some((c) => c.modality === "text" && c.status === "observed");
  const clickAt = (e: React.MouseEvent) => {
    if (dragged.current) return;
    const { ms } = msAtX(e.clientX);
    const b = bins.find((x) => x.start_ms <= ms && ms < x.end_ms);
    focus(b ? { start_ms: b.start_ms, end_ms: b.end_ms } : { start_ms: Math.round(ms), end_ms: Math.min(D, Math.round(ms) + 5000) }, null);
  };

  const lanes = useMemo(() => {
    const out: UFinding[][] = [];
    [...findings].sort((a, b) => a.start_ms - b.start_ms).forEach((f) => {
      const lane = out.find((l) => l[l.length - 1].end_ms <= f.start_ms);
      if (lane) lane.push(f); else if (out.length < 3) out.push([f]); else out[out.length - 1].push(f);
    });
    return out.length ? out : [[]];
  }, [findings]);

  const H = 40;
  const curve = useMemo(() => {
    if (pred) {
      const ps = pred.per_second, n = Math.max(1, pred.summary.duration_s);
      const x = (t: number) => (1000 * t) / n;
      const y = (v: number) => H - v * H;
      const ex = (p: (typeof ps)[number]) => p.end_s ?? p.t + 1;
      return { band: `0,${y(1)} ${ps.map((p) => `${x(ex(p))},${y(p.upper)}`).join(" ")} ${[...ps].reverse().map((p) => `${x(ex(p))},${y(p.lower)}`).join(" ")}`,
        base: `0,${y(1)} ${ps.map((p) => `${x(ex(p))},${y(p.neutral)}`).join(" ")}`, line: `0,${y(1)} ${ps.map((p) => `${x(ex(p))},${y(p.retention)}`).join(" ")}` as string | null };
    }
    if (!scenario) return null;
    const x = (ms: number) => (1000 * ms) / D, y = (v: number) => H - v * H;
    return { band: `0,${y(1)} ${scenario.bins.map((b) => `${x(b.end_ms)},${y(b.retention_end.upper)}`).join(" ")} ${[...scenario.bins].reverse().map((b) => `${x(b.end_ms)},${y(b.retention_end.lower)}`).join(" ")}`,
      base: `0,${y(1)} ${scenario.bins.map((b) => `${x(b.end_ms)},${y(b.baseline_end)}`).join(" ")}`, line: null as string | null };
  }, [pred, scenario, D]);
  const maxRisk = Math.max(1, ...bins.map((b) => b.risk ?? 0));

  const hv = hover ? (() => {
    const b = bins.find((x) => x.start_ms <= hover.ms && hover.ms < x.end_ms);
    const ps = pred?.per_second[Math.min(pred.per_second.length - 1, Math.floor(hover.ms / 1000))];
    const f = findings.find((x) => x.start_ms <= hover.ms && hover.ms < x.end_ms);
    const ch = chapters.find((c) => c.interval.start_ms <= hover.ms && hover.ms < c.interval.end_ms);
    return { b, ps, f, ch };
  })() : null;

  const Track = ({ mini }: { mini?: boolean }) => <>
    {curve && <svg viewBox={`0 0 1000 ${H}`} preserveAspectRatio="none" className="tl-curve" style={{ opacity: pred || scenarioAck ? 1 : 0.5, height: mini ? 28 : H }}>
      <polygon points={curve.band} className="ch-band" />
      <polyline points={curve.base} className="ch-neutral" vectorEffect="non-scaling-stroke" />
      {curve.line && <polyline points={curve.line} className="ch-line" vectorEffect="non-scaling-stroke" />}
    </svg>}
  </>;

  return (
    <div className="tl3">
      <div className="tl3-bar">
        <span className="kicker">Timeline</span>
        <span className="faint num tl3-range">{zoom > 1 ? `${clock(start)}–${clock(start + span)}` : `0:00–${clock(D)}`}</span>
        <span className="tl3-tools">
          <button className="icon-btn" aria-label="Zoom out" title="Zoom out" disabled={zoom <= 1} onClick={() => zoomTo(zoom / 2)}><IconZoomOut /></button>
          <button className="icon-btn" aria-label="Zoom in" title="Zoom in (or Ctrl + scroll)" disabled={zoom >= MAX_ZOOM}
            onClick={() => zoomTo(zoom * 2, currentMs >= start && currentMs <= start + span ? currentMs : start + span / 2)}><IconZoomIn /></button>
          <button className="icon-btn" aria-label="Show whole video" title="Show whole video" disabled={zoom <= 1} onClick={() => zoomTo(1, 0, 0)}><IconFit /></button>
        </span>
      </div>

      {/* minimap: whole video, the visible window, the playhead; click or drag to move the window */}
      <div className="tl3-mini" onPointerDown={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        const move = (cx: number) => setStart(clampStart(((cx - r.left) / r.width) * D - span / 2));
        move(e.clientX);
        const mm = (ev: PointerEvent) => move(ev.clientX);
        const up = () => { window.removeEventListener("pointermove", mm); window.removeEventListener("pointerup", up); };
        window.addEventListener("pointermove", mm); window.addEventListener("pointerup", up);
      }} title="Whole video — drag to move the zoomed window">
        <Track mini />
        {bins.map((b) => b.risk ? <span key={b.start_ms} className="tl-mini-risk" style={{ left: pct(b.start_ms), width: w(b.start_ms, b.end_ms), opacity: 0.15 + 0.85 * (b.risk / maxRisk) }} /> : null)}
        <span className="tl3-window" style={{ left: pct(start), width: pct(span) }} />
        <span className="tl3-mini-head" style={{ left: pct(currentMs) }} />
      </div>

      <div className="tl3-body">
        <div className="tl3-labels" aria-hidden>
          <span className="ruler-l" />
          <span>Sections</span><span style={{ height: H }}>Estimate</span><span>Risk</span>
          {lanes.map((_, i) => <span key={i}>{i === 0 ? "Findings" : ""}</span>)}
          <span>Shots</span><span>Speech</span><span>On-screen text</span>
        </div>
        <div className={`tl3-viewport ${zoom > 1 ? "zoomed" : ""}`} ref={vp} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={() => setHover(null)}
          onPointerDown={(e) => onDown(e, "pan")} onClickCapture={swallowDragClick}>
          <div className="tl3-track" style={{ width: `${zoom * 100}%`, left: `${-(start / D) * zoom * 100}%` }}>
            <div className="tl2-row ruler" onPointerDown={(e) => { e.stopPropagation(); onDown(e, "range"); }} title="Click to jump, drag to select a range">
              {ticks.map((t) => <span key={t} className="tl-tick num" style={{ left: pct(t) }}>{clock(t)}</span>)}
            </div>
            <div className="tl2-row">
              {chapters.map((c) => {
                const label = String((c.value as { label?: string })?.label ?? "");
                const wide = ((c.interval.end_ms - c.interval.start_ms) / span) > 0.07;
                return <button key={c.signal_id} className="tl-band" title={`${label} · ${clock(c.interval.start_ms)}`}
                  style={{ left: pct(c.interval.start_ms), width: `calc(${w(c.interval.start_ms, c.interval.end_ms)} - 2px)` }}
                  onClick={() => focus(c.interval, null)}>{wide ? label : ""}</button>;
              })}
            </div>
            <div className="tl2-row" style={{ height: H }} onClick={clickAt}>
              {curve ? <Track /> : <span className="tl-lane-note">No estimate</span>}
            </div>
            <div className="tl2-row" onClick={clickAt}>
              {bins.length ? bins.map((b) => b.risk === null
                ? <span key={b.start_ms} className="tl-risk tl-unknown" style={{ left: pct(b.start_ms), width: w(b.start_ms, b.end_ms) }} />
                : <span key={b.start_ms} className="tl-risk" style={{ left: pct(b.start_ms), width: w(b.start_ms, b.end_ms), opacity: b.risk > 0 ? 0.12 + 0.88 * (b.risk / maxRisk) : 0 }} />)
                : risk.map((b) => {
                  const known = b.display_value !== null;
                  return <span key={b.interval.start_ms} className={`tl-risk ${known ? "" : "tl-unknown"}`}
                    style={{ left: pct(b.interval.start_ms), width: w(b.interval.start_ms, b.interval.end_ms), opacity: known ? 0.1 + b.display_value! * 0.9 : undefined }} />;
                })}
            </div>
            {lanes.map((lane, li) => (
              <div key={li} className="tl2-row">
                {lane.map((f) => (
                  <button key={f.id} aria-label={`${f.title} ${clock(f.start_ms)}`} title={`${f.title} · ${clock(f.start_ms)}–${clock(f.end_ms)}`}
                    className={`tl-mark ${f.severity} ${f.source} ${selectedIssue && selectedIssue === f.issue?.issue_id ? "sel" : ""}`}
                    style={{ left: pct(f.start_ms), width: w(f.start_ms, f.end_ms) }}
                    onClick={() => focus({ start_ms: f.start_ms, end_ms: f.end_ms }, f.issue?.issue_id ?? null)}>
                    {(f.end_ms - f.start_ms) / span > 0.08 && <span className="tl-mark-label">{f.title}</span>}</button>))}
              </div>))}
            <div className="tl2-row">
              {shots.map((s, k) => {
                const len = s.interval.end_ms - s.interval.start_ms;
                return <button key={s.shot_id} className={`tl-shot ${k % 2 ? "odd" : ""}`} title={`Shot ${k + 1}: ${clock(s.interval.start_ms)} · ${(len / 1000).toFixed(1)} s`}
                  style={{ left: pct(s.interval.start_ms), width: w(s.interval.start_ms, s.interval.end_ms) }} onClick={() => focus(s.interval, null)} />;
              })}
              {!shots.length && <span className="tl-risk tl-unknown full"><span className="tl-lane-note">Not inspected</span></span>}
            </div>
            <div className="tl2-row">
              {segments.map((s) => <button key={s.segment_id} className={`tl-speech ${s.precision !== "word" ? "approx" : ""}`}
                title={`${clock(s.interval.start_ms)} ${s.text.slice(0, 80)}`} style={{ left: pct(s.interval.start_ms), width: w(s.interval.start_ms, s.interval.end_ms) }}
                onClick={() => focus(s.interval, null)} />)}
            </div>
            <div className="tl2-row">
              {textUnknown ? <span className="tl-risk tl-unknown full" title="On-screen text was not read for this run"><span className="tl-lane-note">Not inspected</span></span>
                : coverage.filter((c) => c.modality === "text").map((c, i) => (
                  <span key={i} className={`tl-risk ${c.status === "observed" ? "observed" : "tl-unknown"}`} style={{ left: pct(c.interval.start_ms), width: w(c.interval.start_ms, c.interval.end_ms) }} />))}
            </div>
            {selection && <div className="tl-selection" style={{ left: pct(selection.start_ms), width: w(selection.start_ms, selection.end_ms) }} />}
            {range && <div className="tl-selection preview" style={{ left: pct(range.start_ms), width: w(range.start_ms, range.end_ms) }} />}
            <div className="tl-playhead" style={{ left: pct(currentMs) }} />
          </div>
          {hover && hv && !drag.current?.moved && (
            <div className="tl-tip" style={{ left: Math.max(4, Math.min(hover.x + 14, (vp.current?.clientWidth ?? 600) - 270)) }}>
              <div className="ch-tip-t num">{clock(hover.ms)}{hv.ch ? ` · ${String((hv.ch.value as { label?: string })?.label ?? "")}` : ""}</div>
              {hv.ps && <div>Still watching: <b>{pctFmt(hv.ps.retention)}</b> <span className="faint">estimate</span></div>}
              {hv.ps && Object.keys(hv.ps.contributions).length > 0 && <div>Why: {Object.entries(hv.ps.contributions).sort((p, q) => q[1] - p[1]).slice(0, 2).map(([k]) => featureLabel(k)).join(", ")}</div>}
              {hv.b && <div>Risk {hv.b.risk === null ? "not measured" : <b className="num">{Math.round(hv.b.risk)}</b>}</div>}
              {hv.f && <div className="tip-strong">{hv.f.title}</div>}
            </div>)}
        </div>
      </div>
      <div className="tl3-hint faint">Drag to pan · drag the time ruler to select · Ctrl + scroll to zoom</div>
    </div>
  );
}
