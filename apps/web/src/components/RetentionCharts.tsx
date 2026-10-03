import { useMemo } from "react";
import type { Interval, Prediction, Promise_, Signal } from "../api";
import { usePlayhead } from "../store";
import { GROUP_LABEL, GROUP_ORDER, type UBin, type UFinding } from "./findings";
import { featureLabel, MODALITY_COLOR, MODALITY_LABEL, modalityOf, type Modality } from "./labels";
import { clock, EstimateBadge, Legend, TimeChart } from "./TimeChart";

const pc = (v: number, d = 0) => `${(v * 100).toFixed(d)}%`;
const endMs = (p: Prediction["per_second"][number]) => (p.end_s ?? p.t + 1) * 1000;
const at = (pred: Prediction, ms: number) => pred.per_second[Math.max(0, Math.min(pred.per_second.length - 1, Math.floor(ms / 1000)))];

/** The text model's drop moments, biggest first (numbered markers on the curve). */
export const topDrops = (pred: Prediction, n = 5) => [...pred.drop_moments].sort((a, b) => b.excess_loss - a.excess_loss).slice(0, n);

export function dropHeadline(m: Prediction["drop_moments"][number]) {
  return m.headline || (m.reasons[0] ? m.reasons[0].text.replace(/^\w/, (c) => c.toUpperCase()) : "More viewers than usual may leave here");
}

/** Estimated retention (black), sensitivity band (light blue), assumed average video (grey dashed), numbered drops.
 *  Secondary mode: share of remaining viewers leaving each second. */
/** Runs of seconds where one cause dominates the modelled extra leaving (≥2 s), coloured by the signal it comes from. */
function reasonRuns(pred: Prediction) {
  const ps = pred.per_second;
  const out: { start_ms: number; end_ms: number; key: string; mod: Modality }[] = [];
  ps.forEach((p, i) => {
    const top = Object.entries(p.contributions).filter(([, v]) => v > 1e-5).sort((a, b) => b[1] - a[1])[0];
    if (!top) return;
    const last = out[out.length - 1];
    const a = i * 1000, b = endMs(p);
    if (last && last.key === top[0] && last.end_ms >= a) last.end_ms = b;
    else out.push({ start_ms: a, end_ms: b, key: top[0], mod: modalityOf(top[0]) });
  });
  return out.filter((r) => r.end_ms - r.start_ms >= 2000);
}

