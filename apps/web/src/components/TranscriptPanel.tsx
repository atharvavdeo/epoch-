import { useEffect, useMemo, useRef, useState } from "react";
import { fmt, type Issue, type Promise_, type Segment, type Signal, type Word } from "../api";
import { overlaps, usePlayhead } from "../store";
import { issueLabel } from "./Timeline";

type Mark = { label: string; kind: "structure" | "finding" | "uncertain"; tone?: string };
const SPAN_LABEL: Record<string, string> = {
  viewer_question: "question", open_loop: "open loop", recap: "recap", cta: "CTA", sponsor: "sponsor", greeting: "greeting",
  outro: "outro", tangent_candidate: "tangent?", cold_open: "cold open",
};

/** Transcript as an analytical canvas: follows playback word by word, searchable, with toggleable margin layers. */
export function TranscriptPanel({ segments, words, issues, spans, markers, promises }: {
  segments: Segment[]; words: Word[]; issues: Issue[]; spans: Signal[]; markers: Signal[]; promises: Promise_[];
}) {
  const { currentMs, seek, focus, selection } = usePlayhead();
  const [q, setQ] = useState("");
  const [hit, setHit] = useState(0);
  const [layers, setLayers] = useState({ structure: true, finding: true, uncertain: false });
  const activeRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const wordsBySeg = useMemo(() => {
    const m: Record<string, Word[]> = {};
    for (const w of words) (m[w.segment_id] ??= []).push(w);
    return m;
  }, [words]);

  const marks = useMemo(() => segments.map((s) => {
    const out: Mark[] = [];
    for (const sp of spans) if (overlaps(sp.interval, s.interval) && sp.interval.start_ms >= s.interval.start_ms)
      out.push({ label: SPAN_LABEL[sp.name] ?? sp.name, kind: "structure" });
    for (const m of markers) {
      const at = m.name === "time_to_substance" ? Number(m.value) : m.interval.start_ms;
      if (s.interval.start_ms <= at && at < s.interval.end_ms) out.push({ label: m.name === "hook" ? "hook" : "first real content", kind: "structure" });
    }
    for (const p of promises) {
      const begin = (p.partial_interval ?? p.fulfilled_interval)?.start_ms;
      if (begin !== undefined && s.interval.start_ms <= begin && begin < s.interval.end_ms) out.push({ label: "title payoff starts", kind: "structure" });
    }
    for (const i of issues) if (i.review_status !== "dismissed" && overlaps(i.affected_interval, s.interval)
      && i.affected_interval.start_ms >= s.interval.start_ms - 1) out.push({ label: issueLabel(i.type), kind: "finding", tone: i.severity });
    if (s.precision !== "word") out.push({ label: "segment timing", kind: "uncertain" });
    return out;
  }), [segments, spans, markers, promises, issues]);

  const matches = useMemo(() => {
    const n = q.trim().toLowerCase();
    return n.length < 2 ? [] : segments.map((s, i) => (s.text.toLowerCase().includes(n) ? i : -1)).filter((i) => i >= 0);
  }, [q, segments]);
  const active = segments.findIndex((s) => s.interval.start_ms <= currentMs && currentMs < s.interval.end_ms);
  useEffect(() => {
    const el = activeRef.current, box = boxRef.current;
    if (el && box && !q) box.scrollTo({ top: el.offsetTop - box.clientHeight / 3, behavior: "smooth" });
  }, [active, q]);
  const jump = (k: number) => {
    if (!matches.length) return;
    const i = matches[((k % matches.length) + matches.length) % matches.length];
    setHit(k);
    focus(segments[i].interval, null);
    document.getElementById(`seg-${segments[i].segment_id}`)?.scrollIntoView({ block: "center" });
  };

  if (!segments.length) return <p className="muted">No transcript in this run.</p>;
  return (
    <div className="tp">
      <div className="tp-tools">
        <input value={q} placeholder="Search the transcript" aria-label="Search the transcript" onChange={(e) => { setQ(e.target.value); setHit(0); }}
          onKeyDown={(e) => e.key === "Enter" && jump(e.shiftKey ? hit - 1 : hit + 1)} />
        {q.trim().length >= 2 && <span className="faint" style={{ fontSize: 13 }}>{matches.length} match{matches.length === 1 ? "" : "es"}</span>}
        <span style={{ flex: 1 }} />
        {(["structure", "finding", "uncertain"] as const).map((k) => (
          <button key={k} className={`chip ${layers[k] ? "on" : ""}`} onClick={() => setLayers({ ...layers, [k]: !layers[k] })}>
            {k === "structure" ? "Structure" : k === "finding" ? "Findings" : "Timing"}</button>))}
      </div>
      <div className="transcript" ref={boxRef}>
        {segments.map((s, i) => {
          const ws = wordsBySeg[s.segment_id];
          const sel = selection && overlaps(selection, s.interval);
          const m = marks[i].filter((x) => layers[x.kind]);
          const isHit = matches.includes(i);
          return (
            <div key={s.segment_id} id={`seg-${s.segment_id}`} ref={i === active ? activeRef : undefined}
              className={`seg ${i === active ? "active" : ""} ${sel ? "selected" : ""} ${isHit ? "hit" : ""}`}>
              <button className="t" onClick={() => focus(s.interval, null)} title="select this line">{fmt(s.interval.start_ms)}</button>
              <span className="txt" lang={s.language === "hi" ? "hi" : undefined}>
                {/* transcript is untrusted text: rendered as text nodes, never HTML */}
                {ws && ws.length ? ws.map((w) => {
                  const now = w.start_ms !== null && w.end_ms !== null && w.start_ms <= currentMs && currentMs < w.end_ms;
                  return <span key={w.word_id} className={`w ${now ? "now" : ""} ${w.start_ms === null ? "untimed" : ""}`}
                    onClick={() => { focus(s.interval, null); if (w.start_ms !== null) seek(w.start_ms); }}>{w.text} </span>;
                }) : <span onClick={() => focus(s.interval, null)}>{s.text}</span>}
              </span>
              <span className="tp-margin">
                {m.map((x, k) => <span key={k} className={`mk ${x.kind} ${x.tone ?? ""}`}>{x.label}</span>)}
              </span>
            </div>);
        })}
      </div>
    </div>
  );
}
