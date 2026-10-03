import { appFetch } from "../demo/client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import type { Interval, Issue, Prediction, Promise_, Relations, Segment, Signal, Word } from "../api";
import { usePlayhead } from "../store";
import { FindingCard } from "./FindingCard";
import { GROUP_LABEL, type UBin, type UFinding } from "./findings";
import { IconArrow, IconMic, IconText, IconWave } from "./Icons";
import { MethodAndData } from "./Prediction";
import { RelationsView } from "./Relations";
import { RetentionChart, StructureChart, TranscriptRiskChart, WatchTimeChart } from "./RetentionCharts";
import { Spinner, SkeletonBlock } from "./Spinner";
import { clock, Legend, TimeChart } from "./TimeChart";
import { TranscriptPanel } from "./TranscriptPanel";

type Window = { start_ms: number; end_ms: number; wpm?: number; pitch_hz?: number | null; pitch_std_hz?: number | null; voiced_fraction?: number };
type Decision = { interval?: Interval; start_ms?: number; end_ms?: number; question?: string; answer?: string; decision?: string; reason?: string; quote?: string;
  rewrite?: string; confidence?: number; status?: string; explanation?: string; suggested_rewrite?: string; preserve?: string[] | string; counter_explanation?: string };
export type DeepData = { duration_ms: number; voice: { status: string; windows: Window[]; summary?: Record<string, unknown> };
  audio: { status: string; rms?: { t_ms: number[]; dbfs: (number | null)[] }; silence?: Interval[]; summary?: Record<string, unknown>;
    loudness?: { integrated_lufs?: number; lra_lu?: number; true_peak_dbfs?: number; short_term_t_ms?: number[]; short_term_lufs?: number[] } };
  jev?: { status: string; reason?: string; decisions: Decision[] } };
export type TimelineData = { chapters: Signal[]; markers: Signal[]; structure_spans: Signal[]; promises: Promise_[] };

export function useDeepDive(id: string) {
  return useQuery({ queryKey: ["deepdive", id], retry: false, queryFn: async () => {
    const r = await appFetch("/api/v1/runs/" + id + "/deepdive");
    if (!r.ok) throw new Error("Voice and audio measurements aren't available for this run.");
    return r.json() as Promise<DeepData>;
  } });
}

const num = (v: unknown, d = 0) => typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : null;
type Series = { name: string; points: { t: number; v: number }[]; blue?: boolean };

/** Measured signal over time (black first series, blue second). Missing windows are hatched, never drawn as zero. */
export function SignalChart({ title, series, duration, unit, min, max, fmtV }: {
  title: string; series: Series[]; duration: number; unit: string; min?: number; max?: number; fmtV?: (v: number) => string;
}) {
  const vals = series.flatMap((s) => s.points.map((p) => p.v)).filter(Number.isFinite);
  const lo = min ?? Math.min(...vals);
  const hi = Math.max(lo + 1e-6, max ?? Math.max(...vals));
  const pad = min === undefined || max === undefined ? (hi - lo) * 0.08 : 0;
  const f = fmtV ?? ((v: number) => (Math.abs(hi - lo) < 3 ? v.toFixed(2) : Math.round(v).toString()));
  const first = series[0]?.points ?? [];
  const unknown: Interval[] = [];
  first.forEach((p, i) => { if (!Number.isFinite(p.v)) unknown.push({ start_ms: p.t, end_ms: first[i + 1]?.t ?? Math.min(duration, p.t + 10000) }); });
  const near = (pts: Series["points"], ms: number) => { let best = pts[0]; for (const p of pts) { if (p.t <= ms) best = p; else break; } return best; };
  return (
    <section className="panel">
      <div className="chart-head"><h3>{title}</h3></div>
      {!vals.length ? <p className="note">Not measured.</p> : <>
        <TimeChart duration={duration} height={200} yMin={min ?? lo - pad} yMax={max ?? hi + pad} yFmt={f} yUnit={unit} ariaLabel={title} unknown={unknown}
          render={(s) => series.map((se) => <path key={se.name} className={`ch-line ${se.blue ? "blue" : ""}`} d={se.points.map((p, i) => Number.isFinite(p.v)
            ? `${i === 0 || !Number.isFinite(se.points[i - 1].v) ? "M" : "L"}${s.x(p.t)},${s.y(p.v)}` : "").join(" ")} />)}
          tooltip={(ms) => <>{series.map((se) => { const p = near(se.points, ms); return <div key={se.name}>{se.name}: <b className="num">{p && Number.isFinite(p.v) ? `${f(p.v)} ${unit}` : "Not measured"}</b></div>; })}</>} />
        {series.length > 1 && <Legend items={series.map((s) => ({ label: s.name, kind: "line" as const, color: s.blue ? "var(--accent)" : undefined }))} />}
      </>}
    </section>
  );
}

