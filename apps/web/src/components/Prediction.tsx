import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, fmt, type Prediction } from "../api";
import { usePlayhead } from "../store";

const pc = (v: number) => `${(v * 100).toFixed(1)}%`;
const s2 = (s: number) => fmt(s * 1000).replace(/\.\d$/, "");
export const FEATURE_LABEL: Record<string, string> = {
  setup_before_substance: "Setup before the first point", no_hook_yet: "No hook yet", payoff_pending: "Title payoff delayed",
  low_novelty: "Little new information", repetition: "Repeated wording", slow_pace: "Slower than usual", fast_pace: "Faster than usual",
  filler_density: "Filler words", dead_air: "Dead air", cta_or_sponsor: "Mid-video CTA / sponsor", outro: "Outro",
  long_sentences: "Long sentences", open_loop: "Open question (holds viewers)", concrete: "Concrete example (holds viewers)",
};

/** The core USP: where viewers are predicted to leave, and why — from the transcript. */
export function PredictionView({ runId, pred, onPred }: { runId: string; pred: Prediction; onPred: (p: Prediction) => void }) {
  const { focus, currentMs } = usePlayhead();
  const [a30, setA30] = useState(pred.anchors.retention_at_30s);
  const [aEnd, setAEnd] = useState(pred.anchors.retention_at_end);
  const [ack, setAck] = useState(false);
  const re = useMutation({ mutationFn: () => api.repredict(runId, { retention_at_30s: a30, retention_at_end: aEnd, acknowledged: true }),
    onSuccess: onPred });
  const ps = pred.per_second;
  const T = ps.length;
  const W = 1000, H = 240, P = 26;
  const x = (t: number) => (t / T) * W;
  const y = (v: number) => P / 2 + (1 - v) * (H - P);
  const line = (k: "retention" | "neutral") => `0,${y(1)} ` + ps.map((p) => `${x(p.t + 1)},${y(p[k])}`).join(" ");
  const band = `0,${y(1)} ${ps.map((p) => `${x(p.t + 1)},${y(p.upper)}`).join(" ")} ${[...ps].reverse().map((p) => `${x(p.t + 1)},${y(p.lower)}`).join(" ")}`;
  const s = pred.summary;
  const drivers = Object.entries(s.excess_loss_by_feature).filter(([, v]) => v > 0.0005);
  const maxDriver = Math.max(...drivers.map(([, v]) => v), 1e-9);
  const seekSvg = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const t = Math.round(((e.clientX - r.left) / r.width) * T);
    focus({ start_ms: t * 1000, end_ms: Math.min(T, t + 5) * 1000 }, null);
  };
  const nowT = Math.min(T - 1, Math.floor(currentMs / 1000));
  const now = ps[nowT];

  return (
    <div className="pred">
      <div className="section-title" style={{ marginBottom: 2 }}><h3>Predicted retention</h3><span className="pill uncal">Uncalibrated · rule-based text model</span></div>
      <p className="muted" style={{ margin: "0 0 12px", fontSize: 14 }}>Built from what is said and how: setup length, hook, title payoff, repetition,
        new information, pace, fillers, quiet gaps, CTAs. The weights are reasoned priors, <b>not fitted to audience data</b>; the band shows
        how much the answer moves if every weight is half or one-and-a-half times as strong.</p>
      <div className="stats">
        <div className="stat"><span className="v">{Math.round(s.avd_s.central)} s</span><span className="k">predicted avg watch time ({Math.round(s.avd_s.lower)}–{Math.round(s.avd_s.upper)} s)</span></div>
        <div className="stat"><span className="v">{s.apv_pct.central.toFixed(1)}%</span><span className="k">predicted % viewed ({s.apv_pct.lower.toFixed(0)}–{s.apv_pct.upper.toFixed(0)}%)</span></div>
        <div className="stat"><span className="v">{s.end_pct.central.toFixed(1)}%</span><span className="k">still watching at the end ({s.end_pct.lower.toFixed(0)}–{s.end_pct.upper.toFixed(0)}%)</span></div>
        <div className="stat"><span className="v">{Math.round(s.neutral_avd_s)} s</span><span className="k">an assumed average video of this length</span></div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={pred.label} onClick={seekSvg} style={{ cursor: "pointer", display: "block" }}>
        {[1, 0.75, 0.5, 0.25].map((v) => <g key={v}><line x1={0} x2={W} y1={y(v)} y2={y(v)} stroke="#2a2a2e" /><text x={4} y={y(v) - 3}>{v * 100}%</text></g>)}
        <polygon points={band} fill="rgba(217,138,30,.22)" />
        <polyline points={line("neutral")} fill="none" stroke="#8a8682" strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />
        <polyline points={line("retention")} fill="none" stroke="var(--amber-300)" strokeWidth={2.2} vectorEffect="non-scaling-stroke" />
        {pred.drop_moments.map((m, i) => {
          const cx = x(m.start_s + 5), cy = y(ps[Math.min(T - 1, m.start_s + 5)].retention);
          return <g key={i} onClick={(e) => { e.stopPropagation(); focus({ start_ms: m.start_s * 1000, end_ms: m.end_s * 1000 }, null); }}>
            <circle cx={cx} cy={cy} r={10} fill="var(--coral-end)" /><text x={cx} y={cy + 4} textAnchor="middle" style={{ fill: "#fff", fontSize: 11, fontWeight: 600 }}>{i + 1}</text></g>;
        })}
        <line x1={x(nowT)} x2={x(nowT)} y1={0} y2={H} stroke="var(--amber-300)" strokeOpacity={0.6} />
      </svg>
      <div className="legend">
        <span><span className="swatch" style={{ background: "var(--amber-300)" }} />predicted for this video</span>
        <span><span className="swatch" style={{ background: "rgba(217,138,30,.4)" }} />sensitivity band</span>
        <span><span className="swatch" style={{ background: "#8a8682" }} />assumed average video (dashed)</span>
        <span><span className="swatch" style={{ background: "var(--coral-end)" }} />biggest predicted drop-offs</span>
        {now && <span>at {s2(nowT)}: <b>{pc(now.retention)}</b> predicted still watching</span>}
      </div>

      <div className="bottom" style={{ marginTop: 18 }}>
        <div>
          <h4 className="fdh">Where viewers are predicted to leave, and why</h4>
          {pred.drop_moments.map((m, i) => (
            <button key={i} className="dm" onClick={() => focus({ start_ms: m.start_s * 1000, end_ms: m.end_s * 1000 }, m.issue_ids[0] ?? null)}>
              <span className="dm-n">{i + 1}</span>
              <span className="dm-body">
                <span className="row" style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                  <b className="mono">{s2(m.start_s)}–{s2(m.end_s)}</b>
                  <span className="muted">{pc(m.retention_before)} → {pc(m.retention_after)}</span>
                  <span className="faint">({(m.excess_loss * 100).toFixed(2)} pts more than an average video)</span>
                </span>
                <span className="dm-reasons">{m.reasons.map((r) => (
                  <span key={r.feature} className="reason"><span className="bar" style={{ width: `${Math.max(6, r.share * 100)}%` }} />
                    <span>{r.text} <span className="faint">{Math.round(r.share * 100)}%</span></span></span>))}</span>
                {m.quote && <span className="quote-orig" style={{ display: "block", fontSize: 13 }}>“{m.quote.slice(0, 220)}{m.quote.length > 220 ? "…" : ""}”</span>}
                {!!m.issue_ids.length && <span className="pill amber">linked finding</span>}
              </span>
            </button>))}
        </div>
        <div>
          <h4 className="fdh">What costs the most viewers overall</h4>
          {drivers.map(([k, v]) => (
            <div key={k} className="driver">
              <span>{FEATURE_LABEL[k] ?? k}</span>
              <span className="dbar"><span style={{ width: `${(v / maxDriver) * 100}%` }} /></span>
              <span className="mono faint">{(v * 100).toFixed(1)} pts</span>
            </div>))}
          <p className="faint" style={{ fontSize: 13 }}>Points = share of starting viewers lost beyond an assumed average video, summed over the video.</p>

          <h4 className="fdh" style={{ marginTop: 18 }}>Assumptions</h4>
          <p className="faint" style={{ fontSize: 13, margin: 0 }}>An assumed average video of this length keeps {pc(pred.anchors.retention_at_30s)} at 30 s and
            {" "}{pc(pred.anchors.retention_at_end)} at the end. Change these to match your channel; the features stay the same.</p>
          <div className="row" style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
            <label>at 30 s <input type="number" step="0.05" min="0.05" max="1" value={a30} onChange={(e) => setA30(+e.target.value)} style={{ width: 80 }} /></label>
            <label>at end <input type="number" step="0.05" min="0.05" max="1" value={aEnd} onChange={(e) => setAEnd(+e.target.value)} style={{ width: 80 }} /></label>
            <label><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> These are assumptions</label>
            <button className="amber" disabled={!ack || !(aEnd > 0 && aEnd <= a30 && a30 <= 1) || re.isPending} onClick={() => re.mutate()}>Recompute</button>
          </div>
          {re.error && <p className="err">{(re.error as Error).message}</p>}
          <details style={{ marginTop: 16 }}>
            <summary className="muted" style={{ cursor: "pointer" }}>How this model works ({Object.keys(pred.weights).length} features)</summary>
            <table className="cmp"><thead><tr><th>Feature</th><th>Effect</th><th>Why</th></tr></thead>
              <tbody>{Object.entries(pred.weights).map(([k, w]) => (
                <tr key={k}><td>{FEATURE_LABEL[k] ?? k}</td><td className="mono">{w.weight > 0 ? "×" + Math.exp(w.weight).toFixed(2) : "×" + Math.exp(w.weight).toFixed(2)} hazard</td>
                  <td style={{ fontSize: 13 }}>{w.rationale}</td></tr>))}</tbody></table>
            <ul className="faint" style={{ fontSize: 13 }}>{pred.notes.map((n) => <li key={n}>{n}</li>)}
              <li>Inputs used: {pred.feature_info.sources.join("; ")}.</li></ul>
          </details>
        </div>
      </div>
    </div>
  );
}
