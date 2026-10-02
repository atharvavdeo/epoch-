import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api";
import { Dock } from "../components/Dock";

export default function Projects() {
  const qc = useQueryClient();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [form, setForm] = useState({ title: "", category: "education", declared_language: "en" });
  const [cmd, setCmd] = useState<{ command: string; note: string } | null>(null);

  const upload = useMutation({
    mutationFn: async (f: File) => {
      setImportMsg("Uploading and validating…");
      const { import_id } = await api.importZip(f);
      for (let i = 0; i < 600; i++) {  // the spinner always terminates in a clear state
        const st = await api.importStatus(import_id);
        if (st.status === "committed") return st;
        if (st.status === "rejected") throw new Error(st.errors.map((e) => `${e.code}: ${e.message}`).join("; "));
        await new Promise((r) => setTimeout(r, 500));
      }
      throw new Error("import is still running; refresh later");
    },
    onSuccess: () => { setImportMsg("Imported."); qc.invalidateQueries({ queryKey: ["projects"] }); },
    onError: (e: Error) => setImportMsg(`Rejected: ${e.message}`),
  });

  const create = useMutation({
    mutationFn: async () => { const p = await api.createProject(form); return api.analysisRequest(p.project_id); },
    onSuccess: (r) => { setCmd(r); qc.invalidateQueries({ queryKey: ["projects"] }); },
  });

  return (
    <div className="shell">
      <div className="header">
        <span />
        <div className="title"><h1>Retention review</h1><div className="sub">Local analysis · evidence you can check · runs offline</div></div>
        <span />
      </div>
      <div className="home">
        <div className="card">
          <h2>Projects</h2>
          {projects.isLoading && <p className="muted">Loading…</p>}
          {projects.error && <p className="err">API not reachable. Start it: .venvs/api/Scripts/python.exe -m uvicorn apps.api.main:app --port 8765</p>}
          <div className="projects" style={{ marginTop: 10 }}>
            {projects.data?.items.map((p) => (
              <div className="inset" key={p.project_id} style={{ padding: 16 }}>
                <h3>{p.title}</h3>
                <div className="muted">{p.category} · {p.declared_language} · <span className={`pill ${p.state === "partial" ? "amber" : "supported"}`}>{p.state}</span></div>
                <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                  {p.runs.map((r) => (
                    <Link key={r.run_id} to={`/runs/${r.run_id}`}>
                      {r.run_id === p.active_run_id ? "● " : "○ "}{r.created_at.slice(0, 16).replace("T", " ")} — {r.package_kind}
                    </Link>
                  ))}
                  {!p.runs.length && <span className="muted">No analysis imported yet.</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card">
            <h2>Import analysis</h2>
            <p className="muted">Choose a <span className="mono">*.retention.zip</span> package produced by the pipeline.</p>
            <input type="file" accept=".zip" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} />
            {importMsg && <p className={upload.isError ? "err" : "muted"}>{importMsg}</p>}
          </div>
          <div className="card">
            <h2>Prepare analysis</h2>
            <p className="muted">Uploading a video here does not start GPU analysis. This creates the project and shows the command to run.</p>
            <div style={{ display: "grid", gap: 8 }}>
              <input placeholder="Exact video title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                <option value="education">education</option><option value="tech_review">tech_review</option><option value="other">other</option>
              </select>
              <select value={form.declared_language} onChange={(e) => setForm({ ...form, declared_language: e.target.value })}>
                <option value="en">English</option><option value="hi">Hindi</option><option value="mixed">Hinglish / mixed</option>
              </select>
              <button className="amber" disabled={!form.title.trim()} onClick={() => create.mutate()}>Create project</button>
            </div>
            {cmd && <><p className="muted">{cmd.note}</p><pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{cmd.command}</pre></>}
          </div>
        </div>
      </div>
      <Dock active="projects" />
    </div>
  );
}
