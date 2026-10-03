import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, fmt, type Prediction, type Scenario } from "../api";
import { AtThisMoment } from "../components/AtThisMoment";
import { RetentionChart as OldScenarioChart, RiskChart } from "../components/Charts";
import { ChatPanel } from "../components/Chat";
import { DeepDive, useDeepDive } from "../components/DeepDive";
import { Dock } from "../components/Dock";
import { Drawer } from "../components/Drawer";
import { FindingCard } from "../components/FindingCard";
import { allFindings, riskBins } from "../components/findings";
import { IconBack, IconChat, IconDownload, IconFolder, IconGrid, IconList, IconMic, IconText, IconWave } from "../components/Icons";
import { FindingDetail } from "../components/Issues";
import { OcrFramesView } from "../components/OcrFrames";
import { Outputs } from "../components/Outputs";
import { Player } from "../components/Player";
import { ShotsView } from "../components/Shots";
import { TranscriptPanel } from "../components/TranscriptPanel";
import { Skeleton, SkeletonBlock } from "../components/Spinner";
import { RetentionBreakdown } from "../components/RetentionBreakdown";
import { EstimateBadge } from "../components/TimeChart";
import { issueLabel, Timeline } from "../components/Timeline";
import { usePlayhead } from "../store";

function download(name: string, body: string, type: string) {
  const url = URL.createObjectURL(new Blob([body], { type }));
  Object.assign(document.createElement("a"), { href: url, download: name }).click();
  URL.revokeObjectURL(url);
}

type Panel = { kind: "finding"; id: string } | { kind: "all" } | { kind: "chat" } | null;
type Tab = "overview" | "retention" | "text" | "voice" | "audio" | "outputs";
const TABS: [Tab, string, typeof IconGrid][] = [["overview", "Overview", IconGrid], ["retention", "Retention", IconWave], ["text", "Text", IconText], ["voice", "Voice", IconMic], ["audio", "Audio", IconWave], ["outputs", "Outputs", IconFolder]];
const s2 = (ms: number) => fmt(ms).replace(/\.\d$/, "");