function Stat({ v, k }: { v: ReactNode; k: string }) {
  return <div className="stat"><b className="num">{v ?? <span className="faint">Not measured</span>}</b><span>{k}</span></div>;
}

type Props = {
  runId: string; section: "overview" | "text" | "voice" | "audio"; data?: DeepData; dataLoading?: boolean; duration: number; pred?: Prediction;
  onPred: (p: Prediction) => void; segments: Segment[]; words: Word[]; relations?: Relations; tl?: TimelineData; issues: Issue[];
  findings: UFinding[]; bins: UBin[]; onTab: (t: "text" | "voice" | "audio") => void; onEvidence: (issueId: string) => void; onAll: () => void;
  textRun?: boolean;
};

export function DeepDive(p: Props) {
  if (p.section === "overview") return <Overview {...p} />;
  if (p.section === "text") return <TextTab {...p} />;
  if (p.section === "voice") return <VoiceTab {...p} />;
  return <AudioTab {...p} />;
}

function HeadCard({ icon, label, value, unit, line, onClick }: { icon: ReactNode; label: string; value: ReactNode; unit?: string; line: string; onClick: () => void }) {
  return <button className="head-card" onClick={onClick}>
    <span className="head-icon">{icon}</span>
    <span className="head-label">{label}</span>
    <span className="head-value num">{value}{unit && <small> {unit}</small>}</span>
    <span className="head-line">{line}</span>
    <span className="head-go">See details <IconArrow size={16} /></span>
  </button>;
}

