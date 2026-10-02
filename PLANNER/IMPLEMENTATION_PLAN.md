# Build sequence and phase gates

This is the execution order for a later coding agent. Do not interpret this planning task as authorisation to start coding now. Once implementation is requested, complete each gate before dependent work. Use one issue/task per milestone; do not build every detector in parallel before the first complete video.

## P1 — Diagnose

**M0 Contracts and feasibility (D01–D07,US01/06).** Implement canonical schemas and an intentionally small valid/partial package fixture. Create isolated candidate environments, resolve hashes and freeze successful locks. Run hardware/model access preflight and the bounded clip qualification. Record exact GPU, dtype, peak memory and stage throughput. Exit: actual image inference + ASR + OCR + valid evidence output under one qualified profile. If primary hardware is absent, choose declared fallback explicitly; do not pretend documentation is a passing GPU test.

**M1 Media and evidence pipeline (US01/02).** Implement source PTS/proxy mapping, ASR+alignment, cuts/pause/technical signals, OCR tracks and clip sampling. Add journal/fingerprint/checkpoint execution from day one. Run one full video and manually check opening/middle/end timing. Exit: complete evidence ledger with modality coverage, including honest unknowns.

**M2 Reasoning and scenarios (US02/03/04).** Implement promise ledger, repetition/tangent candidates, bounded visual observations, narrative proposals, validators, deduplication, actionable suggestions and deterministic scoring. Add RETENTION_MODEL golden tests. Export package with source evidence and provenance. Exit: useful supported issues on the first video, valid partial-stage behaviour, correct formula values, no LLM percentages.

**M3 Local review slice (US01–04).** Build FastAPI atomic importer/SQLite/media range delivery; minimal React project/review page with player, transcript, timeline, issues and assumptions controls. Use saved real package. Exit: import→click issue→seek→inspect evidence→read suggested fix; missing stages and assumed retention are obvious. UI styling only sufficient for readability/Hindi; no animations required.

P1 ends only after all four milestones. If time is short, finish this vertical slice and declare the remaining phases unfinished rather than shipping disconnected mock screens.

## P2 — Improve

**M4 Contextual detectors (US02).** Add requiredP2 features in FEATURES, driven by P1 failure cases: caption correspondence/dwell, visual-speech mismatch, meaningful scene roles, transition/prerequisite review. Optional motion/pitch features remain off unless a measured need appears. Exit: clear examples of added visual insight and negative controls that avoid needless flags.

**M5 Plans, comparisons and reruns (US04/06).** Implement edit-plan validation, source→hypothetical timeline map, conflict reporting, assumption-labelled comparison, plan export, rerun-request export and child-run import. Externally edit one video and fully reanalyse it. Exit: immutable original/edited lineage, correct duration mapping, no inherited stale citations, hypothetical and reanalysed outputs visibly distinct.

**M6 Grounded chat (US05).** Implement bounded evidence retrieval and strict response schema, citation validation, refusal for unseen details and proposal-to-plan button. Exit: factual answers cite current evidence; no cross-run contamination; API failure leaves review usable. Nonstreaming answer is acceptable; typing animation is irrelevant.

## P3 — Demonstrate and evaluate

**M7 Freeze and holdout (US07).** Freeze prompts/profiles/locks, split and annotate natural examples, execute baselines/ablations and held-out evaluation. Record precision/localisation/usefulness/coverage plus runtime. Process remaining demonstration videos using cached weights/stage batching. Exit: four real complete packages, or explicitly documented partial shortfall, with transparent measured counts and limitations.

**M8 Hardening and rehearsal (US07/08 conditional).** Test corrupt import/resume/offline operation, local media playback, saved reports and clear assumptions labels. Optional actual-metric importer only if real matching data is available and core gates have passed. Rehearse five-minute judge flow and fallback withoutGPU/network. Exit: stable frozen local demonstration, reproducible packages, no fake live processing or accuracy claims.

## Integration and change control

At each milestone review changes against requirement IDs, schema version, feature catalogue and risk register. Dependency/model/prompt changes record why and which outputs invalidate. A decision change updates the owning specification before implementation spreads the alternative. Reuse passing checks; rerun those affected by new changes rather than repeatedly testing unrelated code.

Implementation completion evidence must include: contract tests, representative extraction checks, actual GPU qualification report, import/review smoke test, formula fixtures, lineage/rerun test, evaluation sample counts and remaining limitations. A beautiful UI, valid JSON, or successful model load alone is not completion.
