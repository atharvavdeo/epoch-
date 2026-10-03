import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api, jobs, uploadAnalysis, type Job, type JobStage } from "../api";
import { Dock } from "../components/Dock";
import { IconBack, IconChart, IconCheck, IconClose, IconDownload, IconFolder, IconList, IconMic, IconPlay, IconText, IconUpload, IconWave } from "../components/Icons";
import { Spinner } from "../components/Spinner";

const prefs = () => { try { return JSON.parse(localStorage.getItem("epoch.prefs") ?? "{}"); } catch { return {}; } };
type Step = "goal" | "upload" | "processing";
type Kind = "video" | "audio" | "script" | "package";
const STEPS: [Step, string][] = [["goal", "Goal"], ["upload", "Upload"], ["processing", "Processing"]];
const kindOf = (name: string): Kind | null =>
  /\.(mp4|mov|mkv|webm)$/i.test(name) ? "video" : /\.(mp3|wav|m4a|aac|flac|ogg|opus)$/i.test(name) ? "audio"
    : /\.(srt|vtt|txt|md)$/i.test(name) ? "script" : /\.zip$/i.test(name) ? "package" : null;
const mb = (n: number) => `${(n / 1048576).toFixed(n > 1048576 * 10 ? 0 : 1)} MB`;
const mmss = (ms: number) => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;

function mediaDuration(f: File): Promise<number | null> {
  return new Promise((res) => {
    const el = document.createElement(f.type.startsWith("audio") ? "audio" : "video");
    const url = URL.createObjectURL(f);
    el.preload = "metadata";
    el.onloadedmetadata = () => { URL.revokeObjectURL(url); res(Number.isFinite(el.duration) ? el.duration * 1000 : null); };
    el.onerror = () => { URL.revokeObjectURL(url); res(null); };
    el.src = url;
  });
}

// ---- processing stages: backend stage names folded into eight creator-readable steps ----
type Group = { key: string; label: string; icon: ReactNode; match: RegExp; media?: boolean };
const GROUPS: Group[] = [
  { key: "check", label: "Checking media", icon: <IconPlay />, match: /probe|proxy|^audio$|audio_extract|video_scan|frames|media|check|upload|shots?|ocr/i, media: true },
  { key: "asr", label: "Transcribing speech", icon: <IconMic />, match: /asr|transcri|whisper|vad/i, media: true },
  { key: "align", label: "Aligning words", icon: <IconText />, match: /align/i, media: true },
  { key: "structure", label: "Reading structure", icon: <IconList />, match: /narrative|struct|relation|script|reason|jev/i },
  { key: "predict", label: "Predicting retention", icon: <IconChart />, match: /predict|score|retention/i },
  { key: "voice", label: "Voice & audio", icon: <IconWave />, match: /voice|loud|pitch/i, media: true },
  { key: "package", label: "Packaging", icon: <IconFolder />, match: /package|export|outputs?/i },
  { key: "import", label: "Importing", icon: <IconDownload />, match: /import|commit/i },
];
type GState = "done" | "partial" | "running" | "failed" | "skipped" | "waiting";
function groupStates(job: Job, groups: Group[]): Record<string, { state: GState; secs: number }> {
  const out: Record<string, { state: GState; secs: number }> = {};
  const stages: JobStage[] = job.stages ?? [];
  const terminalOk = job.status === "complete";
  let currentIdx = job.stage ? groups.findIndex((g) => g.match.test(job.stage!)) : -1;
  groups.forEach((g, i) => {
    const mine = stages.filter((s) => g.match.test(s.name));
    const secs = mine.reduce((t, s) => t + (s.elapsed_s ?? 0), 0);
    let state: GState = "waiting";
    if (mine.length) {
      if (mine.some((s) => /fail|error/i.test(s.status))) state = "failed";
      else if (mine.some((s) => /run|progress|active/i.test(s.status))) state = "running";
      else if (mine.some((s) => s.status === "partial")) state = "partial";
      else if (mine.every((s) => /skip|cached|not_needed|n\/a/i.test(s.status))) state = "skipped";
      else if (mine.every((s) => /complete|done|ok|skip|cached|success/i.test(s.status))) state = "done";
    } else if (currentIdx >= 0) state = i < currentIdx ? "done" : i === currentIdx ? (job.status === "failed" ? "failed" : "running") : "waiting";
    if (terminalOk && (state === "waiting" || state === "running")) state = mine.length || currentIdx >= 0 ? "done" : "skipped";
    out[g.key] = { state, secs };
  });
  if (currentIdx < 0) currentIdx = 0;
  return out;
}
const since = (a?: string | null, b?: string | null) => a ? Math.max(0, ((b ? new Date(b).getTime() : Date.now()) - new Date(a).getTime()) / 1000) : 0;

