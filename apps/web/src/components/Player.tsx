import { useEffect, useRef } from "react";
import { fmt, type Interval, type Segment } from "../api";
import { usePlayhead } from "../store";

export function Player({ src }: { src: string | null }) {
  const ref = useRef<HTMLVideoElement>(null);
  const { seekRequest, setCurrent } = usePlayhead();
  useEffect(() => {
    if (seekRequest && ref.current) ref.current.currentTime = seekRequest.ms / 1000;
  }, [seekRequest]);
  if (!src) return <div className="inset muted">No proxy video in this package (script-only or proxy missing).</div>;
  return (
    <video ref={ref} src={`${src}#t=0.1`} controls preload="metadata"
      onTimeUpdate={(e) => setCurrent(Math.round(e.currentTarget.currentTime * 1000))} />
  );
}

export function Transcript({ segments, flagged = [] }: { segments: Segment[]; flagged?: Interval[] }) {
  const { currentMs, seek } = usePlayhead();
  const activeRef = useRef<HTMLDivElement>(null);
  const active = segments.findIndex((s) => s.interval.start_ms <= currentMs && currentMs < s.interval.end_ms);
  useEffect(() => { activeRef.current?.scrollIntoView({ block: "nearest" }); }, [active]);
  if (!segments.length) return <p className="muted">No transcript in this run.</p>;
  return (
    <div className="transcript">
      {segments.map((s, i) => (
        <div key={s.segment_id} ref={i === active ? activeRef : undefined} tabIndex={0} role="button"
          className={`seg ${i === active ? "active" : ""} ${flagged.some((f) => f.end_ms > s.interval.start_ms && f.start_ms < s.interval.end_ms) ? "flagged" : ""}`} onClick={() => seek(s.interval.start_ms)}
          onKeyDown={(e) => e.key === "Enter" && seek(s.interval.start_ms)}>
          <span className="t mono">{fmt(s.interval.start_ms)}</span>
          {/* transcript is untrusted text: rendered as text, never HTML */}
          <span className="txt" lang={s.language === "hi" ? "hi" : undefined}>{s.text}
            {s.precision !== "word" && <span className="pill" title="word timing unavailable" style={{ marginLeft: 6 }}>segment timing</span>}
          </span>
        </div>
      ))}
    </div>
  );
}