function Overview({ runId, data, duration, pred, onPred, tl, relations, findings, bins, onTab, onEvidence, onAll, textRun }: Props) {
  const voice = data?.voice, audio = data?.audio;
  const textF = findings.filter((f) => f.source === "model");
  const top = findings.slice(0, 3);
  const wpm = num(voice?.summary?.overall_wpm);
  const lufs = num(audio?.loudness?.integrated_lufs, 1);
  const silence = num(audio?.summary?.silence_s, 0);
  const clips = num(audio?.summary?.clipping_windows);
  return (
    <div className="deepdive">
      <div className={`head-cards ${textRun ? "one" : ""}`}>
        <HeadCard icon={<IconText />} label="Text" value={findings.length} unit={findings.length === 1 ? "finding" : "findings"}
          line={textF[0] ? `First: ${textF[0].title.toLowerCase()} at ${clock(textF[0].start_ms)}` : findings[0] ? `First: ${findings[0].title.toLowerCase()}` : "Nothing flagged in the script"} onClick={() => onTab("text")} />
        {!textRun && <><HeadCard icon={<IconMic />} label="Voice" value={wpm ?? "—"} unit={wpm ? "words/min" : undefined}
          line={num(voice?.summary?.pitch_std_hz) ? `Pitch varies ±${num(voice?.summary?.pitch_std_hz)} Hz` : voice ? "Pitch not measured" : "Not measured"} onClick={() => onTab("voice")} />
        <HeadCard icon={<IconWave />} label="Audio" value={lufs ?? "—"} unit={lufs ? "LUFS" : undefined}
          line={audio ? `${silence ?? "0"} s silence · ${clips ?? "0"} clipped` : "Not measured"} onClick={() => onTab("audio")} /></>}
      </div>

      {pred ? <>
        <section className="panel big"><RetentionChart pred={pred} /></section>
        <section className="panel"><RetentionChart pred={pred} mode="drop" height={240} /></section>
      </> : <section className="panel"><p className="note">The retention estimate needs a newer analysis package.</p></section>}

      {bins.length > 0 && <section className="panel">
        <div className="chart-head"><h3>Why — transcript risk by 5 seconds</h3></div>
        <TranscriptRiskChart bins={bins} duration={duration} findings={findings} onBin={(b) => b.top && document.getElementById(`f-${b.top}`)?.scrollIntoView({ block: "center", behavior: "smooth" })} />
      </section>}

      <div className="grid-2">
        {pred && <section className="panel"><WatchTimeChart pred={pred} /></section>}
        <section className="panel"><StructureChart duration={duration} chapters={tl?.chapters ?? []} markers={tl?.markers ?? []} promises={tl?.promises ?? []}
          spans={tl?.structure_spans ?? []} fallback={relations?.rhythm.sections} /></section>
      </div>

      <div className="section-title"><h2>Look at these first</h2>
        {findings.length > 3 && <button className="quiet" onClick={onAll}>See all {findings.length} <IconArrow size={16} /></button>}</div>
      {top.length ? <div className="fcards">{top.map((f, i) => <FindingCard key={f.id} f={f} n={i + 1} runId={runId} onEvidence={onEvidence} />)}</div>
        : <p className="note">Nothing flagged in the inspected parts. Parts marked “not inspected” weren't checked.</p>}

      {pred && <MethodAndData runId={runId} pred={pred} onPred={onPred} />}
    </div>
  );
}

function TextTab({ runId, data, duration, segments, words, relations, tl, issues, findings, bins, onEvidence }: Props) {
  const focus = usePlayhead((s) => s.focus);
  const selection = usePlayhead((s) => s.selection);
  const [picked, setPicked] = useState<string | null>(null);
  const [group, setGroup] = useState("all");
  const [shown, setShown] = useState(6);
  const groups = Array.from(new Set(findings.map((f) => f.group)));
  const list = findings.filter((f) => group === "all" || f.group === group);
  const pickedF = findings.find((f) => f.id === picked);
  const words_ = segments.reduce((n, s) => n + s.text.split(/\s+/).filter(Boolean).length, 0);
  const density = Array.from({ length: Math.ceil(duration / 15000) }, (_, i) => {
    const a = i * 15000, b = Math.min(duration, a + 15000);
    const n = segments.reduce((sum, s) => sum + Math.max(0, Math.min(b, s.interval.end_ms) - Math.max(a, s.interval.start_ms)) / Math.max(1, s.interval.end_ms - s.interval.start_ms) * s.text.split(/\s+/).length, 0);
    return { t: a, v: (n * 60000) / Math.max(1, b - a) };
  });
  return (
    <div className="deepdive">
      <div className="stat-row">
        <Stat v={findings.length} k="findings" />
        <Stat v={words_.toLocaleString()} k="words" />
        <Stat v={relations?.summary.questions ?? null} k="questions asked" />
        <Stat v={relations ? `${Math.round(relations.summary.concrete_share * 100)}%` : null} k="sentences with an example" />
      </div>

      <section className="panel big">
        <div className="chart-head"><h3>Transcript risk</h3></div>
        <TranscriptRiskChart bins={bins} duration={duration} findings={findings} onBin={(b) => setPicked(b.top ?? null)} />
        {pickedF && <div className="picked"><FindingCard f={pickedF} runId={runId} onEvidence={onEvidence} selected /></div>}
      </section>

      <div className="section-title"><h2>Findings</h2>
        {groups.length > 1 && <div className="chips">
          <button className={`chip ${group === "all" ? "on" : ""}`} onClick={() => setGroup("all")}>All</button>
          {groups.map((g) => <button key={g} className={`chip ${group === g ? "on" : ""}`} onClick={() => setGroup(g)}>{GROUP_LABEL[g] ?? g}</button>)}
        </div>}
      </div>
      {list.length ? <div className="fcards">{list.slice(0, shown).map((f) => <FindingCard key={f.id} f={f} runId={runId} onEvidence={onEvidence} selected={f.id === picked} />)}</div>
        : <p className="note">Nothing flagged.</p>}
      {list.length > shown && <div className="center"><button onClick={() => setShown(shown + 10)}>Show {Math.min(10, list.length - shown)} more</button></div>}

      <div className="grid-2">
        <SignalChart title="Words per minute" series={[{ name: "Transcript density", points: density }]} duration={duration} unit="words/min" min={0} />
        <SignalChart title="New ideas" series={[{ name: "New terms", points: (relations?.cognitive_load.windows ?? []).map((w) => ({ t: w.start_ms, v: w.new_terms })), blue: true }]}
          duration={duration} unit="new terms" min={0} />
      </div>

      {relations && <details className="disclose"><summary>Questions and ideas</summary><RelationsView rel={relations} /></details>}
      <JevChecks runId={runId} data={data} selection={selection} focus={focus} duration={duration} />
      <details className="disclose"><summary>Full transcript</summary>
        <TranscriptPanel segments={segments} words={words} issues={issues} spans={tl?.structure_spans ?? []} markers={tl?.markers ?? []} promises={tl?.promises ?? []} />
      </details>
    </div>
  );
}

function JevChecks({ runId, data, selection, focus, duration }: { runId: string; data?: DeepData; selection: Interval | null; focus: (iv: Interval, id?: string | null) => void; duration: number }) {
  const [question, setQuestion] = useState("Does this passage need a rewrite to be clearer without losing information?");
  const [checked, setChecked] = useState<Decision[] | null>(null);
  const check = useMutation({
    mutationFn: async () => {
      const r = await appFetch("/api/v1/runs/" + runId + "/jev-review", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, selection }) });
      const body = await r.json();
      if (!r.ok) throw new Error(body.error?.message ?? body.detail ?? "The check failed");
      return body as { decisions: Decision[]; status?: string; reason?: string };
    },
    onSuccess: (r) => setChecked(r.decisions),
  });
  const decisions = checked ?? data?.jev?.decisions ?? [];
  return (
    <details className="disclose">
      <summary>Second opinion on a passage</summary>
      <div className="jev-form">
        <label className="field">Question<input value={question} onChange={(e) => setQuestion(e.target.value)} /></label>
        <span className="faint">{selection ? `${clock(selection.start_ms)}–${clock(selection.end_ms)}` : "Whole transcript"}</span>
        <button className="soft" disabled={check.isPending || !question.trim()} onClick={() => check.mutate()}>{check.isPending && <Spinner />}Ask</button>
      </div>
      {check.error && <p className="err">{(check.error as Error).message}</p>}
      <div className="fcards">{decisions.map((d, i) => {
        const iv = d.interval ?? { start_ms: d.start_ms ?? 0, end_ms: d.end_ms ?? d.start_ms ?? duration };
        return <article className="fcard low" key={i}>
          <header className="fcard-head"><div className="fcard-title"><h4>{d.decision ? d.decision.replace(/^\w/, (c) => c.toUpperCase()) : d.answer ?? "Review"}</h4>
            <div className="fcard-meta">Model opinion — needs your review</div></div>
            <button className="time" onClick={() => focus(iv, null)}>{clock(iv.start_ms)}–{clock(iv.end_ms)}</button></header>
          <dl className="fcard-body">
            {d.quote && <div><dt>What happens</dt><dd><blockquote>“{d.quote}”</blockquote></dd></div>}
            <div><dt>Why</dt><dd>{d.explanation ?? d.reason ?? "No reason given."}</dd></div>
            {(d.suggested_rewrite ?? d.rewrite) && <div><dt>Draft wording</dt><dd>{d.suggested_rewrite ?? d.rewrite}</dd></div>}
            {d.preserve && <div className="keep"><dt>Keep this</dt><dd>{Array.isArray(d.preserve) ? d.preserve.join("; ") : d.preserve}</dd></div>}
          </dl>
          {d.counter_explanation && <details className="fcard-ev"><summary>Alternative explanation</summary><div className="fcard-ev-body"><p>{d.counter_explanation}</p></div></details>}
        </article>;
      })}</div>
      {!decisions.length && <p className="note">No second-opinion checks yet.</p>}
    </details>
  );
}

