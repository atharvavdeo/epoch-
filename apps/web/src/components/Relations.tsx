import { fmt, type Relations } from "../api";
import { usePlayhead } from "../store";

const s2 = (ms: number) => fmt(ms).replace(/\.\d$/, "");
const KIND: Record<string, string> = {
  immediate: "answered within 10 s", short: "answered within a minute", open_loop: "open loop (> 1 min)",
  framing: "framing question (the whole video answers it)", no_callback: "never returned to in words",
};

/** Transcript relations: how questions, ideas and examples connect across the narration (deterministic text measures). */
export function RelationsView({ rel }: { rel: Relations }) {
  const { focus } = usePlayhead();
  const go = (a: number, b: number) => focus({ start_ms: a, end_ms: b }, null);
  const wins = rel.cognitive_load.windows;
  const maxNew = Math.max(1, ...wins.map((w) => w.new_terms));
  return (
    <div className="rel">
      <p className="muted" style={{ fontSize: 14, marginTop: 0 }}>{rel.method}</p>
      {rel.unpunctuated_ms > 30_000 && <p className="pill amber" style={{ display: "inline-block" }}>
        {Math.round(rel.unpunctuated_ms / 1000)} s of the transcript has no punctuation or casing (speech recognition output);
        sentence-based measures (concreteness by names, rhythm, abstract stretches) are not computed there.</p>}
      <div className="stats">
        <div className="stat"><span className="v">{rel.summary.questions}</span><span className="k">questions the narrator asks</span></div>
        <div className="stat"><span className="v">{rel.summary.open_loops}</span><span className="k">left open for over a minute</span></div>
        <div className="stat"><span className="v">{rel.summary.no_callback}</span><span className="k">never returned to in words</span></div>
        <div className="stat"><span className="v">{Math.round(rel.summary.concrete_share * 100)}%</span><span className="k">sentences with a concrete marker</span></div>
      </div>

      <h4 className="fdh">Question → answer</h4>
      <table className="cmp"><thead><tr><th>Asked</th><th>Question</th><th>Returns to it</th><th>Gap</th><th>What this means</th></tr></thead>
        <tbody>{rel.questions.map((q, i) => (
          <tr key={i}>
            <td><button className="link mono" onClick={() => go(q.question.start_ms, q.question.end_ms)}>{s2(q.question.start_ms)}</button></td>
            <td>“{q.question.text}”</td>
            <td>{q.answer ? <button className="link" onClick={() => go(q.answer!.start_ms, q.answer!.end_ms)}>
              <span className="mono">{s2(q.answer.start_ms)}</span> “{q.answer.text.slice(0, 90)}{q.answer.text.length > 90 ? "…" : ""}”</button>
              : <span className="faint">—</span>}</td>
            <td className="mono">{q.gap_ms !== null ? `${Math.round(q.gap_ms / 1000)} s` : "—"}</td>
            <td>{KIND[q.kind]}{q.shared_words.length > 0 && <div className="faint" style={{ fontSize: 12 }}>shared words: {q.shared_words.join(", ")}</div>}</td>
          </tr>))}</tbody></table>
      <p className="faint" style={{ fontSize: 13 }}>An open loop holds viewers while it is open; it only hurts if it is never paid off.
        “Returns to it” is the first later sentence reusing the question's words: a pointer to check, not proof of a good answer.</p>

      <h4 className="fdh">Abstract stretches (no example, number or named thing for 40 s or more)</h4>
      {rel.abstract_stretches.length ? rel.abstract_stretches.map((x, i) => (
        <button key={i} className="dm" onClick={() => go(x.start_ms, x.end_ms)}>
          <span className="mono">{s2(x.start_ms)}–{s2(x.end_ms)}</span>
          <span className="quote-orig" style={{ fontSize: 13 }}>“{x.quote.slice(0, 220)}…”</span></button>))
        : <p className="faint">None found in the punctuated part of the transcript.</p>}

      <h4 className="fdh">Explained after first use</h4>
      {rel.term_dependencies.length ? rel.term_dependencies.map((t, i) => (
        <p key={i}><b>{t.term}</b>: used at <button className="link mono" onClick={() => go(t.used_at.start_ms, t.used_at.end_ms)}>{s2(t.used_at.start_ms)}</button>,
          explained at <button className="link mono" onClick={() => go(t.explained_at.start_ms, t.explained_at.end_ms)}>{s2(t.explained_at.start_ms)}</button></p>))
        : <p className="faint">No named idea was used before the sentence that explains it.</p>}

      <h4 className="fdh">New ideas per minute (cognitive load)</h4>
      <div className="loadbars" role="img" aria-label="New content words per minute">
        {wins.map((w) => (
          <button key={w.start_ms} className={`lb ${w.load}`} title={`${s2(w.start_ms)}: ${w.new_terms} new words, ${w.mean_sentence_words} words/sentence`}
            onClick={() => go(w.start_ms, w.end_ms)}>
            <span style={{ height: `${(w.new_terms / maxNew) * 100}%` }} /><em>{Math.floor(w.start_ms / 60000)}</em></button>))}
      </div>
      <p className="faint" style={{ fontSize: 13 }}>Bars = content words never heard before that minute (median {rel.cognitive_load.median_new_terms_per_min}).
        Amber = over 1.5× the median (dense), grey = under half (thin). The first minute is new by definition and never flagged.
        {rel.cognitive_load.long_sentences.length > 0 && ` ${rel.cognitive_load.long_sentences.length} sentences run over 30 words.`}</p>

      <h4 className="fdh">Rhythm</h4>
      <p className="faint" style={{ fontSize: 13, marginTop: 0 }}>{rel.rhythm.flat.length
        ? `Very even sentence lengths (monotone risk) at ${rel.rhythm.flat.map((w) => s2(w.start_ms)).join(", ")}.`
        : "No 30 s stretch with unusually even sentence lengths."}</p>
      {!!rel.rhythm.sections.length && <div className="sections">{rel.rhythm.sections.map((c) => (
        <button key={c.start_ms} className="sec" style={{ flexGrow: c.duration_s }} title={`${c.label} · ${c.duration_s} s`}
          onClick={() => go(c.start_ms, c.end_ms)}><span>{c.label}</span><em>{Math.round(c.duration_s)} s</em></button>))}</div>}
    </div>
  );
}
