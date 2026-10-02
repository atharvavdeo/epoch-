import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, fmt, type RiskBin, type Scenario, type Signal } from "../api";
import { usePlayhead } from "../store";

const W = 1000;
const TRACKS = ["narrative", "visual", "pacing", "text", "technical"];

function riskColor(r: number) {
  // ordinal heuristic scale: low risk = dim, high = coral
  const a = Math.min(1, 0.15 + r * 0.85);
  return `rgba(232, 80, 106, ${a})`;
}

function Playhead({ duration, h }: { duration: number; h: number }) {
  const { currentMs } = usePlayhead();
  const x = (currentMs / duration) * W;
  return <line x1={x} x2={x} y1={0} y2={h} stroke="#f2a93b" strokeWidth={1.5} />;
}

function clickSeek(e: React.MouseEvent<SVGSVGElement>, duration: number, seek: (ms: number) => void) {
  const r = e.currentTarget.getBoundingClientRect();
  seek(Math.round(((e.clientX - r.left) / r.width) * duration));
}

export function RiskChart({ bins, duration, chapters }: { bins: RiskBin[]; duration: number; chapters: Signal[] }) {
  const { seek } = usePlayhead();
  const laneH = 16, top = 18, rows = TRACKS.length + 1;
  const h = top + rows * (laneH + 6) + 18;
  const sx = (ms: number) => (ms / duration) * W;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${h}`} width="100%" role="img" aria-label="Diagnostic risk by track (heuristic 0-100)"
        onClick={(e) => clickSeek(e, duration, seek)} style={{ cursor: "pointer" }}>
        <defs>
          <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="#26262a" /><line x1="0" y1="0" x2="0" y2="6" stroke="#55555c" strokeWidth="2" />
          </pattern>
        </defs>
        {chapters.map((c) => (
          <g key={c.signal_id}>
            <line x1={sx(c.interval.start_ms)} x2={sx(c.interval.start_ms)} y1={0} y2={h} stroke="#3a3a3f" />
            <text x={sx(c.interval.start_ms) + 3} y={11}>{String((c.value as { label?: string })?.label ?? "").slice(0, 22)}</text>
          </g>
        ))}
        {TRACKS.map((t, i) => {
          const y = top + i * (laneH + 6);
          return (
            <g key={t}>
              {bins.map((b) => {
                const v = b.track_values[t];
                if (!v) return null;
                const x = sx(b.interval.start_ms), w = Math.max(0.5, sx(b.interval.end_ms) - x);
                const unknownH = laneH * (1 - v.coverage);
                return (
                  <g key={b.interval.start_ms}>
                    {v.coverage > 0 && <rect x={x} y={y + unknownH} width={w} height={laneH - unknownH} fill={v.risk ? riskColor(v.risk) : "#2f3a33"} />}
                    {v.coverage < 1 && <rect x={x} y={y} width={w} height={unknownH} fill="url(#hatch)" />}
                  </g>
                );
              })}
              <text x={4} y={y + 12} style={{ fill: "#d8d4cf" }}>{t}</text>
            </g>
          );
        })}
        {(() => {
          const y = top + TRACKS.length * (laneH + 6);
          return (
            <g>
              {bins.map((b) => {
                const x = sx(b.interval.start_ms), w = Math.max(0.5, sx(b.interval.end_ms) - x);
                return b.display_value !== null
                  ? <rect key={b.interval.start_ms} x={x} y={y} width={w} height={laneH} fill={riskColor(b.combined_lower)} />
                  : <g key={b.interval.start_ms}><rect x={x} y={y} width={w} height={laneH} fill="url(#hatch)" />
                      <rect x={x} y={y + laneH * (1 - b.combined_lower)} width={w} height={laneH * b.combined_lower} fill={riskColor(b.combined_lower)} /></g>;
              })}
              <text x={4} y={y + 12} style={{ fill: "#fff4e6" }}>combined</text>
            </g>
          );
        })()}
        <Playhead duration={duration} h={h} />
        <text x={0} y={h - 2}>0:00</text><text x={W - 34} y={h - 2}>{fmt(duration)}</text>
      </svg>
      <div className="legend">
        <span><span className="swatch" style={{ background: "#2f3a33" }} />inspected, no accepted issue</span>
        <span><span className="swatch" style={{ background: riskColor(0.9) }} />higher heuristic risk</span>
        <span><span className="swatch" style={{ background: "url(#hatch)", backgroundColor: "#55555c" }} />not inspected (unknown, not healthy)</span>
        <span>Risk is an ordinal heuristic (0–100), not the probability a viewer leaves.</span>
      </div>
    </div>
  );
}

export function RetentionChart({ runId, scenario, duration, ack, onScenario }:
  { runId: string; scenario: Scenario | undefined; duration: number; ack: boolean; onScenario: (s: Scenario) => void }) {
  const { seek } = usePlayhead();
  const [a30, setA30] = useState(scenario?.assumptions.retention_at_30s ?? 0.8);
  const [aEnd, setAEnd] = useState(scenario?.assumptions.retention_at_end ?? 0.45);
  const [confirm, setConfirm] = useState(ack);
  const mut = useMutation({ mutationFn: () => api.scenario(runId, { retention_at_30s: a30, retention_at_end: aEnd, kappa: 1, acknowledged: true }),
    onSuccess: onScenario });
  if (!scenario) return <p className="muted">No scenario in this run (needs a duration of at least 60 s).</p>;
  const h = 220, pad = 28;
  const sx = (ms: number) => (ms / duration) * W;
  const sy = (v: number) => pad / 2 + (1 - v) * (h - pad);
  const pts = (k: "lower" | "upper" | "central") => scenario.bins.map((b) => `${sx(b.end_ms)},${sy(b.retention_end[k] ?? 0)}`).join(" ");
  const start = `${sx(0)},${sy(1)}`;
  const band = `${start} ${pts("upper")} ${[...scenario.bins].reverse().map((b) => `${sx(b.end_ms)},${sy(b.retention_end.lower)}`).join(" ")} ${start}`;
  const base = `${start} ${scenario.bins.map((b) => `${sx(b.end_ms)},${sy(b.baseline_end)}`).join(" ")}`;
  const central = scenario.coverage_status === "complete";
  const s = scenario.summary;
  const showNumbers = ack || scenario.assumptions.acknowledged;
  const fmtB = (b: { lower: number; upper: number; central: number | null } | null, unit: string, d = 0) =>
    !b ? "—" : b.central !== null ? `${b.central.toFixed(d)}${unit}` : `${b.lower.toFixed(d)}–${b.upper.toFixed(d)}${unit}`;
  return (
    <div>
      <h3>Estimated retention — uncalibrated scenario</h3>
      <p className="muted" style={{ margin: "2px 0 8px" }}>Uses assumed audience behaviour. Percentages and edit differences are not measured predictions.</p>
      <svg viewBox={`0 0 ${W} ${h}`} width="100%" role="img" aria-label="Estimated retention, uncalibrated scenario"
        onClick={(e) => clickSeek(e, duration, seek)} style={{ cursor: "pointer", opacity: showNumbers ? 1 : 0.55 }}>
        {[1, 0.75, 0.5, 0.25, 0].map((v) => (
          <g key={v}><line x1={0} x2={W} y1={sy(v)} y2={sy(v)} stroke="#2a2a2e" /><text x={2} y={sy(v) - 2}>{v * 100}%</text></g>))}
        <polygon points={band} fill="rgba(217,138,30,.22)" />
        <polyline points={base} fill="none" stroke="#a9a5a0" strokeDasharray="5 4" />
        {central && <polyline points={`${start} ${pts("central")}`} fill="none" stroke="#f2a93b" strokeWidth={2} />}
        <Playhead duration={duration} h={h} />
        {!showNumbers && <text x={W / 2 - 150} y={h / 2} style={{ fill: "#fff4e6", fontSize: 16 }}>PREVIEW — confirm assumptions below</text>}
      </svg>
      <div className="legend">
        <span><span className="swatch" style={{ background: "rgba(217,138,30,.4)" }} />range from evidence coverage</span>
        {central ? <span><span className="swatch" style={{ background: "#f2a93b" }} />scenario curve</span>
          : <span>No central curve: some evidence is missing, so only a range is shown.</span>}
        <span><span className="swatch" style={{ background: "#a9a5a0" }} />assumed baseline (dashed)</span>
      </div>
      <div className="card" style={{ background: "var(--bg-inset)", marginTop: 10 }}>
        <b>Assumptions</b> <span className="muted">(not typical YouTube retention; chosen only to draw an interpretable scenario)</span>
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginTop: 6 }}>
          <label>at 30 s <input type="number" step="0.05" min="0.05" max="1" value={a30} onChange={(e) => setA30(+e.target.value)} style={{ width: 80 }} /></label>
          <label>at end <input type="number" step="0.05" min="0.05" max="1" value={aEnd} onChange={(e) => setAEnd(+e.target.value)} style={{ width: 80 }} /></label>
          <label><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /> These are assumptions</label>
          <button className="amber" disabled={!confirm || !(aEnd > 0 && aEnd <= a30 && a30 <= 1) || mut.isPending} onClick={() => mut.mutate()}>Apply</button>
          {mut.error && <span className="err">{(mut.error as Error).message}</span>}
        </div>
      </div>
      <div style={{ display: "flex", gap: 12, marginTop: 10, flexWrap: "wrap" }}>
        {[["Assumed avg. view duration", showNumbers ? fmtB(s.assumed_avd_seconds, " s") : "—"],
          ["Assumed % viewed", showNumbers ? fmtB(s.assumed_apv_pct, "%", 1) : "—"],
          ["Assumed still watching at end", showNumbers ? fmtB(s.assumed_end_pct, "%", 1) : "—"],
          ["Duration", fmt(s.duration_ms)]].map(([k, v]) => (
          <div className="card" key={k} style={{ minWidth: 190, background: "var(--bg-inset)" }}>
            <div className="muted">{k}</div><div className="mono" style={{ fontSize: 20 }}>{v}</div></div>))}
      </div>
      {scenario.labels.filter((l) => l.startsWith("Coverage")).map((l) => <div key={l} className="muted" style={{ fontSize: 12 }}>{l}</div>)}
    </div>
  );
}
