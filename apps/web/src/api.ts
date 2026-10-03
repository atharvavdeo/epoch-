import { appFetch, DEMO, demoResource } from "./demo/client";
// Typed client for the local API (/api/v1). Shapes mirror contracts/entities.py.

export type Interval = { start_ms: number; end_ms: number };
export type Bound = { lower: number; upper: number; central: number | null };

export type Suggestion = {
  suggestion_id: string; issue_ids: string[]; operation: "cut" | "move" | "rewrite" | "insert_visual" | "adjust_audio";
  source_interval: Interval | null; destination_ms: number | null; proposed_text: string | null; rationale: string;
  prerequisites: string[]; requires_reanalysis: boolean;
};
export type Issue = {
  issue_id: string; type: string; affected_interval: Interval; modality_tags: string[]; risk_track: string;
  severity: "low" | "medium" | "high"; evidence_status: "supported" | "provisional"; evidence_ids: string[];
  explanation: string; counter_explanation: string; suggested_edit_ids: string[]; review_status: string;
  review_reason: string | null; cause_group_id: string; comparison_intervals: Interval[] | null; suggestions: Suggestion[];
};
export type Segment = { segment_id: string; interval: Interval; text: string; language: string; precision: string; word_ids: string[] };
export type Word = { word_id: string; segment_id: string; text: string; start_ms: number | null; end_ms: number | null;
  alignment_status: string };
export type Observation = { observation_id: string; interval: Interval; statement: string; kind?: string; status: string;
  sampled_frame_ids: string[]; evidence_ids: string[] };
export type Shot = { shot_id: string; interval: Interval; start_boundary_source: string; end_boundary_source: string;
  metrics: Record<string, number | null>; thumb: { artifact_id: string; at_ms: number; inside_shot: boolean } | null;
  observations: Observation[] };
export type OcrTrack = { track_id: string; interval: Interval; text: string; confidence: number;
  artifact_id: string | null; at_ms: number; quads: number[][][] };
export type TrackValue = { risk: number | null; coverage: number; lower: number; upper: number };
export type RiskBin = { interval: Interval; track_values: Record<string, TrackValue>; combined_lower: number;
  combined_upper: number; display_value: number | null; evidence_coverage: number; contributing_issue_ids: string[] };
export type ScenarioBin = { start_ms: number; end_ms: number; baseline_start: number; baseline_end: number;
  retention_start: Bound; retention_end: Bound; risk: Bound; conditional_drop: Bound | null; absolute_drop: Bound | null };
export type Scenario = { scenario_id: string; mode: string; formula_version: string; coverage_status: "complete" | "partial";
  labels: string[]; assumptions: { retention_at_30s: number; retention_at_end: number; kappa: number; acknowledged: boolean };
  bins: ScenarioBin[]; summary: { duration_ms: number; assumed_avd_seconds: Bound; assumed_apv_pct: Bound;
    assumed_end_pct: Bound | null; top_regions: { interval: Interval; max_risk: number; issue_ids: string[] }[] } };
export type Signal = { signal_id: string; feature_id: string; interval: Interval; name: string; value: unknown; unit?: string };
export type Coverage = { modality: string; interval: Interval; status: string; reason: string | null; sampling_profile: string };
export type Promise_ = { promise_id: string; title_quote: string; obligation: string; status: string;
  partial_interval: Interval | null; fulfilled_interval: Interval | null };
export type PipelineState = { project_id: string; state: "not_started" | "local_running" | "ready_for_colab" | "package_ready" | "imported";
  workspaces: { asset_sha256: string; original_name: string | null; kind: string; state: string; stages: Record<string, string>;
    visual_attached: boolean; colab_job: string | null; package: string | null; package_imported: boolean; outputs_dir: string | null }[] };
export type Project = { project_id: string; title: string; category: string; declared_language: string; state: string;
  description?: string | null; updated_at?: string; created_at?: string;
  active_run_id: string | null; runs: { run_id: string; status: string; package_kind: string; created_at: string }[] };

type Side = { duration_ms: number; assumed_avd_seconds: Bound; assumed_apv_pct: Bound; assumed_end_pct: Bound | null; coverage_status: string };
export type Hypothetical = { status: string; reason?: string; label: string; cuts: Interval[]; removed_ms: number;
  removed_by_cut_issue_ids: string[]; assumed_resolved_issue_ids: string[]; before: Side; after: Side; not_modelled: string; note: string };
