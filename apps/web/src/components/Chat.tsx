import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, fmt, type ChatAnswer, type ChatMsg } from "../api";
import { usePlayhead } from "../store";

const s2 = (ms: number) => fmt(ms).replace(/\.\d$/, "");
const STARTERS = ["Which first-30-second passages deserve a clarity review?", "Which questions does the video leave open the longest?",
  "What is the safest edit that keeps every point?", "Explain the strongest transcript review cue and its alternative explanation."];

/** Grounded assistant: answers only from this run's transcript, findings and text-model prediction. */
export function ChatPanel({ runId, onClose }: { runId: string; onClose: () => void }) {
  const { focus, selection } = usePlayhead();
  const [msg, setMsg] = useState("");
  const [turns, setTurns] = useState<{ q: string; a?: ChatAnswer; err?: string }[]>([]);
  const ask = useMutation({
    mutationFn: (q: string) => {
      const history: ChatMsg[] = turns.flatMap((t) => t.a ? [{ role: "user", content: t.q }, { role: "assistant", content: t.a.answer }] as ChatMsg[] : []);
      return api.chat(runId, { message: q, history: history.slice(-8), selection });
    },
    onMutate: (q) => setTurns((t) => [...t, { q }]),
    onSuccess: (a) => setTurns((t) => t.map((x, i) => i === t.length - 1 ? { ...x, a } : x)),
    onError: (e) => setTurns((t) => t.map((x, i) => i === t.length - 1 ? { ...x, err: (e as Error).message } : x)),
  });
  const send = (q: string) => { if (q.trim() && !ask.isPending) { ask.mutate(q.trim()); setMsg(""); } };

  return (
    <aside className="chat" role="dialog" aria-label="Ask about this video">
      <div className="chat-head">
        <span><span className="faint" style={{ fontSize: 11, letterSpacing: ".08em" }}>ASSISTANT · GROUNDED IN THIS ANALYSIS</span><br /><b>Ask about this video</b></span>
        <button className="ghost" aria-label="Close assistant" title="Close" onClick={onClose}>×</button>
      </div>
      <p className="faint chat-note">Answers come only from this analysis: transcript passages retrieved for your question, findings and the uncalibrated text model.
        Quotes are checked against the transcript; edit warnings come from fixed rules. Sends transcript text to Cerebras.
        {selection && <> Looking at <b className="mono">{s2(selection.start_ms)}–{s2(selection.end_ms)}</b>.</>}</p>
      <div className="chat-log">
        {!turns.length && <div className="chat-starters">{STARTERS.map((q) => <button key={q} onClick={() => send(q)}>{q}</button>)}</div>}
        {turns.map((t, i) => (
          <div key={i} className="chat-turn">
            <div className="chat-q">{t.q}</div>
            {!t.a && !t.err && <div className="muted">Thinking…</div>}
            {t.err && <div className="err">{t.err}</div>}
            {t.a && <div className="chat-a">
              <div style={{ whiteSpace: "pre-wrap" }}>{t.a.answer}</div>
              {!!t.a.edit_warnings.length && <div className="callout" role="note"><b>Check before editing</b>
                <ul>{t.a.edit_warnings.map((w) => <li key={w}>{w}</li>)}</ul></div>}
              {!!t.a.quotes.length && <div className="chat-rows">
                <div className="rh"><span>Quoted lines</span><span className="faint">{t.a.quotes.filter((q) => q.verified).length} of {t.a.quotes.length} verified</span></div>
                {t.a.quotes.map((q, k) => (
                  <button key={k} className="chat-row" disabled={q.start_ms === null} title={q.verified ? "Jump to this line" : "Not found in the transcript"}
                    onClick={() => q.start_ms !== null && focus({ start_ms: q.start_ms, end_ms: q.start_ms + 5000 }, null)}>
                    <span className="txt">“{q.text}”</span>
                    {q.verified && q.start_ms !== null ? <span className="st time">{s2(q.start_ms)}</span> : null}
                    <span className={`st ${q.verified ? "ok" : "bad"}`}>{q.verified ? "✓ In transcript" : "✕ Not found"}</span>
                  </button>))}</div>}
              {!!t.a.sources?.length && <details className="chat-rows" style={{ padding: 0 }}>
                <summary className="rh" style={{ cursor: "pointer" }}><span>Transcript passages retrieved</span><span className="faint">{t.a.sources.length}</span></summary>
                {t.a.sources.map((src, k) => (
                  <button key={k} className="chat-row" onClick={() => focus({ start_ms: src.start_ms, end_ms: src.end_ms }, null)}>
                    <span className="st time">{s2(src.start_ms)}–{s2(src.end_ms)}</span>
                    <span className="txt faint">matched: {src.matched.join(", ") || "near the selected moment"}</span></button>))}
              </details>}
              {!!t.a.citations.length && <div className="chat-rows">
                <div className="rh"><span>Cited moments</span><span className="faint">{t.a.citations.length}</span></div>
                {t.a.citations.map((c, k) => (
                  <button key={k} className="chat-row" onClick={() => focus({ start_ms: c.start_ms, end_ms: c.end_ms }, null)}>
                    <span className="st time">{s2(c.start_ms)}–{s2(c.end_ms)}</span><span className="txt">{c.why}</span></button>))}
                {t.a.dropped_citations > 0 && <div className="chat-row faint">{t.a.dropped_citations} citation(s) outside the video were dropped</div>}
              </div>}
            </div>}
          </div>))}
      </div>
      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(msg); }}>
        <textarea rows={2} value={msg} placeholder="Ask about a moment, a finding, or an edit…" onChange={(e) => setMsg(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(msg); } }} />
        <button className="hero" disabled={ask.isPending || !msg.trim()} title={!msg.trim() ? "Type a question first" : undefined}>Ask</button>
      </form>
    </aside>
  );
}
