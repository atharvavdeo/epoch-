# Evaluation, acceptance and demonstration

## 1. What can be measured now

Measure extraction/timestamp correctness, issue precision/localisation, evidence validity, edit usefulness, runtime, memory, import reliability and repeatability. Human annotations of defects are **not** actual audience-retention curves. The product may demonstrate the PS's predicted-curve interface using explicit assumptions, while stating that empirical audience-curve accuracy is not yet established.

Four or five videos are a demonstration set, not enough to claim generalisation. Recommended collection: English tech review, Hindi/Hinglish tech review, English education, Hindi/Hinglish education, optional fifth stress-case video. Use authorised/downloadable source copies with titles and provenance. Do not claim India-region videos are Hindi without checking speech.

## 2. Dataset and annotation protocol

Before tuning, assign two videos development and two held-out evaluation, covering both languages/categories as well as possible; optional fifth is a frozen stress test. Keep all clips from one video in one split; if creator overlap exists, disclose it and prefer creator separation. Record content rights/provenance, duration, language distribution, category, source hash, media quality and whether title matches source. Never choose only obvious poor videos.

Annotate6–10 candidate or control spans/video, including random normal spans, useful static teaching, deliberate pauses and valid recaps. Two team reviewers independently label issue type, affected interval, supporting evidence, severity, usefulness of suggested edit and whether adequate context was supplied. Resolve disagreements with a recorded adjudication; retain originals and disagreement count. Reviewers must not see model severity while first annotating if feasible. Label taxonomy is FEATURES; allow no_issue and insufficient_evidence.

Freeze detector thresholds/prompts/model/scoring configuration after development. Evaluate held-out set once; any fix prompted by held-out failures makes those examples development data, requiring new held-out examples for a fresh generalisation claim. With tiny samples, show raw counts and examples instead of impressive aggregate percentages alone.

## 3. Metrics and proposed acceptance targets

| Metric | Calculation / target | Interpretation |
|---|---|---|
| Referential validity |100% displayed evidence IDs/quotes/intervals resolve and validate | Software correctness; invalid claims excluded. |
| Issue precision | Matched adjudicated true issues / all evaluated surfaced issues; target≥0.80 on at least20 surfaced issues, otherwise report insufficient sample | Local feasibility target, not industry performance claim. |
| Issue localisation | Temporal IoU≥0.5 for interval defects; event tolerance≤2s for approximate semantic markers; shot boundary tolerance≤2 source frames on manually checked constant-FPS clips | Report by precision class; do not compare segmentASR against frame labels without tolerance distinction. |
| Recall | Matched labelled issues / all labelled issues **only within exhaustively annotated spans** | Candidate-only annotations cannot estimate full-video recall. |
| Edit usefulness | Reviewer marks actionable + preserves meaning; report useful/total and harm cases | No claim about actual retention uplift. |
| Title payoff | Exact title obligation match and correct partial/fulfilled distinction, with timing error | Keyword mentions are not enough. |
| OCR | Character error rate on manually transcribed sampled English/Hindi crops; report separately | Small-text and code-mixed limitations explicit. |
| ASR | WER/CER on selected natural speech spans, languages separate; timing error where alignable | No universal Hindi accuracy threshold from handful of clips. |
| Memory/runtime | Peak allocated/reservedGPU, peakRSS, cold setup/download/load, warm seconds/minute, semanticAPI latency/cost | Measured on named GPU/driver and exact sampling settings. |
| Coverage | Weighted/per-modality observed/unknown durations and failed clips | High schema validity with missing visual coverage is not full success. |
| Reliability | Duplicate import idempotent; disconnect resume reuses all valid completed units; invalid ZIP atomic rejection | Required engineering acceptance. |

If precision target fails, inspect mechanisms on development data: ASR, sampling, OCR, judgement or duplicate aggregation. Reduce unsupported issue types rather than merely increasing confident wording. Do not automatically soften the benchmark to pass. A fallback model must satisfy the same rubric; label a weaker/partial demonstration if it cannot.

