import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Prediction, type RepredictBody } from "../api";
import { usePlayhead } from "../store";
import { featureLabel, FEATURE_LABEL } from "./labels";
import { Spinner } from "./Spinner";
import { clock } from "./TimeChart";

export { FEATURE_LABEL };
const pc = (v: number) => `${(v * 100).toFixed(1)}%`;

/** "Method and data": what drives the estimate, every drop moment, and the assumptions you can change. */
export function MethodAndData({ runId, pred, onPred }: { runId: string; pred: Prediction; onPred: (p: Prediction) => void }) {
  const focus = usePlayhead((s) => s.focus);
  const [a30, setA30] = useState(pred.anchors.retention_at_30s);
  const [aEnd, setAEnd] = useState(pred.anchors.retention_at_end);
  const b = pred.baseline ?? {};
  const [adv, setAdv] = useState<{ shape_k?: number; end_drop_multiplier?: number; end_drop_fraction?: number }>({});
  const [ack, setAck] = useState(false);
  const re = useMutation({
    mutationFn: () => {
      const body: RepredictBody = { retention_at_30s: a30, retention_at_end: aEnd, acknowledged: true };
      // advanced shape values are sent only when the creator changed them (older servers ignore unknown fields)
      for (const k of ["shape_k", "end_drop_multiplier", "end_drop_fraction"] as const) if (typeof adv[k] === "number" && Number.isFinite(adv[k])) body[k] = adv[k];
      return api.repredict(runId, body);
    },
    onSuccess: (p) => onPred({ ...pred, ...p, summary: { ...pred.summary, ...p.summary } }),
  });
  const s = pred.summary;
  const drivers = Object.entries(s.excess_loss_by_feature).filter(([, v]) => v > 0.0005).sort((x, y) => y[1] - x[1]);
  const maxDriver = Math.max(...drivers.map(([, v]) => v), 1e-9);
  const valid = aEnd > 0 && aEnd <= a30 && a30 <= 1;
  const advField = (k: "shape_k" | "end_drop_multiplier" | "end_drop_fraction", label: string, hint: string, step: string) =>
    <label className="field">{label}
      <input type="number" step={step} placeholder={typeof b[k] === "number" ? String(b[k]) : "server default"} value={adv[k] ?? ""}
        onChange={(e) => setAdv({ ...adv, [k]: e.target.value === "" ? undefined : +e.target.value })} />
      <span className="hint">{hint}</span></label>;
  return (
    <details className="method">
      <summary>How this is calculated</summary>
      <div className="method-grid">
        <section>
          <h4 className="kicker">What moves the estimate</h4>
          {drivers.length ? drivers.map(([k, v]) => (
            <div key={k} className="driver"><span>{featureLabel(k)}</span>
              <span className="dbar"><span style={{ width: `${(v / maxDriver) * 100}%` }} /></span>
              <span className="num faint">{(v * 100).toFixed(1)} pts</span></div>)) : <p className="faint">Nothing moves the estimate away from the assumed average video.</p>}
          <p className="caption">Points = how far each cause pulls this video below the assumed average video, summed over the video. Not an observed loss.</p>
          <h4 className="kicker" style={{ marginTop: 20 }}>All {pred.drop_moments.length} drop moments</h4>
          <div className="dm-list">{pred.drop_moments.map((m, i) => (
            <div key={i} className="dm-mini"><button className="link num" onClick={() => focus({ start_ms: m.start_s * 1000, end_ms: m.end_s * 1000 }, null)}>{clock(m.start_s * 1000)}</button>{" "}
              {m.headline ? <b>{m.headline}. </b> : null}{m.reasons.map((r) => `${r.text} (${Math.round(r.share * 100)}%)`).join("; ")}
              <span className="faint num"> · {pc(m.retention_before)} → {pc(m.retention_after)}</span></div>))}</div>
        </section>
        <section>
          <h4 className="kicker">Assumptions</h4>
          <p className="caption">{b.description ?? <>The assumed average video of this length keeps {pc(pred.anchors.retention_at_30s)} of viewers at 30 s and {pc(pred.anchors.retention_at_end)} at the end.</>}
            {" "}Change these to match your channel; the transcript rules stay the same. The light-blue range shows how far the estimate moves if every rule is half or one-and-a-half times as strong.</p>
          <div className="field-row">
            <label className="field">Still watching at 30 s<input type="number" step="0.05" min="0.05" max="1" value={a30} onChange={(e) => setA30(+e.target.value)} /></label>
            <label className="field">Still watching at the end<input type="number" step="0.05" min="0.05" max="1" value={aEnd} onChange={(e) => setAEnd(+e.target.value)} /></label>
          </div>
          <details className="adv"><summary>Curve shape (advanced)</summary>
            <div className="field-row three">
              {advField("shape_k", "Curve shape", "How quickly early viewers leave", "0.1")}
              {advField("end_drop_multiplier", "End drop strength", "Extra leaving near the end", "0.1")}
              {advField("end_drop_fraction", "End drop length", "Share of the video it covers", "0.01")}
            </div>
            <p className="caption">Only sent if you change them. If this server doesn't support them yet they are ignored.</p>
          </details>
          <label className="check"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I understand these are assumptions, not my audience data</label>
          <div className="actions">
            <button className="soft" disabled={!ack || !valid || re.isPending} onClick={() => re.mutate()}
              title={!ack ? "Tick the box first" : !valid ? "The end value must be at most the 30 s value" : undefined}>{re.isPending && <Spinner />}Recompute estimate</button>
            {re.isSuccess && !re.isPending && <span className="faint">Updated.</span>}
          </div>
          {re.error && <p className="err">{(re.error as Error).message}</p>}
          <h4 className="kicker" style={{ marginTop: 20 }}>How the estimate works ({Object.keys(pred.weights).length} rules)</h4>
          <div className="table-wrap"><table className="cmp"><thead><tr><th>Rule</th><th>Effect</th><th>Why</th></tr></thead>
            <tbody>{Object.entries(pred.weights).map(([k, w]) => (
              <tr key={k}><td>{featureLabel(k)}</td><td className="num">×{Math.exp(w.weight).toFixed(2)}</td><td>{w.rationale}</td></tr>))}</tbody></table></div>
          <ul className="caption">{pred.notes.map((n) => <li key={n}>{n}</li>)}<li>Inputs used: {pred.feature_info.sources.join("; ")}.</li></ul>
        </section>
      </div>
    </details>
  );
}
