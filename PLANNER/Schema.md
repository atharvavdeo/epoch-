# Canonical schema and interchange contract

Schema version `1.0.0`; UTF-8 JSON/JSONL. Pydantic v2 is the canonical validator; generate JSON Schema and TypeScript types from it during implementation. The descriptions here are normative design contracts, not existing executable schemas. Reject unspecified fields in model-produced objects. Package-level forward compatibility follows §9.

## 1. Common types and invariants

IDs are lowercase UUID strings except evidence/artifact IDs, which may be `ev_`/`art_` plus SHA-256 prefix (at least 16 hex characters; collision checked). SHA-256 values are full 64-character lowercase hex. Dates are RFC3339 UTC. Durations/time bounds are integer milliseconds on **source presentation timeline starting at zero**. Intervals are half-open `[start_ms,end_ms)` with `0 ≤ start < end ≤ asset.duration_ms`. Terminal zero-duration markers use a separate `at_ms`, never an invalid interval. Computation retains rational source PTS/time_base in frame references before rounding to milliseconds. Bytes and pixel dimensions are positive integers; numbers must be finite, never NaN/Infinity.

`language`: `en|hi|mixed|unknown`; `category`: `tech_review|education|other`; `modality`: `speech|visual|audio|text`; `precision`: `frame|word|segment|sampled|estimated`; `evidence_status`: `supported|provisional|unknown`; `stage_status`: `pending|running|complete|partial|failed|skipped|cancelled|stale`. A confidence supplied by a detector is named `detector_confidence`; model self-rated confidence is not a calibrated probability. Optional means absent is permitted; nullable means present with null is permitted. Canonical stored records include nullable fields explicitly.

Every artifact has `artifact_id`, `kind`, `relative_path`, `sha256`, `bytes`, `producer_stage_id`, `input_fingerprint`, `created_at`. Relative paths must remain inside package root and use POSIX separators. No executable artifact is accepted. Every stage output is tied to one `run_id`, `asset_id` and `schema_version`.

## 2. Entity contracts