export type EvalRun = { run_id: string; project_title: string; category: string; language: string; created_at: string; package_kind: string;
  duration_ms: number; missing: Record<string, string>; coverage: Record<string, number>; stage_seconds: Record<string, number>;
  issues: { total: number; by_type: Record<string, { total: number; accepted: number; dismissed: number; open: number }>;
    accepted: number; dismissed: number; open: number; supported: number; provisional: number } };
export type Evaluation = { runs: EvalRun[]; unvalidated: string[] };
export type Settings = { data_dir: string; pipeline_command: string; cerebras: { configured: boolean; base_url: string; model: string | null };
  asr_threads: string; sent_to_cerebras: string; models: { role: string; model_id: string; revision: string; present: boolean }[] };

type Range3 = { central: number; lower: number; upper: number };
export type PredSecond = { end_s?: number; duration_s?: number; hazard_per_s?: number; baseline_hazard_per_s?: number; conditional_loss?: number; transcript_risk?: number;
  cumulative_watch_s?: number; neutral_cumulative_watch_s?: number; t: number; retention: number; lower: number; upper: number; neutral: number; loss: number;
  excess_loss: number; contributions: Record<string, number>; protective: string[] };
export type DropMoment = { headline?: string; finding_ids?: string[]; start_s: number; end_s: number; excess_loss: number; retention_before: number; retention_after: number;
  reasons: { feature: string; share: number; text: string }[]; quote: string | null; issue_ids: string[] };
/** One reviewable rule candidate from the text model. Everything beyond the id and interval is optional:
 *  older packages carry these under `analysis.findings` with fewer fields, newer ones at the top level. */
export type ModelFinding = { finding_id: string; rule_id: string; cause_group?: string; group_label?: string; title?: string;
  start_ms: number; end_ms: number; status?: string; severity?: string; evidence_strength?: string; quote?: string;
  earlier_quote?: string | null; earlier_start_ms?: number | null; measurements?: Record<string, unknown>; mechanism?: string;
  counter_explanation?: string; suggestion?: string; preserve?: string | string[]; needs_reanalysis?: boolean; requires_reanalysis?: boolean;
  priority_score?: number; priority_rank?: number };
export type PredRiskBin = { start_s?: number; end_s?: number; start_ms?: number; end_ms?: number; risk?: number | null; score?: number;
  groups?: Record<string, number>; top_finding_id?: string | null; finding_ids?: string[] };
export type Baseline = { kind?: string; shape_k?: number; end_drop_multiplier?: number; end_drop_fraction?: number;
  anchors?: Record<string, number>; description?: string };
export type WatchTime = { avd_s?: number; neutral_avd_s?: number; duration_s?: number; apv_pct?: number; delta_vs_neutral_s?: number };
export type Prediction = { prediction_id: string; model_version: string; label: string; calibrated: false;
  anchors: { retention_at_30s: number; retention_at_end: number }; per_second: PredSecond[];
  summary: { duration_s: number; avd_s: Range3; apv_pct: Range3; end_pct: Range3; neutral_avd_s: number; neutral_end_pct: number;
    excess_loss_by_feature: Record<string, number>; watch_time?: WatchTime };
  drop_moments: DropMoment[]; weights: Record<string, { weight: number; reason: string; rationale: string }>; notes: string[];
  feature_info: { sources: string[]; median_wpm?: number | null }; recomputed?: boolean;
  findings?: ModelFinding[]; risk_bins?: PredRiskBin[]; baseline?: Baseline; risk_weights?: Record<string, unknown>;
  analysis?: { findings?: ModelFinding[]; risk_bins?: PredRiskBin[]; risk_label?: string } };
export type RepredictBody = { retention_at_30s: number; retention_at_end: number; acknowledged: boolean;
  shape_k?: number; end_drop_multiplier?: number; end_drop_fraction?: number };

export class ApiError extends Error {
  constructor(public code: string, message: string, public action?: string | null) { super(message); }
}

export type SentenceRef = { start_ms: number; end_ms: number; text: string; punctuated: boolean };
export type QA = { question: SentenceRef; answer: SentenceRef | null; shared_words: string[]; gap_ms: number | null;
  kind: "immediate" | "short" | "open_loop" | "framing" | "no_callback"; rhetorical_form: boolean };