export default function Review() {
  const { runId = "" } = useParams();
  const nav = useNavigate();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId) });
  const tl = useQuery({ queryKey: ["timeline", runId], queryFn: () => api.timeline(runId) });
  const tr = useQuery({ queryKey: ["transcript", runId], queryFn: () => api.transcript(runId) });
  const issues = useQuery({ queryKey: ["issues", runId], queryFn: () => api.issues(runId) });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const predQ = useQuery({ queryKey: ["prediction", runId], queryFn: () => api.prediction(runId), retry: false });
  const relQ = useQuery({ queryKey: ["relations", runId], queryFn: () => api.relations(runId) });
  const deepQ = useDeepDive(runId);
  const [userPred, setUserPred] = useState<Prediction | null>(null);
  const [userScenario, setUserScenario] = useState<Scenario | null>(null);
  const [panel, setPanel] = useState<Panel>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [outTab, setOutTab] = useState<"files" | "shots" | "ocr" | "run">("files");
  const { focus, selectedIssue } = usePlayhead();
  const items = useMemo(() => issues.data?.items ?? [], [issues.data]);
  const segments = useMemo(() => tr.data?.segments ?? [], [tr.data]);
  const pred = userPred ?? predQ.data ?? undefined;
  const findings = useMemo(() => allFindings(pred, items, segments), [pred, items, segments]);
  const bins = useMemo(() => riskBins(pred, findings), [pred, findings]);
  const close = useCallback(() => setPanel(null), []);

  useEffect(() => {
    setUserPred(null); setUserScenario(null); setPanel(null); setTab("overview");
    usePlayhead.setState({ currentMs: 0, seekRequest: null, selectedIssue: null, selection: null });
  }, [runId]);

  // land on the top finding's moment (drawers stay closed)
  useEffect(() => {
    if (!findings.length || selectedIssue && items.some((i) => i.issue_id === selectedIssue)) return;
    const top = findings[0];
    focus({ start_ms: top.start_ms, end_ms: top.end_ms }, top.issue?.issue_id ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [findings.length]);

  if (run.isLoading) return <div className="shell review"><div className="rv-head"><Skeleton w={44} h={44} r={22} /><div style={{ flex: 1 }}><Skeleton w="40%" h={28} /><Skeleton w="25%" /></div></div>
    <div className="ws2"><div className="card"><Skeleton h={300} r={14} /></div><div className="card"><SkeletonBlock lines={6} /></div></div></div>;
  if (run.error || !run.data) return <div className="shell"><div className="empty"><h3>Run not found</h3><Link to="/"><button>Back to projects</button></Link></div></div>;
  const r = run.data;
  const duration = r.asset.duration_ms;
  const title = r.project?.title ?? r.asset.original_name;
  const scenario = userScenario ?? tl.data?.scenarios[0];
  const scenarioAck = !!userScenario || !!scenario?.assumptions.acknowledged;
  const promises = tl.data?.promises ?? [];
  const runs = projects.data?.items.find((p) => p.project_id === r.project?.project_id)?.runs ?? [];
  const visualPending = "visual" in r.missing_stages;
  const textRun = !r.proxy_artifact_id;
  const tabs = TABS.filter(([k]) => !textRun || (k !== "voice" && k !== "audio"));
  const payoff = promises.map((x) => (x.partial_interval ?? x.fulfilled_interval)?.start_ms).filter((v): v is number => v !== undefined).sort((a, b) => a - b)[0];
  const openFinding = (id: string) => {
    const i = items.find((x) => x.issue_id === id);
    if (i) focus(i.affected_interval, i.issue_id);
    setPanel({ kind: "finding", id });
  };
  const drawerIssue = panel?.kind === "finding" ? items.find((i) => i.issue_id === panel.id) : undefined;
  const exportFindings = () => download(`findings-${runId.slice(0, 8)}.csv`, ["title,group,severity,evidence,start,end,why,what_to_do",
    ...findings.map((f) => [f.title, f.groupLabel, f.severity, f.strength, fmt(f.start_ms), fmt(f.end_ms), f.mechanism, f.suggestion]
      .map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","))].join("\n"), "text/csv");

  return (
    <div className="shell review">
      <header className="rv-head">
        <Link to="/" className="icon-btn icon-lg" aria-label="Back to projects" title="Back to projects"><IconBack /></Link>
        <div className="rv-title">
          <h1>{title}</h1>
          <div className="rv-sub">
            <span>{(r.project?.category ?? "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())}</span><span className="dotsep" /><span className="num">{s2(duration)}</span><span className="dotsep" />
            <select aria-label="Analysis run" className="bare" value={runId} onChange={(e) => nav(`/runs/${e.target.value}`)}>
              {(runs.length ? runs : [{ run_id: runId, created_at: r.run.created_at, package_kind: r.package_kind, status: "" }]).map((x) => (
                <option key={x.run_id} value={x.run_id}>Run {x.run_id.slice(0, 6)} · {x.created_at.slice(0, 10)}</option>))}
            </select>
            {visualPending && <><span className="dotsep" /><span className="hatch-pill">Visuals not inspected</span></>}
          </div>
        </div>
        <div className="rv-actions">
          <button onClick={() => setPanel(panel?.kind === "chat" ? null : { kind: "chat" })} aria-pressed={panel?.kind === "chat"}><IconChat size={17} />Ask</button>
          <Link to={`/runs/${runId}/plan`}><button className="hero"><IconList size={17} />Open edit plan</button></Link>
        </div>
      </header>

      <div className="kpis">
        <div className="kpi"><b className="num">{pred ? `${pred.summary.apv_pct.central.toFixed(0)}%` : "—"}</b><span>Viewed <EstimateBadge /></span></div>
        <div className="kpi"><b className="num">{pred ? s2(pred.summary.avd_s.central * 1000) : "—"}</b><span>Average watch time</span></div>
        <div className="kpi"><b className="num">{issues.isLoading && predQ.isLoading ? "…" : findings.length}</b><span>Findings</span></div>
        <div className="kpi"><b className="num">{payoff !== undefined ? s2(payoff) : "—"}</b><span>Title payoff starts</span></div>
      </div>

      <div className="ws2">
        {textRun ? <div className="card transcript-first"><div className="kicker" style={{ marginBottom: 10 }}>Transcript</div>
          <TranscriptPanel segments={segments} words={tr.data?.words ?? []} issues={items} spans={tl.data?.structure_spans ?? []} markers={tl.data?.markers ?? []} promises={promises} /></div>
          : <div className="card video-card"><Player src={api.artifactUrl(runId, r.proxy_artifact_id!)} /></div>}
        <div className="card"><AtThisMoment segments={segments} chapters={tl.data?.chapters ?? []} findings={findings} pred={pred} rel={relQ.data}
          onOpenFinding={(f) => f.issue ? openFinding(f.issue.issue_id) : (setTab("text"), setTimeout(() => document.getElementById(`f-${f.id}`)?.scrollIntoView({ block: "center", behavior: "smooth" }), 60))}
          onAsk={() => setPanel({ kind: "chat" })} /></div>
      </div>

      <div className="card tl-card">
        {tl.isLoading ? <SkeletonBlock lines={4} /> : <Timeline duration={duration} chapters={tl.data?.chapters ?? []} findings={findings} risk={tl.data?.risk ?? []} bins={bins}
          scenario={scenario} scenarioAck={scenarioAck} shots={tl.data?.shots ?? []} segments={segments} coverage={tl.data?.coverage ?? []} pred={pred} />}
      </div>

      <div className="tabs-wrap">
        <div className="tabs" role="tablist" aria-label="Review sections">
          {tabs.map(([k, l, Ico]) => <button key={k} data-tour-tab={k} role="tab" className={tab === k ? "on" : ""} aria-selected={tab === k} onClick={() => setTab(k)}><Ico size={17} />{l}</button>)}
        </div>
        {textRun && <p className="note tab-note">Voice and audio: not available for a text upload.</p>}
        <div className="tab-body" key={tab}>
          {tab === "retention" && (predQ.isLoading ? <SkeletonBlock chart lines={3} /> : pred ? <RetentionBreakdown runId={runId} pred={pred} onPred={setUserPred} /> : <p className="note">Retention data is not available for this run.</p>)}
          {tab !== "outputs" && tab !== "retention" && (predQ.isLoading && tab === "overview" ? <SkeletonBlock chart lines={3} /> :
            <DeepDive runId={runId} section={tab} data={deepQ.data} dataLoading={deepQ.isLoading} duration={duration} pred={pred} onPred={setUserPred}
              segments={segments} words={tr.data?.words ?? []} relations={relQ.data} tl={tl.data} issues={items} findings={findings} bins={bins}
              onTab={setTab} onEvidence={openFinding} onAll={() => setPanel({ kind: "all" })} textRun={textRun} />)}
          {tab === "outputs" && <div className="deepdive">
            <div className="segctl" role="tablist" aria-label="Outputs view">
              {([["files", "Files"], ["shots", "Shots"], ["ocr", "On-screen text"], ["run", "Run details"]] as const).map(([k, l]) =>
                <button key={k} data-tour-output={k} role="tab" aria-selected={outTab === k} className={outTab === k ? "on" : ""} onClick={() => setOutTab(k)}>{l}</button>)}
            </div>
            {outTab === "files" && <Outputs runId={runId} />}
            {outTab === "shots" && <ShotsView runId={runId} issues={items} segments={segments} visualPending={visualPending} />}
            {outTab === "ocr" && <OcrFramesView runId={runId} />}
            {outTab === "run" && <div className="run-details">
              <div className="kv">
                <span className="faint">Not analysed</span><span>{Object.entries(r.missing_stages).map(([k, v]) => `${k} — ${v}`).join(" · ") || "Nothing missing"}</span>
                <span className="faint">Speech covered</span><span className="num">{Math.round(r.coverage.filter((c) => c.modality === "speech" && c.status === "observed").reduce((t, c) => t + c.interval.end_ms - c.interval.start_ms, 0) / duration * 100)}%</span>
                <span className="faint">Visuals</span><span>{visualPending ? "Not inspected" : "See Shots"}</span>
                <span className="faint">On-screen text</span><span>{r.run.stages.some((s) => s.name === "ocr" && s.status === "complete") ? "Read from sampled frames" : "Not inspected"}</span>
                <span className="faint">Run</span><span>{r.run.status} ({r.package_kind}) · <span className="num">{r.run.created_at.slice(0, 16).replace("T", " ")}</span></span>
                {Object.entries(r.run.provenance).filter(([k]) => ["code_revision", "precision", "scoring_version", "external_service_model"].includes(k))
                  .map(([k, v]) => [<span key={k} className="faint">{k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())}</span>, <span key={k + "v"} className="code">{typeof v === "string" ? v : JSON.stringify(v)}</span>])}
                <span className="faint">Models</span>
                <span className="code">{((r.run.provenance.models as { role: string; model_id: string; revision: string }[] | undefined) ?? []).map((m) => `${m.role}: ${m.model_id}@${m.revision.slice(0, 8)}`).join(" · ")}</span>
                <span className="faint">Stages</span><span>{r.run.stages.map((s) => `${s.name}: ${s.status}`).join(" · ")}</span>
              </div>
              <div className="actions"><button onClick={exportFindings}><IconDownload size={16} />Export findings (CSV)</button></div>
              <details className="disclose"><summary>Risk by track (older narrative scoring)</summary>
                {tl.data && <RiskChart bins={tl.data.risk} duration={duration} chapters={tl.data.chapters} />}</details>
              <details className="disclose"><summary>Findings-based scenario (older curve)</summary>
                <OldScenarioChart runId={runId} scenario={scenario} duration={duration} ack={!!userScenario} onScenario={setUserScenario} /></details>
            </div>}
          </div>}
        </div>
      </div>

      {panel?.kind === "finding" && <Drawer title={drawerIssue ? issueLabel(drawerIssue.type) : "Finding"} kicker="Evidence" onClose={close} wide>
        <FindingDetail runId={runId} issue={drawerIssue} segments={segments} risk={tl.data?.risk ?? []} />
      </Drawer>}
      {panel?.kind === "all" && <Drawer title={`All findings (${findings.length})`} kicker="Findings" onClose={close} wide>
        <div className="fcards">{findings.map((f, i) => <FindingCard key={f.id} f={f} n={i + 1} runId={runId} onEvidence={openFinding} />)}</div>
      </Drawer>}
      {panel?.kind === "chat" && <ChatPanel runId={runId} onClose={close} pred={pred} deep={deepQ.data} />}
      <Dock active="review" runId={runId} />
    </div>
  );
}