| Entity | Required fields | Nullable/optional fields and constraints |
|---|---|---|
| Project | project_id, title, category, declared_language, created_at, updated_at | active_run_id nullable; description optional; title 1–300 Unicode characters. |
| Asset | asset_id, project_id, kind(video/script), sha256, original_name, bytes, duration_ms, time_origin, metadata | parent_asset_id nullable, original_media_artifact_id nullable; script duration is estimated and time_origin=`estimated_script`; video=`source_pts`. metadata video: dimensions, streams, rotation, fps rational, VFR flag, source_start_pts, time_base, has_audio. |
| Run | run_id, project_id, asset_id, status, schema_version, config_hash, input_fingerprint, model_profile, created_at, stages[], coverage_summary, provenance | parent_run_id nullable, source_edit_plan_id nullable, finished_at nullable; status planned/running/complete/partial/failed/cancelled. Parent may reference same or parent asset. |
| Stage | stage_id, name, status, fingerprint, attempt_count, artifact_ids[], dependencies[], started_at, finished_at | error nullable; versions and config required once started; complete requires all artifacts valid. timestamps nullable before start. |
| Provenance | code_revision, environment_locks[], models[], prompts[], hardware, precision, sampling_profile, detector_config, scoring_version, source_rights_note | external_service_model nullable; code_revision may be `uncommitted:<source_tree_hash>` but never omitted. models contain model_id, revision, weight_digest/index_digest, dtype and device placement. |
| TranscriptSegment | segment_id, run_id, interval, text, language, precision, source(asr/user), word_ids[] | speaker_id nullable (diarization not required); original_asr_text nullable after correction; correction_revision integer default0. |
| Word | word_id, segment_id, text, start_ms, end_ms, alignment_status(aligned/unaligned/estimated) | times nullable together when unaligned; detector_confidence nullable. Never fabricate word precision from evenly distributed words. |
| Shot | shot_id, run_id, interval, start_boundary_source, end_boundary_source, metrics | boundary confidence nullable; scene_id nullable; shots cover complete decodable visual timeline without overlap, gaps separately recorded. |
| Frame | frame_id, artifact_id, at_ms, source_pts, time_base_num, time_base_den, width, height, source_width, source_height, sampling_reason | crop_box nullable in original pixel coordinates; clip_id nullable; transformations required list (possibly empty). |
| OCRTrack | track_id, run_id, interval, text, language, samples[], visibility_precision, detector_confidence | samples contain frame_id, quad in source pixels, observed_text, confidence; interval is inferred between samples and must say sampled. |
| Signal | signal_id, run_id, feature_id, interval, modality, name, value, unit, method, evidence_ids[], validity | value scalar/array/object or null; validity measured/estimated/unknown; unknown_reason required if null. Per-signal format registered, not arbitrary model JSON. |
| Observation | observation_id, run_id, clip_id, interval, modality, statement, evidence_ids[], status, sampled_frame_ids[], model_revision, prompt_hash | `unknown_reason` nullable; accepted interval cannot be narrower than evidence supports unless explicit frame event; statement max2,000 chars. |
| Evidence | evidence_id, run_id, asset_id, kind(transcript/frame/ocr/signal/observation), ref_id, interval, precision, provenance_stage_id | quote nullable (must equal source substring if present); frame-specific interval describes inspected clip, and frame ref carries exact at_ms. |
| Promise | promise_id, run_id, title_quote, obligation, setup_evidence_ids[], fulfilment_evidence_ids[], status(unaddressed/partial/fulfilled/uncertain) | partial_interval nullable; fulfilled_interval nullable; must not mark fulfilled without supporting evidence. |
| Issue | issue_id, run_id, type, affected_interval, modality_tags[], risk_track, severity(low/medium/high), evidence_status, evidence_ids[], explanation, counter_explanation, suggested_edit_ids[], review_status(open/accepted/dismissed), cause_group_id | comparison_intervals optional e.g repetition origin; review_reason nullable; issue types from FEATURES. risk_track=`narrative|visual|pacing|text|technical`. |
| EditSuggestion | suggestion_id, run_id, issue_ids[], operation, source_interval, destination_ms, proposed_text, rationale, prerequisites[], requires_reanalysis | operation cut/move/rewrite/insert_visual/adjust_audio; source_interval nullable for insertion; destination_ms nullable except move/insertion; proposed_text required for rewrite; retained as proposal. |
| EditPlan | plan_id, project_id, base_run_id, revision, state, operations[], validation_errors[], created_at, updated_at | scenario_id nullable; operations have operation_id and linked suggestion_id nullable. |
| Coverage | run_id, modality, interval, status(observed/partial/unknown/not_applicable), sampling_profile, evidence_ids[] | reason nullable except partial/unknown requires reason. `observed` means according to sampling profile, not every instant visible. |
| RiskBin | run_id, interval, track_values, combined_lower, combined_upper, display_value, evidence_coverage, contributing_issue_ids[] | track values nullable if unknown; display_value nullable under RETENTION_MODEL gating; lower/upper ∈[0,1]. |
| RetentionScenario | scenario_id, base_run_id, edit_plan_id, mode(baseline/hypothetical/reanalysed), formula_version, assumptions, bins[], summary, coverage_status, labels[], created_at | edit_plan_id nullable; bins contain start/end retention bounds, risk bounds, conditional_drop and absolute_drop when defined; summary includes duration, assumed_avd_seconds, assumed_apv_pct, assumed_end_pct nullable. |
| TimelineMap | map_id, plan_id, original_asset_id, hypothetical_duration_ms, pieces[], status | piece: original interval + new interval + operation_id; linear unit-rate mapping only; inserted intervals have original=null. Moved pieces reorder explicitly. |
| ChatMessage | message_id, project_id, run_id, role(user/assistant), content, citations[], status, created_at | referenced_plan_id nullable; citations contain evidence_id and claim text span; failure code nullable. No secret/system prompt storage in user export. |
| RerunRequest | request_id, schema_version, project_id, asset_sha256, base_run_id, base_manifest_sha256, requested_stages[], intervals[], reasons[], overrides, created_at | overrides only allowlisted sampling/prompt/config fields, no shell/model URL injection. |
| ActualMetricSeries | series_id, asset_id, run_id, source_kind, metric_kind, interval_definition, samples[], imported_at, provenance_note | creator_data_date_range nullable, audience_context nullable, source_file_digest required; metric_kind `audience_watch_ratio|first_pass_survival|replay_intensity`; source_kind team_export/public_dataset; replay cannot be source of first_pass_survival. |
| Evaluation | evaluation_id, config_hash, split_id, asset_ids[], annotation_revision, metrics[], limitations[], created_at | metrics require name,value,unit,numerator,denominator,matching_rule; unsupported metrics value=null with reason. |

An issue requires evidence but an observation can be unknown with no evidence claim; unknown observations do not generate accepted issues. `cause_group_id` merges manifestations of the same defect, e.g CTA and sponsor tags. Each issue has one risk_track even if several modality tags; multiple labels do not multiply its numerical contribution.

## 3. On-disk package

The export name is `<asset-short-id>_<run-id>.retention.zip`. Required root `manifest.json` describes all files and immutable input fingerprints. Contents:

- `data/project.json`, `asset.json`, `run.json`, `coverage.jsonl` always present.
- `data/transcript.jsonl`, `words.jsonl`, `shots.jsonl`, `frames.jsonl`, `ocr.jsonl`, `signals.jsonl`, `observations.jsonl`, `evidence.jsonl`, `promises.jsonl`, `issues.jsonl`, `suggestions.jsonl`, `risk.jsonl`, `scenarios.jsonl`: present as empty files when stage legitimately has no outputs; absent only if corresponding stage failed/skipped with reason in manifest.
- `media/proxy.mp4` optional for script-only; required for self-contained video demo. `media/audio.wav` excluded by default to avoid duplicating source, optional in operator diagnostic package.
- `frames/<frame-id>.jpg` evidence thumbnails/crops used by accepted findings; complete sampling frames optional operator package.
- `provenance/config.json`, `models.json`, `environment-locks/`, `prompts.json` (IDs/digests, templates without secrets), `stage-events.jsonl`, `errors.jsonl`.
- `evaluation/` optional P3 records. `requests/` optional original request for traceability.