export function RetentionChart({ pred, height = 320, mode = "retention" }: { pred: Prediction; height?: number; mode?: "retention" | "drop" }) {
  const focus = usePlayhead((s) => s.focus);
  const runs = useMemo(() => reasonRuns(pred), [pred]);
  const mods = Array.from(new Set(runs.map((r) => r.mod)));
  const ps = pred.per_second;
  const D = pred.summary.duration_s * 1000;
  const drops = topDrops(pred);
  const leave = useMemo(() => {
    const raw = ps.map((p) => p.hazard_per_s !== undefined ? -Math.expm1(-p.hazard_per_s) : p.loss / Math.max(1e-8, p.retention + p.loss));
    const base = ps.map((p) => p.baseline_hazard_per_s !== undefined ? -Math.expm1(-p.baseline_hazard_per_s) : (p.loss - p.excess_loss) / Math.max(1e-8, p.retention + p.loss));
    const sm = (a: number[]) => a.map((_, i) => { let t = 0, n = 0; for (let j = Math.max(0, i - 2); j < Math.min(a.length, i + 3); j++) { t += a[j]; n++; } return t / n; });
    return { v: sm(raw), base: sm(base) };
  }, [ps]);
  // cap the axis near the 98th percentile so one opening spike does not flatten the rest (exact values stay in the tooltip)
  const sorted = [...leave.v, ...leave.base].sort((a, b) => a - b);
  const peak = sorted[sorted.length - 1] ?? 0.002;
  const q98 = sorted[Math.floor(sorted.length * 0.98)] ?? peak;
  const dropMax = Math.max(0.002, Math.min(peak * 1.1, q98 * 1.6));
  const capped = peak > dropMax;
  const dec = dropMax / 4 < 0.005 ? 2 : dropMax / 4 < 0.05 ? 1 : 0;
  const isRet = mode === "retention";
  return (
    <div>
      <div className="chart-head">
        <h3>{isRet ? "Viewers still watching" : "Viewers leaving per second"} <EstimateBadge /></h3>
      </div>
      <TimeChart duration={D} height={height} yMin={0} yMax={isRet ? 1 : dropMax} yTicks={4}
        yFmt={(v) => isRet ? pc(v) : pc(v, dec)} yUnit={isRet ? "% still watching" : "% leaving / s"}
        ariaLabel={isRet ? "Estimated retention curve" : "Estimated share of viewers leaving per second"}
        render={(s) => {
          const pts = (f: (p: (typeof ps)[number], i: number) => number) => ps.map((p, i) => `${s.x(endMs(p))},${s.y(f(p, i))}`).join(" ");
          return isRet ? <>
            <polygon className="ch-band" points={`${s.x(0)},${s.y(1)} ${pts((p) => p.upper)} ${[...ps].reverse().map((p) => `${s.x(endMs(p))},${s.y(p.lower)}`).join(" ")}`} />
            <polyline className="ch-neutral" points={`${s.x(0)},${s.y(1)} ${pts((p) => p.neutral)}`} />
            <polyline className="ch-line" points={`${s.x(0)},${s.y(1)} ${pts((p) => p.retention)}`} />
          </> : <>
            <polyline className="ch-neutral" points={pts((_, i) => leave.base[i])} />
            <polyline className="ch-line blue" points={pts((_, i) => leave.v[i])} />
          </>;
        }}
        overlay={(s) => <>{!isRet && runs.map((r, i) => <rect key={"r" + i} className="reason-run" x={s.x(r.start_ms)} y={s.top - 12}
            width={Math.max(2, s.x(r.end_ms) - s.x(r.start_ms))} height={7} rx={2} fill={MODALITY_COLOR[r.mod]}><title>{featureLabel(r.key)}</title></rect>)}
          {drops.map((m, i) => {
          const mid = ((m.start_s + m.end_s) / 2) * 1000;
          const k = Math.min(ps.length - 1, Math.floor(mid / 1000));
          const cy = isRet ? s.y(ps[k].retention) : s.y(leave.v[k]);
          return <g key={i} className="ch-marker" role="button" aria-label={`Drop ${i + 1} at ${clock(m.start_s * 1000)}: ${dropHeadline(m)}`}
            onClick={(e) => { e.stopPropagation(); focus({ start_ms: m.start_s * 1000, end_ms: m.end_s * 1000 }, m.issue_ids[0] ?? null); }}>
            <circle cx={s.x(mid)} cy={cy - 16} r={10} /><text x={s.x(mid)} y={cy - 12} textAnchor="middle">{i + 1}</text>
            <line x1={s.x(mid)} x2={s.x(mid)} y1={cy - 6} y2={cy} /></g>;
        })}</>}
        tooltip={(ms) => {
          const p = at(pred, ms);
          const k = Math.min(ps.length - 1, Math.floor(ms / 1000));
          const causes = Object.entries(p.contributions).sort((a, b) => b[1] - a[1]).slice(0, 2);
          const drop = pred.drop_moments.find((m) => m.start_s * 1000 <= ms && ms < m.end_s * 1000);
          return <>
            {isRet ? <>
              <div>Still watching: <b>{pc(p.retention)}</b> <span className="faint">({pc(p.lower)}–{pc(p.upper)})</span></div>
              <div className="faint">Assumed average video: {pc(p.neutral)}</div>
            </> : <>
              <div>Leaving per second: <b>{pc(leave.v[k], 2)}</b></div>
              <div className="faint">Assumed average video: {pc(leave.base[k], 2)}</div>
            </>}
            {drop && <div className="tip-strong">{dropHeadline(drop)}</div>}
            {causes.length > 0 && <div>Why: {causes.map(([c]) => featureLabel(c)).join(", ")}</div>}
          </>;
        }} />
      <Legend items={isRet
        ? [{ label: "This video", kind: "line" }, { label: "Range", kind: "band" }, { label: "Average video", kind: "dash" }]
        : [{ label: "This video", kind: "line", color: "var(--accent)" }, { label: "Average video", kind: "dash" },
          ...mods.map((m) => ({ label: `Reason: ${MODALITY_LABEL[m].toLowerCase()}`, kind: "bar" as const, color: MODALITY_COLOR[m] }))]}
        note={!isRet && capped ? "Axis capped; hover a peak for its value" : undefined} />
      {isRet && drops.length > 0 && <ol className="drop-chips" aria-label="Biggest drops">
        {drops.map((m, i) => ({ m, i })).sort((a, b) => a.m.start_s - b.m.start_s).map(({ m, i }) => (
          <li key={i}><button onClick={() => focus({ start_ms: m.start_s * 1000, end_ms: m.end_s * 1000 }, m.issue_ids[0] ?? null)}>
            <span className="drop-n num">{i + 1}</span><span className="num faint">{clock(m.start_s * 1000)}</span><span>{dropHeadline(m)}</span></button></li>))}
      </ol>}
    </div>
  );
}

