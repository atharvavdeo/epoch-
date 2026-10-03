import { useQueries, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, fmt, jobs, type Job, type Prediction, type Project } from "../api";
import { introSeen, Welcome } from "../components/Welcome";
import { Dock } from "../components/Dock";
import { IconCheck, IconFolder, IconLink, IconPlus, IconSearch, IconSliders, IconStar } from "../components/Icons";
import { Skeleton } from "../components/Spinner";

type Status = "ready" | "processing" | "import";
const STATUS_LABEL: Record<Status, string> = { ready: "Ready to review", processing: "Processing", import: "Needs import" };
const statusOf = (p: Project): Status => p.active_run_id ? "ready" : p.state === "package_ready" ? "import" : "processing";
const clock = (ms: number) => fmt(ms).replace(/\.\d$/, "");
const LANG: Record<string, string> = { en: "English", hi: "Hindi", mixed: "Hinglish" };
const hash = (s: string) => { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) | 0; return Math.abs(h); };
const when = (d?: string) => {
  if (!d) return "No activity yet";
  const days = Math.floor((Date.now() - new Date(d).getTime()) / 86_400_000);
  return days <= 0 ? "Today" : days === 1 ? "Yesterday" : days < 30 ? `${days} days ago` : new Date(d).toLocaleDateString();
};
const loadPins = (): string[] => { try { const v = JSON.parse(localStorage.getItem("epoch.pins") ?? "[]"); return Array.isArray(v) ? v : []; } catch { return []; } };