function VoiceTab({ data, dataLoading, duration }: Props) {
  if (dataLoading) return <SkeletonBlock chart />;
  const voice = data?.voice;
  if (!voice) return <p className="note">Voice wasn't measured for this run.</p>;
  const ser = (k: keyof Window, name: string, blue?: boolean): Series[] => [{ name, blue, points: voice.windows.map((w) => ({ t: w.start_ms, v: typeof w[k] === "number" ? (w[k] as number) : NaN })) }];
  const sm = voice.summary ?? {};
  return (
    <div className="deepdive">
      <div className="stat-row">
        <Stat v={num(sm.overall_wpm)} k="words / min" />
        <Stat v={num(sm.median_pitch_hz) && `${num(sm.median_pitch_hz)} Hz`} k="typical pitch" />
        <Stat v={num(sm.pitch_std_hz) && `±${num(sm.pitch_std_hz)} Hz`} k="pitch variation" />
        <Stat v={num(sm.aligned_words)} k="words timed" />
      </div>
      <div className="grid-2">
        <SignalChart title="Speaking rate" series={ser("wpm", "Rate")} duration={duration} unit="words/min" min={0} />
        <SignalChart title="Pitch" series={ser("pitch_hz", "Pitch", true)} duration={duration} unit="Hz" />
        <SignalChart title="Pitch variation" series={ser("pitch_std_hz", "Variation")} duration={duration} unit="Hz" min={0} />
        <SignalChart title="Voiced share" series={ser("voiced_fraction", "Voiced", true)} duration={duration} unit="share" min={0} max={1} />
      </div>
    </div>
  );
}

