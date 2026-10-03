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

/** The core feature: one large chart (retention or drop-off), three numbers, a short ranked list; the rest under Method and data. */
export function PredictionView({ runId, pred, onPred }: { runId: string; pred: Prediction; onPred: (p: Prediction) => void }) {
  const { focus, currentMs, selection } = usePlayhead();
  const [mode, setMode] = useState<"retention" | "risk">("retention");
  const [a30, setA30] = useState(pred.anchors.retention_at_30s);
  const [aEnd, setAEnd] = useState(pred.anchors.retention_at_end);
  const [ack, setAck] = useState(false);
  const re = useMutation({ mutationFn: () => api.repredict(runId, { retention_at_30s: a30, retention_at_end: aEnd, acknowledged: true }),
    onSuccess: onPred });
  const ps = pred.per_second;
  const T = ps.length;
  const W = 1000, H = 260, P = 26;
  const x = (t: number) => (t / T) * W;
  const s = pred.summary;
  // drop-off view: share of current viewers leaving per second (smoothed over 5 s)
  const smooth = (f: (i: number) => number) => ps.map((_, i) => {
    const lo = Math.max(0, i - 2), hi = Math.min(T, i + 3);
    let t = 0;
    for (let j = lo; j < hi; j++) t += f(j);
    return t / (hi - lo);
  });
  const sm = smooth((j) => ps[j].loss);
  const smN = smooth((j) => ps[j].loss - ps[j].excess_loss);
  const maxLoss = Math.max(...sm.slice(3), 1e-6) * 1.1;
  const y = (v: number) => mode === "retention" ? P / 2 + (1 - v) * (H - P) : H - P / 2 - (Math.min(v, maxLoss) / maxLoss) * (H - P);
  const line = (vals: number[]) => vals.map((v, i) => `${x(i + 1)},${y(v)}`).join(" ");
  const ret = [1, ...ps.map((p) => p.retention)];
  const band = `0,${y(1)} ${ps.map((p) => `${x(p.t + 1)},${y(p.upper)}`).join(" ")} ${[...ps].reverse().map((p) => `${x(p.t + 1)},${y(p.lower)}`).join(" ")}`;
  const drivers = Object.entries(s.excess_loss_by_feature).filter(([, v]) => v > 0.0005);
  const maxDriver = Math.max(...drivers.map(([, v]) => v), 1e-9);
  const seekSvg = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const t = Math.round(((e.clientX - r.left) / r.width) * T);
    focus({ start_ms: t * 1000, end_ms: Math.min(T, t + 5) * 1000 }, null);
  };
  const nowT = Math.min(T - 1, Math.floor(currentMs / 1000));
  const top = [...pred.drop_moments].sort((a, b) => b.excess_loss - a.excess_loss).slice(0, 5);

  return (
    <div className="pred">
      <div className="pred-head">
        <h3>{mode === "retention" ? "Estimated retention" : "Drop-off risk"}</h3>
        <span className="pill uncal">Uncalibrated · rule-based text model</span>
        <div className="seg" role="tablist" aria-label="Chart">
          <button role="tab" aria-selected={mode === "retention"} className={mode === "retention" ? "on" : ""} onClick={() => setMode("retention")}>Estimated retention</button>
          <button role="tab" aria-selected={mode === "risk"} className={mode === "risk" ? "on" : ""} onClick={() => setMode("risk")}>Drop-off risk</button>
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={mode === "retention" ? "Estimated retention curve" : "Drop-off risk per second"}
        onClick={seekSvg} style={{ cursor: "pointer", display: "block" }}>
        {mode === "retention" && [1, 0.75, 0.5, 0.25].map((v) => <g key={v}><line x1={0} x2={W} y1={y(v)} y2={y(v)} stroke="#2a2a2e" /><text x={4} y={y(v) - 3}>{v * 100}%</text></g>)}
        {selection && <rect x={x(selection.start_ms / 1000)} width={Math.max(2, x((selection.end_ms - selection.start_ms) / 1000))} y={0} height={H}
          fill="rgba(242,169,59,.10)" />}
        {mode === "retention" ? <>
          <polygon points={band} fill="rgba(217,138,30,.20)" />
          <polyline points={`0,${y(1)} ` + ps.map((p) => `${x(p.t + 1)},${y(p.neutral)}`).join(" ")} fill="none" stroke="#85817d" strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />
          <polyline points={ret.map((v, i) => `${x(i)},${y(v)}`).join(" ")} fill="none" stroke="var(--amber-300)" strokeWidth={2.2} vectorEffect="non-scaling-stroke" />
        </> : <>
          <polyline points={line(smN)} fill="none" stroke="#85817d" strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />
          <polyline points={line(sm)} fill="none" stroke="#e8798a" strokeWidth={2} vectorEffect="non-scaling-stroke" />
        </>}
        {top.map((m, i) => {
          const at = Math.min(T - 1, m.start_s + 5);
          const cx = x(m.start_s + 5), cy = mode === "retention" ? y(ps[at].retention) : y(sm[at]);
          return <g key={i} style={{ cursor: "pointer" }} onClick={(e) => { e.stopPropagation(); focus({ start_ms: m.start_s * 1000, end_ms: m.end_s * 1000 }, m.issue_ids[0] ?? null); }}>
            <circle cx={cx} cy={cy} r={10} fill="#242426" stroke="var(--amber-300)" strokeWidth={1.5} />
            <text x={cx} y={cy + 4} textAnchor="middle" style={{ fill: "var(--amber-300)", fontSize: 11, fontWeight: 600 }}>{i + 1}</text></g>;
        })}
        <line x1={x(nowT)} x2={x(nowT)} y1={0} y2={H} stroke="var(--amber-300)" strokeOpacity={0.8} strokeWidth={1} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="legend">
        {mode === "retention" ? <>
          <span><span className="swatch" style={{ background: "var(--amber-300)" }} />estimated for this video</span>
          <span><span className="swatch" style={{ background: "rgba(217,138,30,.4)" }} />sensitivity band</span>
          <span><span className="swatch" style={{ background: "#85817d" }} />assumed average video (dashed)</span>
        </> : <>
          <span><span className="swatch" style={{ background: "#e8798a" }} />share of current viewers leaving per second (5 s average)</span>
          <span><span className="swatch" style={{ background: "#85817d" }} />assumed average video (dashed)</span>
        </>}
      </div>

      <div className="stats three">
        <div className="stat"><span className="v">{s.apv_pct.central.toFixed(0)}%</span><span className="k">average % viewed ({s.apv_pct.lower.toFixed(0)}–{s.apv_pct.upper.toFixed(0)}%)</span></div>
        <div className="stat"><span className="v">{s.end_pct.central.toFixed(0)}%</span><span className="k">still watching at the end</span></div>
        <div className="stat"><span className="v">{fmt(s.avd_s.central * 1000).replace(/\.\d$/, "")}</span><span className="k">average watch time (average video {fmt(s.neutral_avd_s * 1000).replace(/\.\d$/, "")})</span></div>
      </div>

      <h4 className="fdh">Riskiest moments</h4>
      <div className="rank">
        {top.map((m, i) => (
          <button key={i} className="rank-row" onClick={() => focus({ start_ms: m.start_s * 1000, end_ms: m.end_s * 1000 }, m.issue_ids[0] ?? null)}>
            <span className="rank-n">{i + 1}</span>
            <span className="mono rank-t">{s2(m.start_s)}–{s2(m.end_s)}</span>
            <span className="rank-why">{m.reasons[0]?.text}{m.reasons.length > 1 && <span className="faint"> · {m.reasons.slice(1).map((r) => r.text).join(" · ")}</span>}</span>
            <span className="faint mono">{pc(m.retention_before)} → {pc(m.retention_after)}</span>
          </button>))}
      </div>

      <details className="method">
        <summary>Method and data</summary>
        <div className="bottom" style={{ marginTop: 12 }}>
          <div>
            <h4 className="fdh">What costs the most viewers overall</h4>
            {drivers.map(([k, v]) => (
              <div key={k} className="driver"><span>{FEATURE_LABEL[k] ?? k}</span>
                <span className="dbar"><span style={{ width: `${(v / maxDriver) * 100}%` }} /></span>
                <span className="mono faint">{(v * 100).toFixed(1)} pts</span></div>))}
            <p className="faint" style={{ fontSize: 13 }}>Points = share of starting viewers lost beyond an assumed average video, summed over the video.</p>
            <h4 className="fdh">All {pred.drop_moments.length} drop moments</h4>
            {pred.drop_moments.map((m, i) => (
              <div key={i} className="dm-mini"><button className="link mono" onClick={() => focus({ start_ms: m.start_s * 1000, end_ms: m.end_s * 1000 }, null)}>{s2(m.start_s)}</button>{" "}
                {m.reasons.map((r) => `${r.text} ${Math.round(r.share * 100)}%`).join("; ")}
                {m.quote && <div className="faint" style={{ fontSize: 13 }}>“{m.quote.slice(0, 160)}{m.quote.length > 160 ? "…" : ""}”</div>}</div>))}
          </div>
          <div>
            <h4 className="fdh">Assumptions</h4>
            <p className="faint" style={{ fontSize: 13, margin: 0 }}>An assumed average video of this length keeps {pc(pred.anchors.retention_at_30s)} at 30 s and
              {" "}{pc(pred.anchors.retention_at_end)} at the end. Change these to match your channel; the features stay the same.
              The band shows how far the answer moves if every weight is half or one-and-a-half times as strong.</p>
            <div className="row" style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginTop: 10 }}>
              <label className="field">At 30 s<input type="number" step="0.05" min="0.05" max="1" value={a30} onChange={(e) => setA30(+e.target.value)} /></label>
              <label className="field">At the end<input type="number" step="0.05" min="0.05" max="1" value={aEnd} onChange={(e) => setAEnd(+e.target.value)} /></label>
              <label style={{ display: "flex", gap: 6, alignItems: "center", minHeight: 44 }}><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> These are assumptions</label>
              <button disabled={!ack || !(aEnd > 0 && aEnd <= a30 && a30 <= 1) || re.isPending} onClick={() => re.mutate()}
                title={!ack ? "Tick “These are assumptions” first" : !(aEnd > 0 && aEnd <= a30 && a30 <= 1) ? "The end value must be at most the 30 s value" : undefined}>Recompute</button>
            </div>
            {!ack && <p className="faint" style={{ fontSize: 12 }}>Recompute is available after you confirm these are assumptions.</p>}
            {re.error && <p className="err">{(re.error as Error).message}</p>}
            <h4 className="fdh" style={{ marginTop: 18 }}>How this model works ({Object.keys(pred.weights).length} features)</h4>
            <table className="cmp"><thead><tr><th>Feature</th><th>Effect</th><th>Why</th></tr></thead>
              <tbody>{Object.entries(pred.weights).map(([k, w]) => (
                <tr key={k}><td>{FEATURE_LABEL[k] ?? k}</td><td className="mono">×{Math.exp(w.weight).toFixed(2)} leaving</td>
                  <td style={{ fontSize: 13 }}>{w.rationale}</td></tr>))}</tbody></table>
            <ul className="faint" style={{ fontSize: 13 }}>{pred.notes.map((n) => <li key={n}>{n}</li>)}
              <li>Inputs used: {pred.feature_info.sources.join("; ")}.</li></ul>
          </div>
        </div>
      </details>
    </div>
  );
}