function ProjectCard({ p, pred, pinned, onPin }: { p: Project; pred?: Prediction | null; pinned: boolean; onPin: () => void }) {
  const nav = useNavigate();
  const run = p.active_run_id;
  const lazy = { enabled: !!run, staleTime: 600_000 };
  const shots = useQuery({ queryKey: ["shots", run], queryFn: () => api.shots(run!), ...lazy });
  const runQ = useQuery({ queryKey: ["run", run], queryFn: () => api.run(run!), ...lazy });
  const tl = useQuery({ queryKey: ["timeline", run], queryFn: () => api.timeline(run!), ...lazy });
  const issues = useQuery({ queryKey: ["issues", run], queryFn: () => api.issues(run!), ...lazy });
  const [copied, setCopied] = useState(false);
  // a running browser upload for this project (the jobs endpoint may not exist on older servers: then this stays empty)
  const jobQ = useQuery({ queryKey: ["jobs", p.project_id], queryFn: () => jobs.list(p.project_id), retry: false, staleTime: 3000,
    refetchInterval: (q) => (q.state.data ?? []).some((j: Job) => j.status === "queued" || j.status === "running") ? 4000 : false });
  const job = (jobQ.data ?? []).find((j) => j.status === "queued" || j.status === "running");
  const thumb = shots.data?.items.find((s) => s.thumb)?.thumb;
  const status = statusOf(p);
  const h = hash(p.project_id);
  const code = (run ?? p.project_id).replace(/-/g, "").slice(0, 6).toUpperCase();
  const duration = runQ.data?.asset.duration_ms ?? tl.data?.duration_ms;
  const chapters = tl.data?.chapters.length;
  const items = issues.data?.items ?? [];
  const open = items.filter((i) => i.review_status === "open").length;
  const viewed = pred?.summary.apv_pct.central;
  const to = job ? `/new?job=${job.job_id}` : run ? `/runs/${run}` : `/new?project=${p.project_id}`;
  const jobLabel = job ? `Processing${job.stage ? ` · ${job.stage.replace(/_/g, " ")}` : ""}${typeof job.progress === "number" ? ` · ${Math.round(job.progress * 100)}%` : ""}` : null;
  const copy = (e: React.MouseEvent) => {
    e.stopPropagation();
    const url = `${location.origin}${to}`;
    navigator.clipboard?.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1400); }, () => undefined);
  };
  return (
    <article className="pj-card" role="link" tabIndex={0} aria-label={`${p.title}: ${STATUS_LABEL[status]}`}
      onClick={() => nav(to)} onKeyDown={(e) => { if (e.key === "Enter") nav(to); }}>
      <div className="pj-image" style={thumb && run ? undefined : { background: `linear-gradient(135deg, hsl(${h % 360} 42% 78%), hsl(${(h >> 3) % 360} 48% 56%))` }}>
        {thumb && run && <img src={api.artifactUrl(run, thumb.artifact_id)} alt="" loading="lazy" />}
        <span className="pj-shade" />
        <span className={`pj-status ${job ? "processing live" : status}`}>{jobLabel ?? STATUS_LABEL[status]}</span>
        <span className="pj-tools">
          <button className="round" aria-label={copied ? "Link copied" : "Copy link"} title={copied ? "Copied" : "Copy link"} onClick={copy}>{copied ? <IconCheck size={16} /> : <IconLink size={16} />}</button>
          <button className={`round ${pinned ? "on" : ""}`} aria-label={pinned ? "Unpin" : "Pin"} aria-pressed={pinned} title={pinned ? "Unpin" : "Pin to top"}
            onClick={(e) => { e.stopPropagation(); onPin(); }}><IconStar size={16} filled={pinned} /></button>
        </span>
        <span className="pj-caption"><span className="pj-code">{code}</span><span className="pj-title">{p.title}</span></span>
      </div>
      <div className="pj-body">
        <div className="pj-label">Category</div>
        <div className="pj-value">{p.category.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())} <span className="faint">· {LANG[p.declared_language] ?? p.declared_language}</span></div>
        <div className="pj-meter-head"><span className="pj-label">Estimated % viewed · uncalibrated</span>{pred === null && run ? <span className="faint">Not analysed</span> : null}</div>
        <div className="pj-meter">
          <span className={`pj-track ${viewed === undefined ? "none" : ""}`}>{viewed !== undefined && <span className="pj-fill" style={{ width: `${Math.min(100, viewed)}%` }} />}</span>
          <b className="num">{viewed !== undefined ? `${viewed.toFixed(0)}%` : "—"}</b>
        </div>
        <div className="pj-cols">
          <div><div className="pj-label">Duration</div><div className="pj-value num">{duration ? clock(duration) : "—"}</div>
            <div className="pj-small">{chapters !== undefined ? `${chapters} section${chapters === 1 ? "" : "s"}` : run ? <Skeleton w={60} h={10} /> : "Not analysed"}</div></div>
          <div><div className="pj-label">Findings</div><div className="pj-value num">{run ? (issues.isLoading ? "…" : `${open} open`) : "—"}</div>
            <div className="pj-small">{run ? `${items.length} total` : "Not analysed"}</div></div>
        </div>
        <div className="pj-foot">Last activity · {when(p.updated_at)}</div>
      </div>
    </article>
  );
}