/** Cumulative seconds watched per starting viewer, this video vs the assumed average video. */
export function WatchTimeChart({ pred }: { pred: Prediction }) {
  const ps = pred.per_second;
  const has = ps.some((p) => typeof p.cumulative_watch_s === "number");
  const wt = pred.summary.watch_time ?? {};
  const D = pred.summary.duration_s;
  const avd = wt.avd_s ?? pred.summary.avd_s.central;
  const navd = wt.neutral_avd_s ?? pred.summary.neutral_avd_s;
  const apv = wt.apv_pct ?? pred.summary.apv_pct.central;
  const delta = wt.delta_vs_neutral_s ?? avd - navd;
  const yMax = Math.max(1, ...ps.map((p) => Math.max(p.cumulative_watch_s ?? 0, p.neutral_cumulative_watch_s ?? 0))) * 1.08;
  return (
    <div>
      <div className="chart-head"><h3>Watch time <EstimateBadge /></h3></div>
      <div className="readout">
        <div><b className="num">{clock(avd * 1000)}</b><span>avg. watch time</span></div>
        <div><b className="num">{clock(D * 1000)}</b><span>length</span></div>
        <div><b className="num">{apv.toFixed(0)}%</b><span>viewed</span></div>
        <div><b className="num">{delta >= 0 ? "+" : "−"}{clock(Math.abs(delta) * 1000)}</b><span>vs average video</span></div>
      </div>
      {!has ? <p className="note">Curve available after re-running the analysis.</p> : <>
        <TimeChart duration={D * 1000} height={220} yMin={0} yMax={yMax} yFmt={(v) => clock(v * 1000)} yUnit="watched (m:ss)"
          ariaLabel="Cumulative watch time per starting viewer"
          render={(s) => {
            const line = (k: "cumulative_watch_s" | "neutral_cumulative_watch_s") => `${s.x(0)},${s.y(0)} ` + ps.filter((p) => typeof p[k] === "number")
              .map((p) => `${s.x(endMs(p))},${s.y(p[k] as number)}`).join(" ");
            return <><polyline className="ch-neutral" points={line("neutral_cumulative_watch_s")} /><polyline className="ch-line" points={line("cumulative_watch_s")} /></>;
          }}
          tooltip={(ms) => { const p = at(pred, ms); return <>
            <div>This video: <b>{typeof p.cumulative_watch_s === "number" ? clock(p.cumulative_watch_s * 1000) : "Not measured"}</b> watched so far</div>
            <div className="faint">Assumed average video: {typeof p.neutral_cumulative_watch_s === "number" ? clock(p.neutral_cumulative_watch_s * 1000) : "Not measured"}</div></>; }} />
        <Legend items={[{ label: "This video", kind: "line" }, { label: "Average video", kind: "dash" }]} />
      </>}
    </div>
  );
}

