import { useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { fmt, type Interval } from "../api";
import { usePlayhead } from "../store";

export const clock = (ms: number) => fmt(ms).replace(/\.\d$/, "");

/** Container width in px (charts draw at real pixel size so axis text stays readable on a phone). */
export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(640);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setW(el.clientWidth || 640);
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(200, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

export type Scale = { x: (ms: number) => number; y: (v: number) => number; left: number; right: number; top: number; bottom: number; w: number; h: number };

function niceTimeStep(duration: number, width: number) {
  const target = duration / Math.max(2, Math.floor(width / 90));
  return [5e3, 10e3, 15e3, 30e3, 60e3, 120e3, 300e3, 600e3].find((s) => s >= target) ?? 900e3;
}

/** Playhead as its own component so only this line re-renders while the video plays. */
function PlayheadLine({ s }: { s: Scale }) {
  const ms = usePlayhead((st) => st.currentMs);
  const x = s.x(ms);
  return <line className="ch-playhead" x1={x} x2={x} y1={s.top - 4} y2={s.bottom} />;
}
function SelectionRect({ s }: { s: Scale }) {
  const sel = usePlayhead((st) => st.selection);
  if (!sel) return null;
  const a = s.x(sel.start_ms), b = s.x(sel.end_ms);
  return <rect className="ch-selection" x={a} y={s.top} width={Math.max(2, b - a)} height={s.bottom - s.top} />;
}

/** A time-based chart frame: x = video time, y = one quantity with units. Click anywhere to seek the player. */
export function TimeChart({ duration, height = 240, yMin, yMax, yTicks = 4, yFmt = (v) => String(Math.round(v)), yUnit, ariaLabel,
  render, tooltip, onPick, unknown = [], overlay }: {
  duration: number; height?: number; yMin: number; yMax: number; yTicks?: number; yFmt?: (v: number) => string; yUnit: string; ariaLabel: string;
  render: (s: Scale) => ReactNode; tooltip?: (ms: number) => ReactNode; onPick?: (ms: number) => void; unknown?: Interval[];
  overlay?: (s: Scale) => ReactNode;
}) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const focus = usePlayhead((st) => st.focus);
  const [hover, setHover] = useState<{ ms: number; px: number } | null>(null);
  const hatch = useId().replace(/:/g, "");
  const left = 46, right = w - 12, top = 14, bottom = height - 26;
  const D = Math.max(1, duration);
  const span = Math.max(1e-9, yMax - yMin);
  const s: Scale = {
    x: (ms) => left + (Math.max(0, Math.min(D, ms)) / D) * (right - left),
    y: (v) => bottom - ((Math.max(yMin, Math.min(yMax, v)) - yMin) / span) * (bottom - top),
    left, right, top, bottom, w, h: height,
  };
  const step = niceTimeStep(D, w);
  const xt = Array.from({ length: Math.floor(D / step) + 1 }, (_, i) => i * step).filter((t) => t <= D * 0.98 || t === 0);
  const yt = Array.from({ length: yTicks + 1 }, (_, i) => yMin + (span * i) / yTicks);
  const msAt = (clientX: number, el: Element) => {
    const r = el.getBoundingClientRect();
    const px = clientX - r.left;
    return { ms: Math.max(0, Math.min(D, ((px - left) / (right - left)) * D)), px };
  };
  const pick = (ms: number) => onPick ? onPick(ms) : focus({ start_ms: Math.round(ms), end_ms: Math.min(D, Math.round(ms) + 5000) }, null);
  return (
    <div className="chart" ref={ref}>
      <svg width={w} height={height} role="img" aria-label={`${ariaLabel}. Horizontal axis: video time. Vertical axis: ${yUnit}. Click to jump the video there.`}
        onMouseMove={(e) => setHover(msAt(e.clientX, e.currentTarget))} onMouseLeave={() => setHover(null)}
        onClick={(e) => pick(msAt(e.clientX, e.currentTarget).ms)}>
        <defs>
          <pattern id={hatch} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" className="hatch-bg" /><line x1="0" y1="0" x2="0" y2="6" className="hatch-line" strokeWidth="2" />
          </pattern>
        </defs>
        {yt.map((v) => <g key={v}>
          <line className="ch-grid" x1={left} x2={right} y1={s.y(v)} y2={s.y(v)} />
          <text className="ch-tick" x={left - 8} y={s.y(v) + 4} textAnchor="end">{yFmt(v)}</text></g>)}
        {xt.map((t) => <text key={t} className="ch-tick" x={s.x(t)} y={height - 8} textAnchor={t === 0 ? "start" : "middle"}>{clock(t)}</text>)}
        {unknown.map((u, i) => <rect key={i} x={s.x(u.start_ms)} y={top} width={Math.max(1, s.x(u.end_ms) - s.x(u.start_ms))} height={bottom - top}
          fill={`url(#${hatch})`} opacity={0.9}><title>Not measured {clock(u.start_ms)}–{clock(u.end_ms)}</title></rect>)}
        <SelectionRect s={s} />
        {render(s)}
        <PlayheadLine s={s} />
        {hover && <line className="ch-hover" x1={s.x(hover.ms)} x2={s.x(hover.ms)} y1={top} y2={bottom} />}
        {overlay?.(s)}
      </svg>
      <span className="ch-unit">{yUnit}</span>
      {hover && tooltip && <div className="ch-tip" style={{ left: Math.min(Math.max(8, hover.px + 14), w - 248), top: 10 }}>
        <div className="ch-tip-t">{clock(hover.ms)}</div>{tooltip(hover.ms)}</div>}
    </div>
  );
}

/** The single honesty marker on estimated charts; the full note lives in the tooltip. */
export function EstimateBadge({ label = "Estimate" }: { label?: string }) {
  return <span className="badge-est" tabIndex={0} title="Estimated from the transcript and media, not your real audience"
    aria-label={`${label}: estimated from the transcript and media, not your real audience`}>{label}</span>;
}

export function Legend({ items, note }: { items: { label: string; kind: "line" | "dash" | "band" | "bar" | "hatch" | "dot"; color?: string }[]; note?: ReactNode }) {
  return <div className="legend">
    {items.map((i) => <span key={i.label}><span className={`lg lg-${i.kind}`} style={i.color ? { ["--c" as string]: i.color } : undefined} />{i.label}</span>)}
    {note && <span className="legend-note">{note}</span>}
  </div>;
}