export type Relations = { method: string; sentences: number; unpunctuated_ms: number; questions: QA[];
  concreteness: { start_ms: number; end_ms: number; score: number }[];
  abstract_stretches: { start_ms: number; end_ms: number; sentences: number; abstract_terms: number; quote: string }[];
  term_dependencies: { term: string; used_at: SentenceRef; explained_at: SentenceRef; gap_ms: number }[];
  cognitive_load: { long_sentences: (SentenceRef & { words: number })[]; median_new_terms_per_min: number;
    windows: { start_ms: number; end_ms: number; new_terms: number; mean_sentence_words: number; sentences: number; load: string }[] };
  rhythm: { windows: { start_ms: number; end_ms: number; sentences: number; variation: number | null }[];
    flat: { start_ms: number; end_ms: number }[]; sections: { label: string; start_ms: number; end_ms: number; duration_s: number }[] };
  summary: { questions: number; answered_immediately: number; open_loops: number; no_callback: number; concrete_share: number } };
export type ChatMsg = { role: "user" | "assistant"; content: string };
export type ChatAnswer = { answer: string; quotes: { text: string; verified: boolean; start_ms: number | null }[];
  edit_warnings: string[]; sources: { start_ms: number; end_ms: number; score: number; matched: string[] }[]; citations: { start_ms: number; end_ms: number; why: string }[]; dropped_citations: number;
  model: string; grounding: string };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await appFetch(`/api/v1${path}`, init);
  if (!r.ok) {
    let body: { error?: { code: string; message: string; recommended_action?: string } } = {};
    try { body = await r.json(); } catch { /* non-JSON error */ }
    throw new ApiError(body.error?.code ?? `http_${r.status}`, body.error?.message ?? r.statusText, body.error?.recommended_action);
  }
  return r.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export const api = {
  projects: () => call<{ items: Project[] }>("/projects"),
  project: (id: string) => call<Project>(`/projects/${id}`),
  createProject: (b: { title: string; category: string; declared_language: string; description?: string }) => call<Project>("/projects", json("POST", b)),
  pipeline: (id: string) => call<PipelineState>(`/projects/${id}/pipeline`),
  importLocal: (path: string) => call<{ import_id: string }>("/imports/local", json("POST", { path })),
  saveScript: (id: string, p: { source_name: string; raw: string }) => call<{ path: string; command: string }>(`/projects/${id}/script`, json("POST", { source_name: p.source_name, text: p.raw })),
  analysisRequest: (id: string) => call<{ command: string; note: string }>(`/projects/${id}/analysis-request`),
  importZip: (f: File) => { const fd = new FormData(); fd.append("file", f); return call<{ import_id: string }>("/imports", { method: "POST", body: fd }); },
  importStatus: (id: string) => call<{ status: string; committed_run_id: string | null; errors: { code: string; message: string }[] }>(`/imports/${id}`),
  run: (id: string) => call<{ run: { run_id: string; status: string; model_profile: string; created_at: string;
    provenance: Record<string, unknown>; stages: { name: string; status: string; fingerprint: string | null }[] };
    asset: { duration_ms: number; original_name: string }; package_kind: string; missing_stages: Record<string, string>;
    project: { project_id: string; title: string; category: string; declared_language: string } | null;
    proxy_artifact_id: string | null; coverage: Coverage[] }>(`/runs/${id}`),
  transcript: (id: string) => call<{ segments: Segment[]; words: Word[] }>(`/runs/${id}/transcript`),
  shots: (id: string) => call<{ items: Shot[] }>(`/runs/${id}/shots`),
  ocr: (id: string) => call<{ items: OcrTrack[] }>(`/runs/${id}/ocr`),
  timeline: (id: string) => call<{ risk: RiskBin[]; scenarios: Scenario[]; coverage: Coverage[]; chapters: Signal[];
    markers: Signal[]; structure_spans: Signal[]; promises: Promise_[]; shots: { shot_id: string; interval: Interval; metrics: Record<string, number | null> }[];
    duration_ms: number }>(`/runs/${id}/timeline`),
  issues: (id: string) => call<{ items: Issue[] }>(`/runs/${id}/issues`),
  evidence: (run: string, ev: string) => call<{ evidence: { kind: string; interval: Interval; quote: string | null; precision: string };
    ref: Record<string, unknown> | null; frames: { frame_id: string; artifact_id: string; at_ms: number }[] }>(`/runs/${run}/evidence/${ev}`),
  review: (run: string, issue: string, status: string, reason?: string) =>
    call(`/runs/${run}/issues/${issue}/review`, json("PATCH", { status, reason })),
  scenario: (run: string, a: { retention_at_30s: number; retention_at_end: number; kappa: number; acknowledged: boolean }) =>
    call<Scenario>(`/runs/${run}/scenarios`, json("POST", a)),
  hypothetical: (run: string, a: { retention_at_30s: number; retention_at_end: number; kappa: number; acknowledged: boolean;
    assumed_resolved_issue_ids: string[] }) => call<Hypothetical>(`/runs/${run}/hypothetical`, json("POST", a)),
  evaluation: () => call<Evaluation>("/evaluation"),
  settings: () => call<Settings>("/settings"),
  relations: (run: string) => call<Relations>(`/runs/${run}/relations`),
  chat: (run: string, b: { message: string; history: ChatMsg[]; selection: Interval | null }) =>
    call<ChatAnswer>(`/runs/${run}/chat`, json("POST", b)),
  transcriptUrl: (run: string, f: "srt" | "vtt" | "txt") => DEMO ? demoResource(run, "txt") : `/api/v1/runs/${run}/transcript.${f}`,
  prediction: (run: string) => call<Prediction>(`/runs/${run}/prediction`),
  repredict: (run: string, a: RepredictBody) =>
    call<Prediction>(`/runs/${run}/prediction`, json("POST", a)),
  artifactUrl: (run: string, art: string) => DEMO ? demoResource(run, art) : `/api/v1/runs/${run}/artifacts/${art}`,
  outputs: (run: string) => call<{ items: { artifact_id: string; name: string; kind: string; bytes: number; stage: string; sha256: string }[] }>(`/runs/${run}/outputs`),
  outputUrl: (run: string, art: string) => DEMO ? demoResource(run, art) : `/api/v1/runs/${run}/outputs/${art}`,
  outputsZipUrl: (run: string) => DEMO ? demoResource(run, "zip") : `/api/v1/runs/${run}/outputs.zip`,
};