function AudioTab({ data, dataLoading, duration }: Props) {
  const focus = usePlayhead((s) => s.focus);
  if (dataLoading) return <SkeletonBlock chart />;
  const audio = data?.audio;
  if (!audio) return <p className="note">Audio wasn't measured for this run.</p>;
  const L = audio.loudness ?? {};
  return (
    <div className="deepdive">
      <div className="stat-row">
        <Stat v={num(L.integrated_lufs, 1) && `${num(L.integrated_lufs, 1)} LUFS`} k="overall loudness" />
        <Stat v={num(L.true_peak_dbfs, 1) && `${num(L.true_peak_dbfs, 1)} dB`} k="loudest peak" />
        <Stat v={num(audio.summary?.silence_s, 0) && `${num(audio.summary?.silence_s, 0)} s`} k="silence" />
        <Stat v={num(audio.summary?.clipping_windows)} k="clipped moments" />
      </div>
      <SignalChart title="Level" series={[{ name: "Level", points: (audio.rms?.t_ms ?? []).map((t, i) => ({ t, v: audio.rms?.dbfs[i] ?? NaN })) }]} duration={duration} unit="dBFS" min={-80} max={0} />
      <SignalChart title="Loudness" series={[{ name: "Short-term loudness", blue: true, points: (L.short_term_t_ms ?? []).map((t, i) => ({ t, v: L.short_term_lufs?.[i] ?? NaN })) }]} duration={duration} unit="LUFS" />
      <section className="panel">
        <div className="chart-head"><h3>Silent gaps</h3></div>
        {audio.silence?.length ? <div className="chips">{audio.silence.map((s, i) => <button key={i} className="chip num" onClick={() => focus(s, null)}>{clock(s.start_ms)} · {((s.end_ms - s.start_ms) / 1000).toFixed(1)} s</button>)}</div>
          : <p className="note">No silent gaps found.</p>}
      </section>
    </div>
  );
}
