import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api } from "../api";
import { Dock } from "../components/Dock";
import { parseTranscriptFile, type ParsedTranscript } from "../transcriptParse";

const prefs = () => { try { return JSON.parse(localStorage.getItem("epoch.prefs") ?? "{}"); } catch { return {}; } };

export function PipelineStatus({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["pipeline", projectId], queryFn: () => api.pipeline(projectId), refetchInterval: 8000 });
  const imp = useMutation({
    mutationFn: async (path: string) => {
      const { import_id } = await api.importLocal(path);
      for (let i = 0; i < 600; i++) {
        const st = await api.importStatus(import_id);
        if (st.status === "committed") return st.committed_run_id!;
        if (st.status === "rejected") throw new Error(st.errors.map((e) => `${e.code}: ${e.message}`).join("; "));
        await new Promise((r) => setTimeout(r, 700));
      }
      throw new Error("import still running; refresh later");
    },
    onSuccess: (runId) => { qc.invalidateQueries(); nav(`/runs/${runId}`); },
  });
  const ws = q.data?.workspaces[0];
  const state = q.data?.state ?? "not_started";
  const steps = [
    { key: "ready_for_colab", label: "Ready for Colab", done: ["ready_for_colab", "package_ready", "imported"].includes(state) },
    { key: "package_ready", label: "Waiting for analysis package", done: ["package_ready", "imported"].includes(state) },
    { key: "imported", label: "Analysis imported", done: state === "imported" },
  ];
  return (
    <div>
      <div className="steps">{steps.map((s) => (
        <span key={s.key} className={`step ${s.done ? "done" : state === "local_running" && s.key === "ready_for_colab" ? "pending" : "off"}`}>
          <span className="dot" />{s.label}</span>))}</div>
      {state === "not_started" && <p className="muted">Nothing has run for this project yet. Run the command above on this computer.</p>}
      {state === "local_running" && ws && <p className="muted">Local analysis is in progress or stopped part-way:{" "}
        {Object.entries(ws.stages).filter(([k]) => ["probe", "proxy", "audio", "video_scan", "frames", "asr", "align", "visual_job"].includes(k))
          .map(([k, v]) => `${k} ${v === "complete" ? "✓" : v}`).join(" · ")}. Re-run the same command to resume; finished steps are reused.</p>}
      {ws?.colab_job && !ws.visual_attached && (
        <div className="inset" style={{ marginTop: 8 }}>
          <b>Colab step (manual).</b> Upload this file to Google Drive at <span className="mono">MyDrive/epoch/jobs/</span>, open
          {" "}<span className="mono">notebooks/epoch_visual_colab.ipynb</span> in Colab on an A100 and run the cells in order:
          <div className="mono" style={{ marginTop: 6, wordBreak: "break-all" }}>{ws.colab_job}</div>
          <div className="faint" style={{ fontSize: 13, marginTop: 6 }}>Then: <span className="mono">pipeline.cli attach-visual {ws.asset_sha256.slice(0, 8)} &lt;result.zip&gt;</span>
            {" "}and <span className="mono">pipeline.cli finish {ws.asset_sha256.slice(0, 8)}</span>. You can also review the local-only package
            below first: visual analysis will show as not inspected.</div>
        </div>)}
      {ws?.package && !ws.package_imported && (
        <div className="inset" style={{ marginTop: 8 }}>
          <b>Analysis package ready</b>{!ws.visual_attached && <span className="pill amber" style={{ marginLeft: 8 }}>visual analysis incomplete</span>}
          <div className="mono" style={{ marginTop: 6, wordBreak: "break-all", fontSize: 12 }}>{ws.package}</div>
          <div className="actions"><button className="hero" disabled={imp.isPending} onClick={() => imp.mutate(ws.package!)}>
            {imp.isPending ? "Validating and importing…" : "Import result ZIP"}</button></div>
          {imp.error && <p className="err">Import rejected: {(imp.error as Error).message}</p>}
        </div>)}
      {state === "imported" && <p className="muted">The latest package is imported. Open it from Projects or the Review dock.</p>}
    </div>
  );
}

type Step = "goal" | "sources" | "check" | "process";
type Kind = "video" | "audio" | "script" | "package";
const STEPS: [Step, string][] = [["goal", "Goal"], ["sources", "Sources"], ["check", "Check"], ["process", "Process"]];
const kindOf = (name: string): Kind | null =>
  /\.(mp4|mov|mkv)$/i.test(name) ? "video" : /\.(mp3|wav|m4a|aac|flac|ogg|opus)$/i.test(name) ? "audio"
    : /\.(srt|vtt|txt|md)$/i.test(name) ? "script" : /\.zip$/i.test(name) ? "package" : null;
