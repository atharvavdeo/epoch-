import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api } from "../api";
import { Dock } from "../components/Dock";
import { parseTranscriptFile, type ParsedTranscript } from "../transcriptParse";

type Start = "video" | "script" | "package";

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
          <div className="actions"><button className="amber" disabled={imp.isPending} onClick={() => imp.mutate(ws.package!)}>
            {imp.isPending ? "Validating and importing…" : "Import and open review"}</button></div>
          {imp.error && <p className="err">Import rejected: {(imp.error as Error).message}</p>}
        </div>)}
      {state === "imported" && <p className="muted">The latest package is imported. Open it from Projects or the Review dock.</p>}
    </div>
  );
}

export default function NewAnalysis() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [start, setStart] = useState<Start | null>((params.get("start") as Start) || null);
  const p0 = prefs();
  const [form, setForm] = useState({ title: "", category: p0.category ?? "education", declared_language: p0.language ?? "en", audience: "" });
  const [videoPath, setVideoPath] = useState("");
  const [parsed, setParsed] = useState<ParsedTranscript | null>(null);
  const [projectId, setProjectId] = useState<string | null>(params.get("project"));
  const [pkgMsg, setPkgMsg] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => api.createProject({ title: form.title.trim(), category: form.category, declared_language: form.declared_language,
      description: form.audience.trim() ? `Audience: ${form.audience.trim()}` : undefined }),
    onSuccess: (p) => { setProjectId(p.project_id); qc.invalidateQueries({ queryKey: ["projects"] }); },
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

  const py = ".venvs/media/Scripts/python.exe -m pipeline.cli";
  const cmd = projectId && videoPath.trim()
    ? `${py} analyze "${videoPath.trim().replace(/^"|"$/g, "")}" --title "${form.title.trim()}" --category ${form.category} --language ${form.declared_language} --project-id ${projectId}`
    : null;

  return (
    <div className="shell">
      <div className="header"><Link to="/"><button className="back" aria-label="Back to projects">‹</button></Link>
        <div className="title"><h1>New analysis</h1><div className="sub">The website prepares the work; analysis runs on this computer and on Colab</div></div><span /></div>

      <div className="choices">
        {([["video", "I have a video", "Best route: measured cuts, audio and transcript, plus visual analysis on Colab."],
          ["script", "I have a transcript or script", "Text-only review of the narrative. Timing is estimated unless the file has timestamps."],
          ["package", "I have an analysis package", "Import a *.retention.zip produced by the pipeline."]] as const).map(([k, t, d]) => (
          <button key={k} className={`choice ${start === k ? "on" : ""}`} onClick={() => setStart(k)}>
            <b>{t}</b><span>{d}</span></button>))}
      </div>

      {start === "package" && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="section-title"><h3>Import an analysis package</h3></div>
          <input type="file" accept=".zip" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} />
          {pkgMsg && <p className={upload.isError ? "err" : "muted"}>{pkgMsg}</p>}
          <p className="faint" style={{ fontSize: 13 }}>The package is fully validated before anything is stored. You land in Review on success.</p>
        </div>)}

      {(start === "video" || start === "script") && (
        <div className="home" style={{ marginTop: 16 }}>
          <div className="card">
            <div className="section-title"><h3>1 · What does the video promise?</h3></div>
            <div style={{ display: "grid", gap: 10 }}>
              <label>Exact video title <span className="faint">(required: "delayed payoff" is judged against it)</span>
                <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} style={{ width: "100%", marginTop: 4 }} /></label>
              <label>Intended audience <span className="faint">(optional)</span>
                <input value={form.audience} placeholder="e.g. beginner YouTubers" onChange={(e) => setForm({ ...form, audience: e.target.value })}
                  style={{ width: "100%", marginTop: 4 }} /></label>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <label>Category<br /><select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                  <option value="education">education</option><option value="tech_review">tech review</option><option value="other">other</option></select></label>
                <label>Primary language<br /><select value={form.declared_language} onChange={(e) => setForm({ ...form, declared_language: e.target.value })}>
                  <option value="en">English</option><option value="hi">Hindi</option><option value="mixed">Hinglish / mixed</option></select></label>
              </div>
              {!projectId ? <div className="actions"><button className="hero" disabled={!form.title.trim() || create.isPending} onClick={() => create.mutate()}>
                Create project</button></div>
                : <p className="muted">Project created. <Link to="/">See it in Projects</Link>.</p>}
              {create.error && <p className="err">{(create.error as Error).message}</p>}
            </div>
          </div>

          <div className="card">
            {start === "video" ? (<>
              <div className="section-title"><h3>2 · Where is the video?</h3></div>
              <label>Path to the video file on this computer
                <input value={videoPath} placeholder={'C:\\Users\\you\\Videos\\my-video.mp4'} onChange={(e) => setVideoPath(e.target.value)}
                  style={{ width: "100%", marginTop: 4 }} disabled={!projectId} /></label>
              <p className="faint" style={{ fontSize: 13 }}>The browser cannot read files on your disk, and visual analysis needs Colab, so the
                website never starts analysis by itself. It gives you the exact command and then tracks progress below.</p>
              {cmd && <><div className="section-title" style={{ marginTop: 12 }}><h3>3 · Run on this computer</h3></div>
                <pre className="mono inset" style={{ whiteSpace: "pre-wrap", wordBreak: "break-all", fontSize: 12 }}>{cmd}</pre>
                <div className="actions"><button onClick={() => navigator.clipboard?.writeText(cmd)}>Copy command</button></div></>}
              {projectId && <><div className="section-title" style={{ marginTop: 16 }}><h3>4 · Progress</h3></div><PipelineStatus projectId={projectId} /></>}
            </>) : (<>
              <div className="section-title"><h3>2 · Attach the transcript</h3></div>
              <p className="faint" style={{ fontSize: 13 }}>Paste text or choose .txt, .md, .srt or .vtt. Subtitle files keep their timestamps;
                plain text gets a timeline explicitly estimated from word count.</p>
              <input type="file" accept=".txt,.md,.srt,.vtt" onChange={async (e) => {
                const f = e.target.files?.[0]; if (f) setParsed(parseTranscriptFile(f.name, await f.text()));
              }} />
              <textarea placeholder="…or paste the script here" rows={6} style={{ width: "100%", marginTop: 8 }}
                onChange={(e) => setParsed(e.target.value.trim() ? parseTranscriptFile("pasted.txt", e.target.value) : null)} />
              {parsed && <div className="inset" style={{ marginTop: 10, fontSize: 14 }}>
                <b>Check:</b> {parsed.segments.length} lines · {parsed.words} words · timing{" "}
                {parsed.timed ? <span className="pill supported">from subtitle timestamps</span> : <span className="pill amber">estimated from text</span>}
                {" "}· length ≈ {Math.round(parsed.duration_ms / 60000)} min{parsed.warnings.map((w) => <div key={w} className="faint">{w}</div>)}
                <div style={{ marginTop: 6 }}>{parsed.segments.slice(0, 3).map((s, i) => <div key={i} className="faint" style={{ fontSize: 13 }}>{s.text}</div>)}</div>
              </div>}
              {parsed && projectId && <ScriptHandoff projectId={projectId} parsed={parsed} />}
            </>)}
          </div>
        </div>)}
      <Dock active="new" />
    </div>
  );
}

function ScriptHandoff({ projectId, parsed }: { projectId: string; parsed: ParsedTranscript }) {
  const save = useMutation({ mutationFn: () => api.saveScript(projectId, parsed) });
  return (
    <div style={{ marginTop: 12 }}>
      <div className="section-title"><h3>3 · Run the text analysis</h3></div>
      {!save.data ? <button className="amber" disabled={save.isPending} onClick={() => save.mutate()}>Save transcript to the project</button>
        : <><pre className="mono inset" style={{ whiteSpace: "pre-wrap", wordBreak: "break-all", fontSize: 12 }}>{save.data.command}</pre>
          <div className="actions"><button onClick={() => navigator.clipboard?.writeText(save.data!.command)}>Copy command</button></div>
          <PipelineStatus projectId={projectId} /></>}
      {save.error && <p className="err">{(save.error as Error).message}</p>}
    </div>
  );
}