type Section = { label: string; start_ms: number; end_ms: number };

/** Sections by duration (a timeline-aligned bar per chapter) plus the four structure numbers creators ask about. */
export function StructureChart({ duration, chapters, markers, promises, spans, fallback }: {
  duration: number; chapters: Signal[]; markers: Signal[]; promises: Promise_[]; spans: Signal[]; fallback?: Section[];
}) {
  const { focus, currentMs } = usePlayhead();
  const secs: Section[] = chapters.length
    ? chapters.map((c) => ({ label: String((c.value as { label?: string })?.label ?? c.name ?? "Section"), start_ms: c.interval.start_ms, end_ms: c.interval.end_ms }))
    : fallback ?? [];
  const sub = markers.find((m) => m.name === "time_to_substance");
  const firstPoint = sub ? (Number(sub.value) || sub.interval.start_ms) : undefined;
  const payoff = promises.map((p) => (p.partial_interval ?? p.fulfilled_interval)?.start_ms).filter((v): v is number => v !== undefined).sort((a, b) => a - b)[0];
  const outro = spans.find((s) => s.name === "outro");
  const outroLen = outro ? outro.interval.end_ms - outro.interval.start_ms : undefined;
  const longest = Math.max(1, ...secs.map((s) => s.end_ms - s.start_ms));
  const pct = (ms: number) => `${(100 * ms) / Math.max(1, duration)}%`;
  const stat = (v: number | undefined, label: string, iv?: Interval) => <div>
    {v !== undefined ? <button className="link num" onClick={() => iv && focus(iv, null)}>{clock(v)}</button> : <b className="faint">Not measured</b>}
    <span>{label}</span></div>;
  return (
    <div>
      <div className="chart-head"><h3>Sections</h3></div>
      <div className="readout">
        <div><b className="num">{clock(duration)}</b><span>length</span></div>
        {stat(firstPoint, "first real point", firstPoint !== undefined ? { start_ms: firstPoint, end_ms: firstPoint + 5000 } : undefined)}
        {stat(payoff, "title payoff starts", payoff !== undefined ? { start_ms: payoff, end_ms: payoff + 5000 } : undefined)}
        {stat(outroLen, "outro length", outro?.interval)}
      </div>
      {!secs.length ? <p className="note">No sections detected.</p> :
        <div className="gantt" role="list">
          {secs.map((s, i) => {
            const len = s.end_ms - s.start_ms;
            const now = s.start_ms <= currentMs && currentMs < s.end_ms;
            return <button key={i} role="listitem" className={`gantt-row ${now ? "now" : ""} ${len === longest ? "longest" : ""}`} onClick={() => focus({ start_ms: s.start_ms, end_ms: s.end_ms }, null)}
              title={`${s.label}: ${clock(s.start_ms)}–${clock(s.end_ms)}`}>
              <span className="gantt-label">{s.label}</span>
              <span className="gantt-track"><span className="gantt-bar" style={{ left: pct(s.start_ms), width: `max(3px, ${pct(len)})` }} /></span>
              <span className="gantt-len num">{clock(len)}</span>
            </button>;
          })}
          <div className="gantt-axis"><span /><span className="gantt-track"><span>0:00</span><span>{clock(duration / 2)}</span><span>{clock(duration)}</span></span><span /></div>
        </div>}
    </div>
  );
}

export const GROUP_COLOR: Record<string, string> = {
  opening_promise: "#121212", progress: "#2457f5", comprehension: "#8aa4f7", questions_payoff: "#3d4a66", interruptions: "#c3d0fb", delivery: "#a8a39a", visual_pacing: "#d9d4ca",
};

