import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, fmt, type ChatAnswer, type ChatMsg, type Prediction } from "../api";
import { usePlayhead } from "../store";
import type { DeepData } from "./DeepDive";
import { IconChat, IconClose, IconHistory, IconPlus, IconSend, IconTrash } from "./Icons";
import { dropHeadline, topDrops } from "./RetentionCharts";
import { Skeleton, Spinner } from "./Spinner";

const s2 = (ms: number) => fmt(ms).replace(/\.\d$/, "");
const STARTERS = ["Where do viewers most likely leave, and why?", "What is the safest edit that keeps every point?",
  "Which questions does the video leave open the longest?", "Is the first 30 seconds clear enough?"];
type Turn = { q: string; a?: ChatAnswer; err?: string; at: number };
type Thread = { id: string; title: string; at: number; turns: Turn[] };
const key = (run: string) => `epoch.chat.${run}`;
const loadThreads = (run: string): Thread[] => { try { const v = JSON.parse(localStorage.getItem(key(run)) ?? "[]"); return Array.isArray(v) ? v : []; } catch { return []; } };
const saveThreads = (run: string, t: Thread[]) => { try { localStorage.setItem(key(run), JSON.stringify(t.slice(0, 30))); } catch { /* storage blocked or full */ } };

/** Grounded assistant: a chat layout with a per-run history sidebar and a strip showing what it can draw on. */
export function ChatPanel({ runId, onClose, pred, deep }: { runId: string; onClose: () => void; pred?: Prediction; deep?: DeepData }) {
  const { focus, selection } = usePlayhead();
  const [threads, setThreads] = useState<Thread[]>(() => loadThreads(runId));
  const [current, setCurrent] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [side, setSide] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const outputs = useQuery({ queryKey: ["outputs", runId], queryFn: () => api.outputs(runId), staleTime: 600_000 });
  const thread = threads.find((t) => t.id === current);
  const turns = thread?.turns ?? [];
  useEffect(() => { saveThreads(runId, threads); }, [runId, threads]);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" }); }, [turns.length, turns[turns.length - 1]?.a]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);

  const update = (id: string, f: (t: Thread) => Thread) => setThreads((all) => all.map((t) => t.id === id ? f(t) : t));
  const ask = useMutation({
    mutationFn: ({ q }: { q: string; id: string }) => {
      const history: ChatMsg[] = turns.flatMap((t) => t.a ? [{ role: "user", content: t.q }, { role: "assistant", content: t.a.answer }] as ChatMsg[] : []);
      return api.chat(runId, { message: q, history: history.slice(-8), selection });
    },
    onSuccess: (a, { id }) => update(id, (t) => ({ ...t, turns: t.turns.map((x, i) => i === t.turns.length - 1 ? { ...x, a } : x) })),
    onError: (e, { id }) => update(id, (t) => ({ ...t, turns: t.turns.map((x, i) => i === t.turns.length - 1 ? { ...x, err: (e as Error).message } : x) })),
  });
  const send = (q: string) => {
    q = q.trim();
    if (!q || ask.isPending) return;
    let id = current;
    if (!id || !thread) {
      id = `t${Date.now()}`;
      const nt: Thread = { id, title: q.slice(0, 80), at: Date.now(), turns: [{ q, at: Date.now() }] };
      setThreads((all) => [nt, ...all]);
      setCurrent(id);
    } else update(id, (t) => ({ ...t, at: Date.now(), turns: [...t.turns, { q, at: Date.now() }] }));
    ask.mutate({ q, id });
    setMsg("");
  };

  const ocr = outputs.data ? outputs.data.items.some((f) => /ocr/i.test(f.stage) || /ocr/i.test(f.name)) : null;
  const drops = pred ? topDrops(pred, 3) : [];
  return (
    <div className="chat-overlay" role="dialog" aria-label="Ask about this video">
      <div className="chat-scrim" onClick={onClose} />
      <aside className={`chat2 ${side ? "side-open" : ""}`}>
        <nav className="chat-side" aria-label="Past questions">
          <div className="chat-side-head"><span className="kicker">History</span>
            <button className="icon-btn" aria-label="New conversation" title="New conversation" onClick={() => { setCurrent(null); setSide(false); }}><IconPlus /></button></div>
          {!threads.length && <p className="faint chat-side-empty">Your questions for this video will appear here.</p>}
          <ul>{threads.map((t) => <li key={t.id} className={t.id === current ? "on" : ""}>
            <button className="chat-side-item" onClick={() => { setCurrent(t.id); setSide(false); }}>
              <IconChat size={15} /><span>{t.title}</span></button>
            <button className="icon-btn sm" aria-label="Delete conversation" title="Delete" onClick={() => { setThreads((all) => all.filter((x) => x.id !== t.id)); if (current === t.id) setCurrent(null); }}><IconTrash size={15} /></button>
          </li>)}</ul>
        </nav>
        <div className="chat-main">
          <header className="chat-top">
            <button className="icon-btn chat-hist-btn" aria-label="Show history" onClick={() => setSide(!side)}><IconHistory /></button>
            <div className="chat-title"><b>Ask about this video</b><span className="faint">Answers use only this analysis{selection ? <> · looking at <span className="num">{s2(selection.start_ms)}–{s2(selection.end_ms)}</span></> : null}</span></div>
            <button className="icon-btn" aria-label="Close assistant" title="Close (Esc)" onClick={onClose}><IconClose /></button>
          </header>
          <div className="chat-context" aria-label="What the assistant can use">
            <span className="ctx"><b className="num">{pred ? `${pred.summary.apv_pct.central.toFixed(0)}%` : "—"}</b> viewed <em>estimate</em></span>
            <span className="ctx"><b className="num">{pred ? s2(pred.summary.avd_s.central * 1000) : "—"}</b> avg. watch</span>
            {drops.map((m, i) => <button key={i} className="ctx link-ctx" onClick={() => focus({ start_ms: m.start_s * 1000, end_ms: m.end_s * 1000 }, null)} title={dropHeadline(m)}>
              <b className="num">{s2(m.start_s * 1000)}</b> drop</button>)}
            <span className={`ctx ${deep?.voice ? "" : "off"}`}>Voice {deep?.voice?.summary?.overall_wpm ? `${deep.voice.summary.overall_wpm} wpm` : "not measured"}</span>
            <span className={`ctx ${deep?.audio?.loudness?.integrated_lufs !== undefined ? "" : "off"}`}>Audio {deep?.audio?.loudness?.integrated_lufs !== undefined ? `${deep.audio.loudness.integrated_lufs.toFixed(1)} LUFS` : "not measured"}</span>
            <span className={`ctx ${ocr ? "" : "off"}`}>On-screen text {ocr === null ? "…" : ocr ? "read" : "not inspected"}</span>
          </div>
          <div className="chat-log" ref={logRef}>
            {!turns.length && <div className="chat-empty">
              <span className="chat-empty-icon"><IconChat size={26} /></span>
              <h3>What would you like to know?</h3>
              <div className="chat-starters">{STARTERS.map((q) => <button key={q} className="chip" onClick={() => send(q)}>{q}</button>)}</div>
            </div>}
            {turns.map((t, i) => (
              <div key={i} className="chat-turn">
                <div className="bubble user">{t.q}</div>
                {!t.a && !t.err && <div className="bubble bot thinking"><Skeleton w="80%" /><Skeleton w="60%" /><Skeleton w="70%" /></div>}
                {t.err && <div className="bubble bot err">{t.err}</div>}
                {t.a && <div className="bubble bot">
                  <div className="answer">{t.a.answer}</div>
                  {!!t.a.edit_warnings.length && <div className="callout" role="note"><b>Check before editing</b><ul>{t.a.edit_warnings.map((w) => <li key={w}>{w}</li>)}</ul></div>}
                  {!!t.a.citations.length && <div className="cites">{t.a.citations.map((c, k) => (
                    <button key={k} className="cite num" title={c.why} onClick={() => focus({ start_ms: c.start_ms, end_ms: c.end_ms }, null)}>{s2(c.start_ms)}–{s2(c.end_ms)}</button>))}</div>}
                  {!!t.a.quotes.length && <details className="quotes"><summary>{t.a.quotes.filter((q) => q.verified).length} of {t.a.quotes.length} quotes found in the transcript</summary>
                    {t.a.quotes.map((q, k) => <button key={k} className="quote-row" disabled={q.start_ms === null}
                      onClick={() => q.start_ms !== null && focus({ start_ms: q.start_ms, end_ms: q.start_ms + 5000 }, null)}>
                      <span>“{q.text}”</span><span className={`st ${q.verified ? "ok" : "bad"}`}>{q.verified ? "Found" : "Not found"}</span></button>)}
                  </details>}
                </div>}
              </div>))}
          </div>
          <form className="composer" onSubmit={(e) => { e.preventDefault(); send(msg); }}>
            <textarea rows={1} value={msg} placeholder="Ask about a moment, a finding or an edit…" aria-label="Your question" onChange={(e) => setMsg(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(msg); } }} />
            <button className="hero send" disabled={ask.isPending || !msg.trim()} aria-label="Send">{ask.isPending ? <Spinner /> : <IconSend />}</button>
          </form>
          <p className="chat-foot faint">Sends transcript passages to the configured language model. Quotes are checked against the transcript.</p>
        </div>
      </aside>
    </div>
  );
}