## 4. Baselines and ablations

Run a deterministic-only baseline (cuts/pauses/black/freeze candidates) and transcript-only semantic baseline on the frozen spans. Compare their issue precision/coverage to multimodal analysis. This tests whether the VLM adds useful visual evidence rather than only verbose narration. Use exact same spans and annotation matching. Qualify a challenger only if a named failure persists; cap the initial model comparison to the six clips in DesignDecisions. Never combine multiple models' best outputs and report them as one model's performance.

## 5. Functional tests to build

Test native source/proxy timestamp mapping on variable-frame-rate footage, missing audio, rotated portrait footage, tinyHindi captions, long static useful slide and rapid cuts. Test silence detected as a measurement without automatic defect. Test ASR unaligned words and code-mixed spans. Verify VLM receives actual image tensors with timestamp labels; a text-only successful JSON response is not a video-analysis pass.

Contract tests: malformed IDs, out-of-range times, unsupported schema, unknown enum, hallucinated source quote, cross-run citation, NaN, repeated package, wrong media hash, interrupted ZIP, path traversal, duplicate normalised paths and oversized archive. Tests must verify behaviour rather than mirror implementation structure.

Scoring tests: all golden fixtures in RETENTION_MODEL, missing-track masking, no duplicate cause penalty, all-zero hazard safe integration, cut/reorder mapping and baseline comparison assumptions. UI checks: seek from issue/chat, source vs proposed text distinction, local media Range responses, keyboard navigation, Hindi fonts, partial-stage status, offline package access. P2 chat checks: answer known fact with evidence, decline unseen interval/audio question, ignore injected transcript instructions, no cross-project disclosure.

## 6. Authentic retention data if supplied later

Require matching video identity/version, metric name/definition, native bins, date range, audience/source context and provenance. YouTube analytics elapsedVideoTimeRatio uses100 equal bins; for5–15min videos that is roughly3–9s/bin. Do not claim1s measured accuracy by interpolating. Preserve raw native bins; display resampling clearly. Watch ratio can exceed1 and rise because of repeats. Relative retention is a comparison metric, not a percent of starting viewers. [S17–S18]

For a matching observable metric, proposed later evaluation includes per-video MAE/RMSE, rank correlation of risk with negative curve changes, and event localisation with documented bin tolerance. Metric semantics must first match model output; do not compare monotone first-pass survival directly to replay-influenced watch ratios and call the error calibrated prediction accuracy. Baseline comparisons and video-level holdouts remain required. These steps are conditional backlog unless genuine matching data arrives duringP3.

## 7. vRetention decision

The repository supplies datasets and notebook analyses; it is not a ready trained retention predictor. The public YouTube series comes from most-replayed heatmap SVGs. Use as optional research on replay peaks or exploratory duration/category distributions after checking licensing, duplicates, extraction and source availability. Do not use its normalised curve as an abandonment label, invert peaks into drop-off, or present interpolation as new temporal measurements. It cannot close today's actual-retention validation gap. See RESEARCH for the repository and paper.

## 8. Judge demonstration and fallback rehearsal

Prepare four complete self-contained packages and optional fifth stress-case. Each includes local proxy, evidence and precomputed findings. Pick one clear supported script issue, one supported visual/text issue, one useful static scene correctly left unflagged, and one before/after scenario with honest assumptions. Demonstrate click→seek→evidence→suggestion→plan→comparison, then a genuine reanalysed edited upload if time permits.

Show provenance and measured evaluation denominators. State which outputs were computed earlier and which chat answers are live. If internet fails, open saved results and previously saved chat examples labelled as such; do not animate a fake inference. If noGPU is available, the cached analyses still work. If a package is partial, show its gap openly. Rehearse disconnect/import/failure states before demo, not onstage.

P3 deliverable report has: dataset/splits, profile/locks, diagnostic results, representative successes/failures, runtime/memory, evidence coverage, formula assumptions, and explicit “actual audience-curve accuracy: not evaluated” unless authentic matching evaluation was completed.