/** 5-second transcript risk bars, stacked by cause. Clicking a bar seeks and hands its top finding to the caller. */
export function TranscriptRiskChart({ bins, duration, findings, onBin }: { bins: UBin[]; duration: number; findings: UFinding[]; onBin?: (b: UBin) => void }) {
  const focus = usePlayhead((s) => s.focus);
  const maxRisk = Math.max(0, ...bins.map((b) => b.risk ?? 0));
  const yMax = Math.max(20, Math.ceil(maxRisk / 10) * 10);
  const groups = GROUP_ORDER.filter((g) => bins.some((b) => (b.groups[g] ?? 0) > 0));
  const extra = Array.from(new Set(bins.flatMap((b) => Object.keys(b.groups)))).filter((g) => !GROUP_ORDER.includes(g));
  const all = [...groups, ...extra];
  const byId = Object.fromEntries(findings.map((f) => [f.id, f]));
  const binAt = (ms: number) => bins.find((b) => b.start_ms <= ms && ms < b.end_ms);
  const unknown = bins.filter((b) => b.risk === null).map((b) => ({ start_ms: b.start_ms, end_ms: b.end_ms }));
  if (!bins.length) return <p className="note">Risk bars available after re-running the analysis.</p>;
  return (
    <div>
      <TimeChart duration={duration} height={220} yMin={0} yMax={yMax} yTicks={yMax > 40 ? 4 : 2} yUnit="risk (0–100)"
        ariaLabel="Heuristic transcript risk in 5-second bars" unknown={unknown}
        onPick={(ms) => { const b = binAt(ms); if (!b) return; focus({ start_ms: b.start_ms, end_ms: b.end_ms }, null); onBin?.(b); }}
        render={(s) => bins.filter((b) => b.risk !== null && b.risk > 0).map((b) => {
          const x = s.x(b.start_ms), w = Math.max(1, s.x(b.end_ms) - x - 1);
          const sum = all.reduce((t, g) => t + (b.groups[g] ?? 0), 0);
          if (!sum) return <rect key={b.start_ms} className="ch-bar" x={x} width={w} y={s.y(b.risk!)} height={s.y(0) - s.y(b.risk!)} />;
          let y0 = 0;
          return <g key={b.start_ms}>{all.map((g) => {
            const v = ((b.groups[g] ?? 0) / sum) * b.risk!;
            if (v <= 0) return null;
            const r = <rect key={g} x={x} width={w} y={s.y(y0 + v)} height={Math.max(0.5, s.y(y0) - s.y(y0 + v))} fill={GROUP_COLOR[g] ?? "#8a867e"} />;
            y0 += v;
            return r;
          })}</g>;
        })}
        tooltip={(ms) => {
          const b = binAt(ms);
          if (!b) return <div className="faint">No bin here.</div>;
          if (b.risk === null) return <div>Not measured here.</div>;
          const top = b.top ? byId[b.top] : undefined;
          const sum = all.reduce((t, g) => t + (b.groups[g] ?? 0), 0) || 1;
          return <>
            <div>Risk <b className="num">{Math.round(b.risk)}</b> <span className="faint">of 100 · {clock(b.start_ms)}–{clock(b.end_ms)}</span></div>
            {all.filter((g) => (b.groups[g] ?? 0) > 0).map((g) => <div key={g} className="tip-row"><span className="lg lg-bar" style={{ ["--c" as string]: GROUP_COLOR[g] }} />
              {GROUP_LABEL[g] ?? g}: {Math.round(((b.groups[g] ?? 0) / sum) * b.risk!)}</div>)}
            {top ? <div className="tip-strong">{top.title}</div> : <div className="faint">No finding in this bar.</div>}
            {b.ids.length > 1 && <div className="faint">+{b.ids.length - 1} more finding{b.ids.length > 2 ? "s" : ""}</div>}
          </>;
        }} />
      <Legend items={[...all.map((g) => ({ label: GROUP_LABEL[g] ?? g, kind: "bar" as const, color: GROUP_COLOR[g] ?? "#8a867e" })),
        ...(unknown.length ? [{ label: "Not measured", kind: "hatch" as const }] : [])]}
        note={<span title="Heuristic transcript risk, not the probability of leaving">Heuristic, not a probability</span>} />
    </div>
  );
}