// ---- browser upload + background analysis jobs ----
export type JobStage = { name: string; status: string; elapsed_s?: number | null };
export type Job = { job_id: string; project_id: string; kind: "video" | "audio" | "text"; title?: string;
  status: "queued" | "running" | "complete" | "failed" | "cancelled"; stage?: string | null; stages?: JobStage[]; progress?: number | null;
  log_tail?: string[]; run_id?: string | null; error?: { code: string; message: string } | null; created_at?: string; started_at?: string | null;
  finished_at?: string | null; notes?: string[] };
export type NewAnalysis = { title: string; category: string; language: string; project_id?: string | null; audience?: string };
export const UPLOAD_DOWN = "Upload service not running — restart the API.";
const missing = (status: number) => status === 404 || status === 405 || status === 501;

/** Multipart upload through XMLHttpRequest so the page can show real upload progress. */
export function uploadAnalysis(file: File, meta: NewAnalysis, onProgress: (f: number) => void) {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<{ job_id: string; project_id: string; kind: string; status: string }>((resolve, reject) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("title", meta.title); fd.append("category", meta.category); fd.append("language", meta.language);
    if (meta.project_id) fd.append("project_id", meta.project_id);
    if (meta.audience) fd.append("audience", meta.audience);
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    xhr.onload = () => {
      let body: { error?: { code?: string; message?: string }; detail?: unknown } & Record<string, unknown> = {};
      try { body = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(body as never);
      if (missing(xhr.status)) return reject(new ApiError("upload_unavailable", UPLOAD_DOWN));
      reject(new ApiError(body.error?.code ?? `http_${xhr.status}`, body.error?.message ?? (typeof body.detail === "string" ? body.detail : xhr.statusText || "Upload failed")));
    };
    xhr.onerror = () => reject(new ApiError("network", "Couldn't reach the local service. Is the API running?"));
    xhr.onabort = () => reject(new ApiError("aborted", "Upload cancelled."));
    xhr.open("POST", "/api/v1/analyses");
    xhr.send(fd);
  });
  return { promise, abort: () => xhr.abort() };
}

async function jobCall<T>(path: string, init?: RequestInit): Promise<T> {
  try { return await call<T>(path, init); } catch (e) {
    if (e instanceof ApiError && /^http_(404|405|501)$/.test(e.code) && !/job/i.test(e.message)) throw new ApiError("upload_unavailable", UPLOAD_DOWN);
    throw e;
  }
}
export const jobs = {
  text: (b: NewAnalysis & { text: string; source_name?: string }) => jobCall<{ job_id: string; project_id: string; kind: string; status: string }>("/analyses/text", json("POST", b)),
  get: (id: string) => jobCall<Job>(`/jobs/${id}`),
  list: (projectId: string) => jobCall<{ items: Job[] } | Job[]>(`/jobs?project_id=${encodeURIComponent(projectId)}`)
    .then((r) => (Array.isArray(r) ? r : r.items ?? [])),
  cancel: (id: string) => jobCall<Job>(`/jobs/${id}/cancel`, { method: "POST" }),
};

export const fmt = (ms: number) => {
  const s = Math.max(0, ms) / 1000;
  return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;
};