Manifest fields: schema_version, package_id, project_id, asset_id, run_id, created_at, package_kind(`analysis|partial_analysis`), source_sha256, files[] (Artifact records), required_stage_names[], completed_stage_names[], missing_stage_names[], exported_by_version. Manifest does not hash itself; package SHA is computed on the downloaded ZIP and stored by importer. Every listed file must exist and hash-match; every unlisted file is rejected. Data files must not recursively contain a copy of their manifest.

## 4. Relational persistence

SQLite foreign keys ON. Tables: projects, assets, runs, stages, artifacts, evidence, issues, suggestions, edit_plans, scenarios, chat_messages, imports, metric_series, evaluations. Large frame/signal/transcript JSONL files remain immutable artifacts; searchable summaries and evidence rows indexed in SQLite. Unique `(run_id,evidence_id)`, `(run_id,issue_id)`, `imports.package_sha256`, `(asset_id,input_fingerprint)` for a completed analysis version; same input may have failed attempts retained separately. Index issues on run+start, evidence on run+kind, runs on project+created_at. Active run switch is transactional and never deletes older run data.

Import verifies everything in staging, then moves files under run directory and commits metadata. If process dies between move and transaction, import journal enables orphan staging cleanup without deleting referenced runs. Deleting a project is outside baseline UI; no accidental cascade from version switching.

## 5. Fingerprints, dependency invalidation and resume

Fingerprint = SHA-256 of canonical sorted JSON containing upstream artifact hashes, relevant configuration subset, tool/environment lock digest, model revision, prompt hash and schema producer version. Media preprocessing depends on asset bytes; ASR on audio+ASR profile; alignment on ASR text+audio+language model; OCR on sampled frames+OCR profile; VLM on frames+associated transcript/context+prompt; narrative on title+transcript+observations+signals+prompt; risk on validated issues+coverage+scoring configuration; scenario on risk+assumptions+edit plan.

A title change invalidates promise/narrative/issues/risk/scenario, not decoded media. Transcript correction invalidates alignment for affected spans plus semantic downstream outputs and any VLM observations whose prompts contained that text. Frame-density change invalidates affected VLM/OCR outputs and downstream findings. Model change invalidates its stage and dependents. New video bytes are a new asset: reuse only when exact segment identity is independently established, not merely similar names or duration. Default reanalyse new edited video fully.

## 6. Edit semantics

Cuts operate on original half-open intervals. Sort and reject overlapping operations; adjacent cuts may be explicitly merged. A move references original coordinates and a destination in the original timeline; destination inside removed/moved span is invalid. P2 supports **one move plus nonoverlapping cuts per plan**; multiple moves require separate plans to prevent ambiguous ordering. Resolve cuts first, then map destination using remaining source pieces. Rewrite/visual/audio proposals have no numeric retention uplift unless a scenario assumption is explicitly supplied and displayed; default needs_reanalysis.

Estimated timing of rewritten speech is not word-aligned. Plans cannot cut all media or produce duration outside a meaningful playable range; minimum hypothetical duration 60s. Immutable original evidence is retained. Dismissal of an issue changes review state; it does not erase evidence or automatically prove zero risk. Scenario inclusion choices are separately recorded.

## 7. Errors and structured model output

Error object: `code`, `message`, `stage`, `retryable`, `attempt`, `evidence_ids`, `details` (allowlisted, secret-redacted), `recommended_action`, `occurred_at`. API error envelope: error plus request_id. Model outputs may contain only observation/issue proposal fields permitted by the prompt schema. IDs/time bounds are validated against provided context; reject extra fields, invented evidence, unsupported precision and nonfinite numbers. At most one repair prompt contains validation errors and the original evidence; after that record a partial stage.

## 8. Import limits

Prototype defaults: compressed ZIP ≤2GiB, expanded ≤5GiB, ≤20,000 entries, individual JSON/JSONL ≤100MiB, image ≤25MiB, proxy ≤2GiB, compression ratio ≤100:1, path ≤240 characters. Reject absolute paths, traversal, symlinks, devices, executables, duplicate normalised paths and encrypted ZIPs. Check limits while streaming, not after extraction. Accept image/video formats only after content sniff/decode checks. Never render transcript/OCR as HTML. Hashes protect integrity, not scientific truth.

## 9. Version evolution

Major schema mismatch rejects import with supported versions. Minor updates accepted only if a registered migration exists; unknown fields cannot silently disappear. Migrations create a new local derived representation and preserve original package hash. Patch releases may clarify validation without changing required shape. Future calibrated scores need a separate calibration/model version and training provenance; they cannot overwrite heuristic scores under formula v1.