export default function Projects() {
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const items = projects.data?.items ?? [];
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"new" | "old" | "viewed">("new");
  const [filters, setFilters] = useState<Status[]>([]);
  const [showFilters, setShowFilters] = useState(false);
  const [readyOnly, setReadyOnly] = useState(false);
  const [pins, setPins] = useState<string[]>(loadPins);
  const [intro, setIntro] = useState(() => !introSeen());
  const preds = useQueries({ queries: items.map((p) => ({
    queryKey: ["prediction", p.active_run_id], enabled: !!p.active_run_id, retry: false, staleTime: 600_000,
    queryFn: () => api.prediction(p.active_run_id!),
  })) });
  const predOf = (i: number): Prediction | null | undefined => preds[i]?.data ?? (preds[i]?.isError ? null : undefined);
  const togglePin = (id: string) => setPins((all) => { const n = all.includes(id) ? all.filter((x) => x !== id) : [id, ...all]; try { localStorage.setItem("epoch.pins", JSON.stringify(n)); } catch { /* blocked */ } return n; });
  const rows = items.map((p, i) => ({ p, pred: predOf(i) }))
    .filter(({ p }) => p.title.toLowerCase().includes(q.trim().toLowerCase()))
    .filter(({ p }) => (!readyOnly || statusOf(p) === "ready") && (!filters.length || filters.includes(statusOf(p))))
    .sort((a, b) => (pins.includes(b.p.project_id) ? 1 : 0) - (pins.includes(a.p.project_id) ? 1 : 0)
      || (sort === "viewed" ? (b.pred?.summary.apv_pct.central ?? -1) - (a.pred?.summary.apv_pct.central ?? -1)
        : sort === "old" ? (a.p.updated_at ?? "").localeCompare(b.p.updated_at ?? "") : (b.p.updated_at ?? "").localeCompare(a.p.updated_at ?? "")));
  return (
    <div className="page-projects">
      <header className="topbar-row">
        <div className="tb-title"><IconFolder /><h1>Projects</h1></div>
        <div className="tb-tools">
          <label className="search"><IconSearch size={16} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search projects…" aria-label="Search projects" /></label>
          <select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} aria-label="Sort">
            <option value="new">Newest first</option><option value="old">Oldest first</option><option value="viewed">Highest estimated % viewed</option>
          </select>
          <div className="filters-wrap">
            <button className={showFilters || filters.length ? "on" : ""} aria-expanded={showFilters} onClick={() => setShowFilters(!showFilters)}><IconSliders size={16} />Filters{filters.length ? ` · ${filters.length}` : ""}</button>
            {showFilters && <div className="popover" role="group" aria-label="Filter by status">
              {(Object.keys(STATUS_LABEL) as Status[]).map((s) => <label key={s} className="check"><input type="checkbox" checked={filters.includes(s)}
                onChange={(e) => setFilters(e.target.checked ? [...filters, s] : filters.filter((x) => x !== s))} />{STATUS_LABEL[s]}</label>)}
              {filters.length > 0 && <button className="quiet" onClick={() => setFilters([])}>Clear</button>}
            </div>}
          </div>
          <Link to="/new"><button className="hero"><IconPlus size={16} />New analysis</button></Link>
        </div>
      </header>
      <div className="shell">
        <div className="count-row">
          <span className="faint">{projects.isLoading ? "Loading…" : `${rows.length} project${rows.length === 1 ? "" : "s"}`}</span>
          <button className={`chip ${readyOnly ? "on" : ""}`} aria-pressed={readyOnly} onClick={() => setReadyOnly(!readyOnly)}><IconCheck size={14} />Ready</button>
        </div>
        {projects.error && <div className="empty"><h3>Can't reach the local service</h3><p className="faint">Start the API, then refresh.</p>
          <pre className="cmd">.venvs/api/Scripts/python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8765</pre></div>}
        {projects.isLoading && <div className="pj-grid">{[0, 1, 2].map((k) => <div key={k} className="pj-card skel-card"><Skeleton h={160} r={0} /><div className="pj-body"><Skeleton w="50%" /><Skeleton w="80%" /><Skeleton h={6} /><Skeleton w="60%" /></div></div>)}</div>}
        {!projects.isLoading && !projects.error && !items.length && <div className="empty">
          <h3>No projects yet</h3><Link to="/new"><button className="hero"><IconPlus size={16} />New analysis</button></Link></div>}
        {!!items.length && !rows.length && <div className="empty"><h3>No projects match</h3></div>}
        <div className="pj-grid">{rows.map(({ p, pred }) => <ProjectCard key={p.project_id} p={p} pred={pred} pinned={pins.includes(p.project_id)} onPin={() => togglePin(p.project_id)} />)}</div>
      </div>
      <Dock active="projects" />
      {intro && <Welcome onClose={() => setIntro(false)} />}
    </div>
  );
}
