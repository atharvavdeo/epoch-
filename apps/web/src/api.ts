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
export type Settings = { data_dir: string; cerebras: { configured: boolean; base_url: string; model: string | null };
  asr_threads: string; sent_to_cerebras: string; models: { role: string; model_id: string; revision: string; present: boolean }[] };

type Range3 = { central: number; lower: number; upper: number };
export type PredSecond = { t: number; retention: number; lower: number; upper: number; neutral: number; loss: number;
  excess_loss: number; contributions: Record<string, number>; protective: string[] };
export type DropMoment = { start_s: number; end_s: number; excess_loss: number; retention_before: number; retention_after: number;
  reasons: { feature: string; share: number; text: string }[]; quote: string | null; issue_ids: string[] };
export type Prediction = { prediction_id: string; model_version: string; label: string; calibrated: false;
  anchors: { retention_at_30s: number; retention_at_end: number }; per_second: PredSecond[];
  summary: { duration_s: number; avd_s: Range3; apv_pct: Range3; end_pct: Range3; neutral_avd_s: number; neutral_end_pct: number;
    excess_loss_by_feature: Record<string, number> };
  drop_moments: DropMoment[]; weights: Record<string, { weight: number; reason: string; rationale: string }>; notes: string[];
  feature_info: { sources: string[]; median_wpm?: number | null }; recomputed?: boolean };

export class ApiError extends Error {
  constructor(public code: string, message: string, public action?: string | null) { super(message); }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api/v1${path}`, init);
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
  prediction: (run: string) => call<Prediction>(`/runs/${run}/prediction`),
  repredict: (run: string, a: { retention_at_30s: number; retention_at_end: number; acknowledged: boolean }) =>
    call<Prediction>(`/runs/${run}/prediction`, json("POST", a)),
  artifactUrl: (run: string, art: string) => `/api/v1/runs/${run}/artifacts/${art}`,
};

export const fmt = (ms: number) => {
  const s = Math.max(0, ms) / 1000;
  return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;
};