const mb = (n: number) => `${(n / 1048576).toFixed(n > 1048576 * 10 ? 0 : 1)} MB`;
const mmss = (ms: number) => `${Math.floor(ms / 60000)}:${String(Math.round(ms / 1000) % 60).padStart(2, "0")}`;

/** Media duration from the browser (no upload): lets the Check step show the real expected processing time. */
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

export default function NewAnalysis() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const nav = useNavigate();
  const [params] = useSearchParams();
  const p0 = prefs();
  const [step, setStep] = useState<Step>(params.get("project") ? "sources" : "goal");
  const [form, setForm] = useState({ title: "", category: p0.category ?? "education", declared_language: p0.language ?? "en", audience: "" });
  const [projectId, setProjectId] = useState<string | null>(params.get("project"));
  const [file, setFile] = useState<{ f: File; kind: Kind; duration_ms: number | null } | null>(null);
  const [videoPath, setVideoPath] = useState("");
  const [parsed, setParsed] = useState<ParsedTranscript | null>(null);
  const [over, setOver] = useState(false);
  const [pkgMsg, setPkgMsg] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => api.createProject({ title: form.title.trim(), category: form.category, declared_language: form.declared_language,
      description: form.audience.trim() ? `Audience: ${form.audience.trim()}` : undefined }),
    onSuccess: (p) => { setProjectId(p.project_id); qc.invalidateQueries({ queryKey: ["projects"] }); setStep("sources"); },
  });
  const upload = useMutation({
    mutationFn: async (f: File) => {
      setPkgMsg("Uploading and validating…");
      const { import_id } = await api.importZip(f);
      for (let i = 0; i < 600; i++) {
        const st = await api.importStatus(import_id);
        if (st.status === "committed") return st.committed_run_id!;
        if (st.status === "rejected") throw new Error(st.errors.map((e) => `${e.code}: ${e.message}`).join("; "));
        await new Promise((r) => setTimeout(r, 600));
      }
      throw new Error("import still running; refresh later");
    },
    onSuccess: (runId) => { qc.invalidateQueries(); nav(`/runs/${runId}`); },
    onError: (e: Error) => setPkgMsg(`Rejected: ${e.message}. Nothing was imported; the previous state is unchanged.`),
  });

  const choose = async (f: File | undefined) => {
    if (!f) return;
    const kind = kindOf(f.name);
    if (!kind) { setPkgMsg(`${f.name}: not a supported file. Use MP4/MOV/MKV, an audio file, .srt/.vtt/.txt/.md, or a .retention.zip.`); return; }
    setPkgMsg(null);
    setFile({ f, kind, duration_ms: kind === "video" || kind === "audio" ? await mediaDuration(f) : null });
    if (kind === "script") setParsed(parseTranscriptFile(f.name, await f.text()));
    if (kind === "video" || kind === "audio") setVideoPath((v) => v || f.name);
  };

  const py = settings.data?.pipeline_command;
  const path = videoPath.trim().replace(/^"|"$/g, "");
  const cmd = !file || !path || !py ? null : file.kind === "audio"
    ? `${py} transcribe "${path}" --title "${form.title.trim()}" --language ${form.declared_language === "mixed" ? "mixed" : form.declared_language}${file.duration_ms && (file.duration_ms < 300_000 || file.duration_ms > 900_000) ? " --allow-out-of-scope" : ""}`
    : `${py} analyze "${path}" --title "${form.title.trim()}" --category ${form.category} --language ${form.declared_language} --project-id ${projectId}${file.duration_ms && (file.duration_ms < 300_000 || file.duration_ms > 900_000) ? " --allow-out-of-scope" : ""}`;
  const idx = STEPS.findIndex(([k]) => k === step);
  const canGo = (k: Step) => k === "goal" || (k === "sources" && !!projectId) || ((k === "check" || k === "process") && !!projectId && !!file);

  return (
    <div className="shell onboarding">
      <div className="header"><Link to="/"><button className="ghost back" aria-label="Back to projects" title="Back to projects">‹</button></Link>
        <div className="title"><h1>New analysis</h1><div className="sub">One step at a time. Analysis runs on this computer; nothing is uploaded except to the local site.</div></div><span /></div>

      <ol className="stepper" aria-label="Progress">
        {STEPS.map(([k, label], i) => (
          <li key={k} className={`${k === step ? "on" : ""} ${i < idx ? "done" : ""}`}>
            <button className="quiet" disabled={!canGo(k)} onClick={() => setStep(k)} aria-current={k === step ? "step" : undefined}
              title={!canGo(k) ? (k === "sources" ? "Create the project first" : "Choose a source first") : undefined}>
              <span className="n">{i < idx ? "✓" : i + 1}</span>{label}</button></li>))}
      </ol>

      <div className="card step-card">
        {step === "goal" && <>
          <h2>What does the video promise?</h2>
          <p className="muted">The exact title matters: a delayed payoff is judged against it.</p>
          <label className="field">Exact video title<input value={form.title} autoFocus onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. How MrBeast Solved YouTube" /></label>
          <label className="field">Intended audience <span className="faint">(optional)</span><input value={form.audience} placeholder="e.g. beginner YouTubers" onChange={(e) => setForm({ ...form, audience: e.target.value })} /></label>
          <div className="field-row">
            <label className="field">Category<select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              <option value="education">Education</option><option value="tech_review">Tech review</option><option value="other">Other</option></select></label>
            <label className="field">Primary language<select value={form.declared_language} onChange={(e) => setForm({ ...form, declared_language: e.target.value })}>
              <option value="en">English</option><option value="hi">Hindi</option><option value="mixed">Hinglish / mixed</option></select></label>
          </div>
          {create.error && <p className="err">{(create.error as Error).message}</p>}
          <div className="step-actions">
            <button className="quiet" onClick={() => { setStep("sources"); }} disabled={!projectId} title={!projectId ? "Create the project first" : undefined}>Skip</button>
            {projectId ? <button className="hero" onClick={() => setStep("sources")}>Continue</button>
              : <button className="hero" disabled={!form.title.trim() || create.isPending} title={!form.title.trim() ? "Enter the exact title first" : undefined}
                onClick={() => create.mutate()}>{create.isPending ? "Creating…" : "Continue"}</button>}
          </div>
          <p className="faint" style={{ fontSize: 13 }}>Already have a finished analysis package? <button className="link" onClick={() => document.getElementById("pkg-input")?.click()}>Import it directly</button>
            <input id="pkg-input" type="file" accept=".zip" hidden onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} /></p>
          {pkgMsg && <p className={upload.isError ? "err" : "muted"}>{pkgMsg}</p>}
        </>}

        {step === "sources" && <>
          <h2>What do you have?</h2>
          {!file ? (
            <label className={`dropzone ${over ? "over" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
              onDrop={(e) => { e.preventDefault(); setOver(false); choose(e.dataTransfer.files?.[0]); }}>
              <input type="file" hidden accept=".mp4,.mov,.mkv,.mp3,.wav,.m4a,.aac,.flac,.ogg,.opus,.srt,.vtt,.txt,.md,.zip" onChange={(e) => choose(e.target.files?.[0])} />
              <span className="dz-icon" aria-hidden>⤓</span>
              <b>Drop a file here, or click to choose</b>
              <span className="muted">Video (MP4, MOV, MKV) · audio (MP3, WAV, M4A…) · transcript or script (SRT, VTT, TXT, MD) · analysis package (.zip)</span>
              <span className="faint" style={{ fontSize: 13 }}>No subtitles? Drop the video or audio: speech is transcribed locally (faster-whisper large-v3).</span>
            </label>
          ) : (
            <div className="filesum">
              <span className="pill">{{ video: "Video", audio: "Audio", script: "Transcript", package: "Package" }[file.kind]}</span>
              <b>{file.f.name}</b>
              <span className="faint">{mb(file.f.size)}{file.duration_ms ? ` · ${mmss(file.duration_ms)}` : ""}</span>
              <button className="quiet" style={{ marginLeft: "auto" }} onClick={() => { setFile(null); setParsed(null); }}>Change</button>
            </div>
          )}
          {pkgMsg && <p className={upload.isError ? "err" : "muted"}>{pkgMsg}</p>}
          {file && (file.kind === "video" || file.kind === "audio") && <label className="field" style={{ marginTop: 16 }}>Full path of this file on this computer
            <input value={videoPath} onChange={(e) => setVideoPath(e.target.value)} placeholder={`C:\\Users\\you\\Videos\\${file.f.name}`} />
            <span className="faint" style={{ fontSize: 13 }}>Browsers never reveal a file's folder, so paste the full path (Shift + right-click the file → Copy as path).</span></label>}
          <div className="step-actions">
            <button className="quiet" onClick={() => setStep("goal")}>Back</button>
            {file?.kind === "package"
              ? <button className="hero" disabled={upload.isPending} onClick={() => upload.mutate(file.f)}>{upload.isPending ? "Validating…" : "Import result ZIP"}</button>
              : <button className="hero" disabled={!file || ((file.kind === "video" || file.kind === "audio") && !path.includes("\\") && !path.includes("/"))}
                  title={!file ? "Choose a file first" : "Paste the full path first"} onClick={() => setStep("check")}>Continue</button>}
          </div>
        </>}

        {step === "check" && file && <>
          <h2>Check before processing</h2>
          <div className="checklist">
            <div className="ck ok"><span>✓</span><div><b>Title</b><div className="muted">{form.title || "(set in Goal)"}</div></div></div>
            <div className="ck ok"><span>✓</span><div><b>Source</b><div className="muted">{file.f.name}{file.duration_ms ? ` · ${mmss(file.duration_ms)}` : ""}</div></div></div>
            {file.duration_ms && (file.duration_ms < 300_000 || file.duration_ms > 900_000) &&
              <div className="ck warn"><span>!</span><div><b>Length outside 5–15 min</b><div className="muted">It will run, labelled out of scope; the model was designed for 5–15 minute videos.</div></div></div>}
            {(file.kind === "video" || file.kind === "audio") && <>
              <div className="ck ok"><span>✓</span><div><b>Will run here</b><div className="muted">{file.kind === "video"
                ? "Media checks, audio levels, cuts and black/frozen frames, speech-to-text, word alignment; then narrative (Cerebras), the text retention model and the package."
                : "Speech-to-text and word alignment. You get SRT, VTT and text with timestamps in outputs/."}</div></div></div>
              <div className="ck info"><span>i</span><div><b>Expected time</b><div className="muted">Speech-to-text runs on the CPU at roughly 2–3× the media length
                {file.duration_ms ? ` (about ${Math.round(file.duration_ms * 2.5 / 60000)} min for this file)` : ""}. Finished steps are reused if you re-run.</div></div></div>
              {file.kind === "video" && <div className="ck info"><span>i</span><div><b>Not analysed</b><div className="muted">Visual analysis is on hold and on-screen text (OCR) is off. Those parts will show as “not inspected”, never as fine.</div></div></div>}
            </>}
            {file.kind === "script" && parsed && <div className={`ck ${parsed.timed ? "ok" : "warn"}`}><span>{parsed.timed ? "✓" : "!"}</span><div><b>Transcript</b>
              <div className="muted">{parsed.segments.length} lines · {parsed.words} words · {parsed.timed ? "timing from subtitle timestamps" : "timing estimated from word count"}
                {" "}· ≈ {Math.round(parsed.duration_ms / 60000)} min</div>
              {parsed.warnings.map((w) => <div key={w} className="faint">{w}</div>)}
              <div className="quote-orig" style={{ marginTop: 6, fontSize: 13 }}>{parsed.segments.slice(0, 2).map((s) => s.text).join(" ")}</div></div></div>}
            {file.kind === "script" && <div className="ck warn"><span>!</span><div><b>Script-only analysis is not built yet</b>
              <div className="muted">The transcript is checked here, but the backend that analyses a script without media does not exist yet. Use the video or audio route for a full result.</div></div></div>}
          </div>
          <div className="step-actions">
            <button className="quiet" onClick={() => setStep("sources")}>Back</button>
            <button className="hero" onClick={() => setStep("process")}>Continue</button>
          </div>
        </>}

        {step === "process" && file && <>
          <h2>Process</h2>
          {(file.kind === "video" || file.kind === "audio") && cmd && <>
            <p className="muted">The browser can't start programs, so run this once in a terminal in the project folder. Progress appears below on its own.</p>
            <pre className="mono inset cmd">{cmd}</pre>
            <div className="step-actions" style={{ justifyContent: "flex-start" }}><button onClick={() => navigator.clipboard?.writeText(cmd)}>Copy command</button></div>
            {file.kind === "video" && projectId && <div style={{ marginTop: 20 }}><PipelineStatus projectId={projectId} /></div>}
            {file.kind === "audio" && <p className="faint">When it finishes, the transcript files are in <span className="mono">outputs/&lt;name&gt;/</span> (transcript.srt, transcript.vtt, 07_transcript.txt).</p>}
          </>}
          {file.kind === "script" && parsed && projectId && <ScriptHandoff projectId={projectId} parsed={parsed} />}
        </>}
      </div>
      <Dock active="new" />
    </div>
  );
}

function ScriptHandoff({ projectId, parsed }: { projectId: string; parsed: ParsedTranscript }) {
  const save = useMutation({ mutationFn: () => api.saveScript(projectId, parsed) });
  return (
    <div style={{ marginTop: 12 }}>
      <div className="section-title"><h3>3 · Run the text analysis</h3></div>
      {!save.data ? <button disabled={save.isPending} onClick={() => save.mutate()}>Save transcript to the project</button>
        : <><pre className="mono inset" style={{ whiteSpace: "pre-wrap", wordBreak: "break-all", fontSize: 12 }}>{save.data.command}</pre>
          <div className="actions"><button onClick={() => navigator.clipboard?.writeText(save.data!.command)}>Copy command</button></div>
          <PipelineStatus projectId={projectId} /></>}
      {save.error && <p className="err">{(save.error as Error).message}</p>}
    </div>
  );
}