function Processing({ jobId, onRetry }: { jobId: string; onRetry: () => void }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["job", jobId], queryFn: () => jobs.get(jobId), retry: 1,
    refetchInterval: (query) => { const s = query.state.data?.status; return s === "complete" || s === "failed" || s === "cancelled" ? false : 2000; } });
  const cancel = useMutation({ mutationFn: () => jobs.cancel(jobId), onSuccess: () => qc.invalidateQueries({ queryKey: ["job", jobId] }) });
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 1000); return () => clearInterval(t); }, []);
  const job = q.data;
  useEffect(() => {
    if (job?.status === "complete" && job.run_id) {
      qc.invalidateQueries({ queryKey: ["projects"] });
      const t = setTimeout(() => nav(`/runs/${job.run_id}`), 1000);
      return () => clearTimeout(t);
    }
  }, [job?.status, job?.run_id, nav, qc]);
  if (q.isLoading) return <div className="proc"><Spinner /> Connecting…</div>;
  if (q.error || !job) return <div className="proc"><p className="err">{(q.error as Error)?.message ?? "Job not found."}</p><button onClick={onRetry}>Back to upload</button></div>;
  const media = job.kind !== "text";
  const groups = GROUPS.filter((g) => media || !g.media);
  const st = groupStates(job, groups);
  const progress = typeof job.progress === "number" ? job.progress : groups.filter((g) => ["done", "partial", "skipped"].includes(st[g.key].state)).length / groups.length;
  const live = job.status === "queued" || job.status === "running";
  const elapsed = since(job.started_at ?? job.created_at, live ? null : job.finished_at);
  return (
    <div className="proc">
      <div className="proc-head">
        <div><h2>{job.status === "complete" ? "Analysis ready" : job.status === "failed" ? "Analysis stopped" : job.status === "cancelled" ? "Cancelled" : job.kind === "text" ? "Analysing your script" : job.kind === "audio" ? "Analysing your recording" : "Analysing your video"}</h2>
          <p className="faint">{job.title ?? ""}{job.title ? " · " : ""}<span className="num">{mmss(elapsed * 1000)}</span> elapsed</p></div>
        <span className="proc-pct num">{Math.round(progress * 100)}%</span>
      </div>
      <div className="bar"><span style={{ width: `${Math.max(2, progress * 100)}%` }} className={live ? "live" : ""} /></div>
      {media && live && <p className="note">Speech transcription takes about 2–3× the media length on this computer.</p>}
      <ol className="stages">
        {groups.map((g) => {
          const s = st[g.key];
          return <li key={g.key} className={`stage ${s.state}`}>
            <span className="stage-icon">{g.icon}</span>
            <span className="stage-name">{g.label}</span>
            {s.secs > 0 && <span className="faint num">{mmss(s.secs * 1000)}</span>}
            <span className="stage-state">{s.state === "done" ? <IconCheck size={16} /> : s.state === "running" ? <Spinner /> : s.state === "failed" ? <IconClose size={16} />
              : s.state === "partial" ? <span className="faint">Partial</span> : s.state === "skipped" ? <span className="faint">Skipped</span> : <span className="dot" />}</span>
          </li>;
        })}
      </ol>
      {job.error && <p className="err">{job.error.message}</p>}
      {!!job.notes?.length && <ul className="caption">{job.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
      {!!job.log_tail?.length && <details className="adv"><summary>Details</summary><pre className="cmd log">{job.log_tail.join("\n")}</pre></details>}
      <div className="step-actions">
        {live && <button className="quiet" disabled={cancel.isPending} onClick={() => cancel.mutate()}>{cancel.isPending && <Spinner />}Cancel</button>}
        {(job.status === "failed" || job.status === "cancelled") && <button onClick={onRetry}>Try again</button>}
        {job.status === "complete" && job.run_id && <Link to={`/runs/${job.run_id}`}><button className="hero">Open review</button></Link>}
      </div>
      {cancel.error && <p className="err">{(cancel.error as Error).message}</p>}
    </div>
  );
}

export default function NewAnalysis() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const p0 = prefs();
  const jobParam = params.get("job");
  const [step, setStep] = useState<Step>(jobParam ? "processing" : params.get("project") ? "upload" : "goal");
  const [form, setForm] = useState({ title: "", category: p0.category ?? "education", language: p0.language ?? "en", audience: "" });
  const projectId = params.get("project");
  const existing = useQuery({ queryKey: ["project", projectId], queryFn: () => api.project(projectId!), enabled: !!projectId });
  useEffect(() => {
    if (existing.data) setForm({ title: existing.data.title, category: existing.data.category,
      language: existing.data.declared_language, audience: "" });
  }, [existing.data]);
  const [mode, setMode] = useState<"file" | "paste">("file");
  const [file, setFile] = useState<{ f: File; kind: Kind; duration_ms: number | null } | null>(null);
  const [text, setText] = useState("");
  const [over, setOver] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [pct, setPct] = useState<number | null>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const [jobId, setJobId] = useState<string | null>(jobParam);

  const toProcessing = (id: string) => { setJobId(id); setStep("processing"); setParams({ job: id }, { replace: true }); };
  const meta = () => ({ title: form.title.trim(), category: form.category, language: form.language, project_id: projectId, audience: form.audience.trim() || undefined });
  const start = useMutation({
    mutationFn: async () => {
      if (mode === "paste") return jobs.text({ ...meta(), text, source_name: "pasted script" });
      const up = uploadAnalysis(file!.f, meta(), setPct);
      abortRef.current = up.abort;
      setPct(0);
      try { return await up.promise; } finally { abortRef.current = null; }
    },
    onSuccess: (r) => { setPct(null); qc.invalidateQueries({ queryKey: ["projects"] }); toProcessing(r.job_id); },
    onError: () => setPct(null),
  });
  const importZip = useMutation({
    mutationFn: async (f: File) => {
      const { import_id } = await api.importZip(f);
      for (let i = 0; i < 600; i++) {
        const st = await api.importStatus(import_id);
        if (st.status === "committed") return st.committed_run_id!;
        if (st.status === "rejected") throw new Error(st.errors.map((e) => `${e.code}: ${e.message}`).join("; "));
        await new Promise((r) => setTimeout(r, 600));
      }
      throw new Error("Import still running; refresh later.");
    },
    onSuccess: (runId) => { qc.invalidateQueries(); nav(`/runs/${runId}`); },
  });

  const choose = async (f: File | undefined) => {
    if (!f) return;
    const kind = kindOf(f.name);
    if (!kind) { setMsg(`${f.name}: not a supported file. Use a video, an audio file, a script (.txt, .md, .srt, .vtt) or a .retention.zip.`); return; }
    setMsg(null);
    if (kind === "package") { importZip.mutate(f); return; }
    setFile({ f, kind, duration_ms: kind === "video" || kind === "audio" ? await mediaDuration(f) : null });
  };
  const idx = STEPS.findIndex(([k]) => k === step);
  const canStart = !!form.title.trim() && (mode === "paste" ? text.trim().split(/\s+/).length >= 20 : !!file) && !start.isPending;
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;

  return (
    <div className="shell onboarding">
      <div className="header"><Link to="/" className="icon-btn icon-lg" aria-label="Back to projects" title="Back to projects"><IconBack /></Link>
        <div className="title"><h1>New analysis</h1></div><span /></div>

      <ol className="stepper" aria-label="Progress">
        {STEPS.map(([k, label], i) => (
          <li key={k} className={`${k === step ? "on" : ""} ${i < idx ? "done" : ""}`}>
            <button disabled={k === "processing" ? !jobId : step === "processing" || (k === "upload" && !form.title.trim())}
              onClick={() => setStep(k)} aria-current={k === step ? "step" : undefined}>
              <span className="n">{i < idx ? <IconCheck size={13} /> : i + 1}</span>{label}</button></li>))}
      </ol>

      <div className="card step-card" key={step}>
        {step === "goal" && <>
          <h2>What's the video called?</h2>
          <label className="field">Exact title<input value={form.title} autoFocus onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. How MrBeast Solved YouTube"
            onKeyDown={(e) => { if (e.key === "Enter" && form.title.trim()) setStep("upload"); }} /></label>
          <div className="field-row">
            <label className="field">Category<select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              <option value="education">Education</option><option value="tech_review">Tech review</option><option value="other">Other</option></select></label>
            <label className="field">Language<select value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })}>
              <option value="en">English</option><option value="hi">Hindi</option><option value="mixed">Hinglish / mixed</option></select></label>
          </div>
          <label className="field">Audience <span className="faint">(optional)</span><input value={form.audience} placeholder="e.g. beginner YouTubers" onChange={(e) => setForm({ ...form, audience: e.target.value })} /></label>
          <div className="step-actions">
            <button className="hero" disabled={!form.title.trim()} title={!form.title.trim() ? "Enter the title first" : undefined} onClick={() => setStep("upload")}>Continue</button>
          </div>
        </>}

        {step === "upload" && <>
          <div className="upload-head"><h2>Add your video</h2>
            <div className="segctl" role="tablist" aria-label="Source">
              <button role="tab" aria-selected={mode === "file"} className={mode === "file" ? "on" : ""} onClick={() => setMode("file")}>Upload a file</button>
              <button role="tab" aria-selected={mode === "paste"} className={mode === "paste" ? "on" : ""} onClick={() => setMode("paste")}>Paste script</button>
            </div></div>
          {!form.title.trim() && <p className="err">Add the title in the Goal step first.</p>}
          {mode === "file" ? (!file ? (
            <label className={`dropzone ${over ? "over" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
              onDrop={(e) => { e.preventDefault(); setOver(false); choose(e.dataTransfer.files?.[0]); }}>
              <input type="file" hidden accept=".mp4,.mov,.mkv,.webm,.mp3,.wav,.m4a,.aac,.flac,.ogg,.opus,.srt,.vtt,.txt,.md,.zip" onChange={(e) => choose(e.target.files?.[0])} />
              <span className="dz-icon" aria-hidden><IconUpload size={30} /></span>
              <b>Drop a video, voice note or script</b>
              <span className="faint">or click to choose a file</span>
            </label>
          ) : (
            <div className="filesum">
              <span className="pill">{{ video: "Video", audio: "Audio", script: "Script", package: "Package" }[file.kind]}</span>
              <b className="filesum-name">{file.f.name}</b>
              <span className="faint num">{mb(file.f.size)}{file.duration_ms ? ` · ${mmss(file.duration_ms)}` : ""}</span>
              {!start.isPending && <button className="quiet" style={{ marginLeft: "auto" }} onClick={() => setFile(null)}>Change</button>}
            </div>
          )) : (
            <label className="field">Script or transcript
              <textarea rows={10} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the full script here…" />
              <span className="hint num">{words.toLocaleString()} words{words > 0 && words < 20 ? " · paste at least 20 words" : ""}</span></label>
          )}
          {pct !== null && <div className="upload-progress"><div className="bar"><span style={{ width: `${Math.round(pct * 100)}%` }} /></div>
            <span className="num faint">{pct < 1 ? `Uploading ${Math.round(pct * 100)}%` : "Upload complete — starting analysis…"}</span></div>}
          {start.error && <p className="err">{(start.error as Error).message}</p>}
          {msg && <p className="err">{msg}</p>}
          {file && (file.kind === "video" || file.kind === "audio") && !start.isPending && <p className="note">Speech transcription takes about 2–3× the media length on this computer{file.duration_ms ? ` (about ${Math.max(1, Math.round(file.duration_ms * 2.5 / 60000))} min here)` : ""}.</p>}
          <div className="step-actions">
            <button className="quiet" onClick={() => setStep("goal")}>Back</button>
            {start.isPending && abortRef.current && <button className="quiet" onClick={() => abortRef.current?.()}>Cancel upload</button>}
            <button className="hero" disabled={!canStart} onClick={() => start.mutate()}>{start.isPending && <Spinner />}Start analysis</button>
          </div>
          <div className="secondary-path">
            <span className="faint">Already have a finished analysis package?</span>
            <label className="link-like">{importZip.isPending ? <><Spinner /> Importing…</> : "Import a .retention.zip"}
              <input type="file" accept=".zip" hidden disabled={importZip.isPending} onChange={(e) => e.target.files?.[0] && importZip.mutate(e.target.files[0])} /></label>
          </div>
          {importZip.error && <p className="err">Import rejected: {(importZip.error as Error).message}. Nothing was changed.</p>}
        </>}

        {step === "processing" && (jobId ? <Processing jobId={jobId} onRetry={() => { setJobId(null); setParams({}, { replace: true }); setStep("upload"); }} />
          : <p className="note">No analysis running. Start one from the Upload step.</p>)}
      </div>
      <Dock active="new" />
    </div>
  );
}
