import type { Prediction } from "../api";
import { usePlayhead } from "../store";
import { featureLabel } from "./labels";
import { MethodAndData } from "./Prediction";
import { dropHeadline, RetentionChart, topDrops, WatchTimeChart } from "./RetentionCharts";
import { clock, EstimateBadge, Legend, TimeChart } from "./TimeChart";

const pc = (n: number) => `${(n * 100).toFixed(2)}%`;

/** A model inspection view: survival stays monotone; measured changes appear in the hazard ratio. */
export function RetentionBreakdown({ runId, pred, onPred }: { runId: string; pred: Prediction; onPred: (p: Prediction) => void }) {
  const ms = usePlayhead((s) => s.currentMs);
  const focus = usePlayhead((s) => s.focus);
  const ps = pred.per_second;
  if (!ps.length) return <p className="note">No per-second retention data is available for this run.</p>;
  const p = ps.find((x) => x.t * 1000 <= ms && (x.end_s ?? x.t + 1) * 1000 > ms) ?? (ms >= pred.summary.duration_s * 1000 ? ps[ps.length - 1] : ps[0]);
  const ratios = ps.map((x) => x.hazard_per_s !== undefined && x.baseline_hazard_per_s !== undefined && x.baseline_hazard_per_s > 0 ? x.hazard_per_s / x.baseline_hazard_per_s : null);
  const finite = ratios.filter((x): x is number => x !== null && Number.isFinite(x));
  const ratio = ratios[ps.indexOf(p)];
  const drivers = Object.entries(p.contributions).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  const dt = p.duration_s ?? (p.end_s ?? p.t + 1) - p.t;
  const conditional = p.conditional_loss ?? p.loss / Math.max(1e-8, p.retention + p.loss);
  return <div className="deepdive">
    <section className="panel">
      <div className="chart-head"><h3>Retention breakdown <EstimateBadge /></h3></div>
      <p className="note">Follow the estimated audience, then inspect why leaving speeds up or slows down. Click a chart or a drop moment to inspect its timestamp.</p>
      <RetentionChart pred={pred} height={340} />
    </section>
    <section className="panel">
      <div className="chart-head"><h3>Departure pressure over time</h3></div>
      <p className="caption">The instantaneous leaving rate divided by the assumed baseline. Above 1× means greater modelled pressure; below 1× means less. These undulations come from the available rules and media measurements.</p>
      {finite.length ? <>
        <TimeChart duration={pred.summary.duration_s * 1000} height={230} yMin={0} yMax={Math.max(1.25, ...finite) * 1.05}
          yFmt={(v) => `${v.toFixed(1)}×`} yUnit="hazard / baseline" ariaLabel="Departure pressure relative to baseline"
          unknown={ps.flatMap((x, i) => ratios[i] === null ? [{ start_ms: x.t * 1000, end_ms: (x.end_s ?? x.t + 1) * 1000 }] : [])}
          render={(s) => <>
            <line className="ch-neutral" x1={s.x(0)} x2={s.x(pred.summary.duration_s * 1000)} y1={s.y(1)} y2={s.y(1)} />
            <path className="ch-line blue" d={ps.map((x, i) => ratios[i] === null ? "" : `${i === 0 || ratios[i - 1] === null ? "M" : "L"}${s.x((x.end_s ?? x.t + 1) * 1000)},${s.y(ratios[i]!)}`).join(" ")} />
          </>}
          tooltip={(t) => { const i = Math.min(ps.length - 1, Math.floor(t / 1000)); return <div>Departure pressure: <b>{ratios[i] === null ? "Not available" : `${ratios[i]!.toFixed(2)}× baseline`}</b></div>; }} />
        <Legend items={[{ label: "Modelled pressure", kind: "line", color: "var(--accent)" }, { label: "Baseline 1×", kind: "dash" }]} />
      </> : <p className="note">This older package does not include hazard measurements. Reanalyse to inspect departure pressure.</p>}
    </section>
    <div className="ws2">
      <section className="panel">
        <div className="chart-head"><h3>Selected moment · {clock(p.t * 1000)}</h3></div>
        <div className="kv">
          <span className="faint">Still watching at bin end</span><span className="num">{pc(p.retention)}</span>
          <span className="faint">Baseline at bin end</span><span className="num">{pc(p.neutral)}</span>
          <span className="faint">Departures among remaining viewers</span><span className="num">{pc(conditional)} in {dt.toFixed(2)} s</span>
          <span className="faint">Departure pressure</span><span className="num">{ratio === null ? "Not available" : `${ratio.toFixed(2)}× baseline`}</span>
          <span className="faint">Same-audience excess departures</span><span className="num">{(p.excess_loss * 100).toFixed(3)} percentage points</span>
        </div>
        <h4>Attributed causes at this moment</h4>
        {drivers.length ? drivers.map(([key, value]) => <p key={key}>{featureLabel(key)} <span className="num faint">· {(value * 100).toFixed(3)} pts</span></p>) : <p className="note">No positive excess departure is attributed in this bin.</p>}
        {p.protective.length > 0 && <p className="caption">Protective candidates: {p.protective.map(featureLabel).join(" · ")}. The strongest eligible protective rule is capped and cannot cancel a detected risk; measured micro-variation is a separate signed adjustment.</p>}
        <p className="caption">Attribution compares hazards for the same remaining audience within this bin. Its sum across time is a different quantity from the gap between the two final curves.</p>
      </section>
      <section className="panel">
        <div className="chart-head"><h3>Priority drop moments</h3></div>
        {topDrops(pred, 8).map((m, i) => <div className="dm-mini" key={m.start_s}>
          <button className="link num" onClick={() => focus({ start_ms: m.start_s * 1000, end_ms: m.end_s * 1000 }, m.issue_ids[0] ?? null)}>{i + 1}. {clock(m.start_s * 1000)}–{clock(m.end_s * 1000)}</button>
          <p><b>{dropHeadline(m)}</b></p>
          <p className="caption">{pc(m.retention_before)} → {pc(m.retention_after)} still watching · {(m.excess_loss * 100).toFixed(2)} pts attributed excess departures</p>
          {m.quote && <blockquote>{m.quote}</blockquote>}
        </div>)}
        {!pred.drop_moments.length && <p className="note">No excess-loss window was ranked by this model.</p>}
      </section>
    </div>
    <section className="panel"><RetentionChart pred={pred} mode="drop" height={240} /></section>
    <section className="panel"><WatchTimeChart pred={pred} /></section>
    <section className="panel"><MethodAndData key={pred.prediction_id} runId={runId} pred={pred} onPred={onPred} />
      <p className="caption">The band changes rule strength to 0.5× and 1.5×. It is an assumption sensitivity band, not a confidence interval. Survival does not increase: changing slopes and departure pressure show changes in attention assumptions.</p>
    </section>
  </div>;
}
