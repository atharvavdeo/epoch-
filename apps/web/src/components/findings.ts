// Normalises every source of "why might viewers leave here" into one shape the UI can explain the same way:
// title → what happens → why it may lose viewers → what to do → keep this → evidence & alternative explanation.
// Sources, in order of preference: prediction.findings (new) → prediction.analysis.findings (older packages) → narrative issues.
import type { Interval, Issue, ModelFinding, Prediction, PredRiskBin, Segment } from "../api";
import { issueLabel } from "./Timeline";

export type Sev = "high" | "medium" | "low";
export type UFinding = {
  id: string; source: "model" | "issue"; issue?: Issue;
  title: string; group: string; groupLabel: string;
  start_ms: number; end_ms: number; severity: Sev; strength: string;
  quote: string; earlierQuote?: string; earlierStartMs?: number;
  mechanism: string; suggestion: string; preserve: string; counter: string;
  measurements: Record<string, unknown>; needsReanalysis: boolean; rank: number;
};
export type UBin = { start_ms: number; end_ms: number; risk: number | null; groups: Record<string, number>; top?: string; ids: string[] };

export const GROUP_LABEL: Record<string, string> = {
  opening_promise: "Opening & promise", progress: "Progress", comprehension: "Clarity", questions_payoff: "Questions & payoff",
  interruptions: "Interruptions", delivery: "Delivery", visual_pacing: "Visual pacing", narrative: "Story", pacing: "Pacing", visual: "Visuals", text: "On-screen text",
  technical: "Recording",
};
export const GROUP_ORDER = ["opening_promise", "progress", "comprehension", "questions_payoff", "interruptions", "delivery", "visual_pacing"];

const RULE_TITLE: Record<string, string> = {
  setup_before_substance: "Long setup before the first real point", no_hook_yet: "No clear hook yet",
  payoff_pending: "The title's promise hasn't started yet", low_novelty: "Little new information here",
  repetition: "Repeats an earlier point", long_sentences: "A very long sentence", fast_pace: "Faster than your usual pace",
  slow_pace: "Slower than your usual pace", filler_density: "A cluster of filler words", dead_air: "A silent gap",
  cta_or_sponsor: "A request interrupts the flow", outro: "A long sign-off", extended_abstraction: "A long stretch without an example",
  term_used_before_explanation: "A term is used before it's explained", open_question: "A question that isn't picked up again",
  unanswered_question: "A question that isn't picked up again", delayed_answer: "A question answered much later",
  long_static_shot: "One shot is held a long time", dense_text_fast_speech: "Dense on-screen text while you talk fast",
  flat_low_energy: "Delivery goes flat and quiet", loudness_drop: "The audio suddenly gets quieter",
};
export const ruleTitle = (rule: string) => RULE_TITLE[rule] ?? rule.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

const SEV_ORDER: Record<Sev, number> = { high: 0, medium: 1, low: 2 };
const sevOf = (s?: string): Sev => (s === "high" || s === "medium" || s === "low" ? s : "medium");
const strengthLabel = (s?: string) => !s ? "Provisional" : s === "supported" ? "Supported" : s === "provisional" ? "Provisional" : s.replace(/_/g, " ");
const preserveText = (p?: string | string[]) => !p ? "" : Array.isArray(p) ? p.join("; ") : p;

export function textAt(segments: Segment[], iv: Interval) {
  return segments.filter((s) => s.interval.end_ms > iv.start_ms && s.interval.start_ms < iv.end_ms).map((s) => s.text).join(" ");
}

export function modelFindings(pred?: Prediction): ModelFinding[] {
  if (!pred) return [];
  const f = Array.isArray(pred.findings) ? pred.findings : Array.isArray(pred.analysis?.findings) ? pred.analysis!.findings! : [];
  return f.filter((x) => x && typeof x.start_ms === "number" && typeof x.end_ms === "number");
}

function fromModel(f: ModelFinding, i: number): UFinding {
  const group = f.cause_group ?? "progress";
  return {
    id: f.finding_id, source: "model", title: f.title || ruleTitle(f.rule_id), group, groupLabel: f.group_label || GROUP_LABEL[group] || group,
    start_ms: f.start_ms, end_ms: f.end_ms, severity: sevOf(f.severity), strength: strengthLabel(f.evidence_strength),
    quote: f.quote ?? "", earlierQuote: f.earlier_quote ?? undefined, earlierStartMs: f.earlier_start_ms ?? undefined,
    mechanism: f.mechanism ?? "", suggestion: f.suggestion ?? "", preserve: preserveText(f.preserve), counter: f.counter_explanation ?? "",
    measurements: f.measurements ?? {}, needsReanalysis: !!(f.needs_reanalysis ?? f.requires_reanalysis),
    rank: typeof f.priority_rank === "number" ? f.priority_rank : 1000 + i,
  };
}

