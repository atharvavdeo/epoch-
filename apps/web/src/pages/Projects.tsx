import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, type Project } from "../api";
import { Dock } from "../components/Dock";

const STATE_LABEL: Record<string, string> = {
  not_started: "Waiting for local analysis", local_running: "Local analysis in progress", ready_for_colab: "Ready for Colab",
  package_ready: "Analysis package ready to import", imported: "Ready to review",
};

function ProjectCard({ p }: { p: Project }) {
  const pipe = useQuery({ queryKey: ["pipeline", p.project_id], queryFn: () => api.pipeline(p.project_id), refetchInterval: 15000 });
  const run = p.active_run_id;
  const shots = useQuery({ queryKey: ["shots", run], queryFn: () => api.shots(run!), enabled: !!run, staleTime: 600_000 });
  const thumb = shots.data?.items.find((s) => s.thumb)?.thumb;
  const active = p.runs.find((r) => r.run_id === run);
  const state = pipe.data?.state ?? (run ? "imported" : "not_started");
  const ws = pipe.data?.workspaces[0];
  const visualIncomplete = !!active && active.package_kind !== "analysis";
  const label = state === "imported" && visualIncomplete ? "Ready to review · visual analysis incomplete"
    : state === "package_ready" && run ? "New analysis package ready to import" : STATE_LABEL[state];
  return (
    <div className="pcard">
      <div className="pthumb">{thumb && run ? <img src={api.artifactUrl(run, thumb.artifact_id)} alt="" /> : <span className="faint">no preview yet</span>}</div>
      <div className="pbody">
        <h3>{p.title}</h3>
        <div className="faint" style={{ fontSize: 13 }}>{p.category} · {p.declared_language} · {ws?.kind ?? "video"} source
          {p.runs.length ? ` · run ${p.runs.length}` : ""}{p.updated_at ? ` · last activity ${p.updated_at.slice(0, 16).replace("T", " ")}` : ""}</div>
        <div style={{ marginTop: 8 }}><span className={`pill ${state === "imported" && !visualIncomplete ? "supported" : "amber"}`}>{label}</span></div>
        <div className="actions">
          {run && <Link to={`/runs/${run}`}><button className="amber">Open review</button></Link>}
          {state !== "imported" && <Link to={`/new?project=${p.project_id}&start=video`}><button>{state === "package_ready" ? "Import package" : "Resume"}</button></Link>}
          {run && <Link to={`/runs/${run}/plan`}><button className="ghost">Edit plan</button></Link>}
        </div>
      </div>
    </div>
  );
}

export default function Projects() {
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const items = projects.data?.items ?? [];
  return (
    <div className="shell">
      <div className="header"><span />
        <div className="title"><h1>Projects</h1><div className="sub">Local analysis · evidence you can check · runs offline</div></div>
        <div className="right"><Link to="/new"><button className="hero">+ New analysis</button></Link></div>
      </div>
      {projects.isLoading && <p className="muted">Loading…</p>}
      {projects.error && <div className="banner">The local API is not reachable. Start it with:
        <div className="mono">.venvs/api/Scripts/python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8765</div></div>}
      {!projects.isLoading && !items.length && !projects.error && (
        <div className="card" style={{ textAlign: "center", padding: 40 }}>
          <h2>Start with one video</h2>
          <p className="muted">Tell us the title it promises, run the local analysis, and land in Review.</p>
          <Link to="/new"><button className="hero">+ New analysis</button></Link>
        </div>)}
      <div className="projects">{items.map((p) => <ProjectCard key={p.project_id} p={p} />)}</div>
      <Dock active="projects" />
    </div>
  );
}