function fromIssue(issue: Issue, segments: Segment[], i: number): UFinding {
  const s = issue.suggestions[0];
  return {
    id: issue.issue_id, source: "issue", issue, title: issueLabel(issue.type), group: issue.risk_track, groupLabel: GROUP_LABEL[issue.risk_track] ?? issue.risk_track,
    start_ms: issue.affected_interval.start_ms, end_ms: issue.affected_interval.end_ms, severity: issue.severity,
    strength: issue.evidence_status === "supported" ? "Supported" : "Provisional",
    quote: textAt(segments, issue.affected_interval),
    mechanism: issue.explanation, suggestion: s ? (s.proposed_text ? `${s.rationale} Proposed wording: “${s.proposed_text}”` : s.rationale) : "",
    preserve: "", counter: issue.counter_explanation, measurements: {}, needsReanalysis: !!s?.requires_reanalysis, rank: 500 + i,
  };
}

/** All findings, best first. Model candidates keep their own priority_rank when the package provides one. */
export function allFindings(pred: Prediction | undefined, issues: Issue[], segments: Segment[]): UFinding[] {
  const model = modelFindings(pred).map(fromModel);
  const narrative = issues.filter((x) => x.review_status !== "dismissed").map((x, i) => fromIssue(x, segments, i));
  const hasRank = model.some((f) => f.rank < 1000);
  const sorted = [...model, ...narrative].sort((a, b) =>
    (hasRank ? a.rank - b.rank : 0) || SEV_ORDER[a.severity] - SEV_ORDER[b.severity]
    || (a.strength === "Supported" ? 0 : 1) - (b.strength === "Supported" ? 0 : 1) || a.start_ms - b.start_ms);
  return sorted;
}

/** 5-second transcript risk bins, from the new top-level list or the older analysis list. risk is 0–100 or null (unknown). */
export function riskBins(pred: Prediction | undefined, findings: UFinding[]): UBin[] {
  const raw: PredRiskBin[] = Array.isArray(pred?.risk_bins) ? pred!.risk_bins! : Array.isArray(pred?.analysis?.risk_bins) ? pred!.analysis!.risk_bins! : [];
  return raw.map((b) => {
    const start_ms = b.start_ms ?? Math.round((b.start_s ?? 0) * 1000);
    const end_ms = b.end_ms ?? Math.round((b.end_s ?? (b.start_s ?? 0) + 5) * 1000);
    const risk = typeof b.risk === "number" ? b.risk : typeof b.score === "number" ? b.score : null;
    const ids = b.finding_ids ?? findings.filter((f) => f.source === "model" && f.start_ms < end_ms && f.end_ms > start_ms).map((f) => f.id);
    const top = b.top_finding_id ?? findings.find((f) => ids.includes(f.id))?.id;
    return { start_ms, end_ms, risk, groups: b.groups ?? {}, top: top ?? undefined, ids };
  }).filter((b) => b.end_ms > b.start_ms);
}

/** Measurement keys in plain words for the evidence panel. */
export const MEASURE_LABEL: Record<string, string> = {
  feature_strength: "Detector strength (0–1)", affected_duration_s: "Length (s)", new_content_terms: "New words here",
  content_term_count: "Content words", passage_lexical_novelty: "Share of new words", best_earlier_trigram_overlap: "Overlap with the earlier passage",
  threshold: "Threshold", longest_sentence_words: "Longest sentence (words)", threshold_words: "Threshold (words)",
  speaker_median_wpm: "Your usual pace (words/min)", relative_threshold: "Relative threshold", detector: "How it was detected",
  duration_s: "Length (s)", threshold_s: "Threshold (s)", abstract_term_matches: "Abstract terms", sentences: "Sentences",
  concrete_marker_matches: "Concrete examples found", term: "Term", gap_s: "Gap (s)", first_use_ms: "First use", definition_candidate_ms: "Possible definition",
  definition_detection: "How the definition was found",
};
