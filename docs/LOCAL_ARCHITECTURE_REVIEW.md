# Local architecture review — 2026-10-03

Reviewed main at `320af3a32fa8bf78da24b804adc4728fc26126ab` using code-review-graph 2.3.9 and direct source reads. The graph indexed 108 files, 914 nodes and 9,484 edges, with 15 communities and 77 inferred execution flows. Static edges guide navigation; they do not establish runtime correctness.

## From source media to review

1. `pipeline.cli analyze` registers the source and project in a content-addressed workspace. The controller runs probe, playback proxy, waveform measurements, video scan, sampled frames, speech recognition and word alignment. OCR is opt-in. A visual job bundles inputs for Colab; it does not run Qwen locally.
2. `pipeline/orchestration/stage.py` fingerprints stage version, configuration, model metadata, dependency output digests and a dependency lock. It verifies cached artifact hashes, writes through partial directories, records stage events and launches speech/embedding subprocesses in their isolated environments. ASR additionally checkpoints individual chunks.
3. `pipeline.cli finish` runs embeddings, narrative, prediction, scoring and package export. It stops at a failed or skipped stage to prevent later stages from exporting stale successful outputs. Missing visual results remain unknown.
4. Narrative reasoning builds candidates from measurements and transcript signals. Cerebras first identifies structure and title promises, then adjudicates candidates. Validators check evidence, quotes and proposed edits; a finding may survive without a safe edit.
5. The text predictor is a proportional-hazards model with documented prior weights, one-second features and assumed audience anchors. Its sensitivity band scales weights by 0.5 and 1.5. It is not trained or calibrated against real audience data. Separate scoring produces coverage-aware risk bins and the older assumed scenario.
6. `pipeline/package_export.py` builds a retention ZIP and validates it with `contracts/package.py`. The importer uses the same validation, extracts only listed files, stages them, then indexes the immutable run in SQLite. Duplicate package bytes reuse the existing run; different bytes with the same run identity are rejected.
7. FastAPI serves the built React site and its API from port 8765. SQLite indexes projects, assets, runs, evidence, findings, suggestions, imports and scenarios. Review decisions remain separate from immutable findings.
8. React supplies Projects, New analysis, Review, Edit plan, Evaluation and Settings. Review synchronizes playback, transcript, timeline, findings and evidence. Accepting an edit adds it to the plan; it does not edit the video or change the baseline prediction. Hypothetical comparisons are assumptions; an edited video must be analysed again for a new run.
9. The assistant retrieves transcript passages with BM25, combines them with run-specific findings, structure and prediction, and calls Cerebras. The server checks quotes and citation bounds and flags edits touching hooks, questions, transitions or quoted clips. These checks do not guarantee the advice is correct.

## Local verification

- Pulled main with a fast-forward and restored the existing local planning changes.
- Installed separate macOS Python 3.11 media, API and ASR environments, plus a graph tooling environment.
- Generated Mac-specific locks without overwriting Windows locks. ASR compilation required an explicit Python 3.11 interpreter; default compilation selected a Python 3.12-only AV release.
- `npm ci` and `npm run build` passed.
- Generated synthetic media; the media suite passed 49 tests and the API suite passed 3 tests. The end-to-end test uses mocked speech/embeddings/LLM, so this is not a real-model video run.
- ASR, WhisperX and sentence-transformers imported successfully on Apple Silicon.
- Local homepage and health endpoint returned HTTP 200.
- Cerebras authentication returned HTTP 200 and listed `gpt-oss-120b`. The key is in the git-ignored `.env`, with file mode 0600.
- Pinned speech/alignment/embedding model downloads were started. No real input video was supplied, so real-media inference and live narrative/chat answers remain unverified.

## Relevant gaps before further changes

- New analysis prepares CLI instructions and imports results; it does not upload media to start an analysis worker.
- New analysis and the API analysis-request route still generate Windows interpreter paths. Use `.venvs/media/bin/python -m pipeline.cli` on this Mac.
- `settings.lock_path` always selects the Windows lock, even when the Mac environment was installed from `*.mac.txt`. Mac run provenance currently fingerprints the wrong dependency lock.
- Below-normal subprocess priority is explicitly implemented only on Windows. Launch Mac heavy jobs with `nice -n 10`, keeping one heavy inference job at a time and six ASR threads.
- The declared stage order/status list omits `predict`, although `finish` runs it.
- Visual AI is on hold, OCR has not been exercised here, script-only backend is missing and mixed-language alignment remains unvalidated.
- The graph installer added project/client configurations, graph guidance and hooks. These are local uncommitted changes; nothing was pushed.

## Commands on this laptop

```sh
.venvs/api/bin/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8765
nice -n 10 .venvs/media/bin/python -m pipeline.cli analyze /absolute/path/video.mp4 --title 'Exact title' --category education --language en
nice -n 10 .venvs/media/bin/python -m pipeline.cli finish ASSET_PREFIX
.venvs/review/bin/code-review-graph build
```

Generated data and model caches are under `/Users/atharvadeo/Desktop/epoch-data`; readable exports are under this repository's `outputs/`.

## Completed real run

On 2026-10-03, `yt-dlp` downloaded https://youtu.be/ve7AA01vplE (286 s, English). All available local stages including qualified OCR completed; the package validated and was imported as run `5a80ca3b-788c-551f-bb5f-0a4cc2fc546b`. The website returned HTTP 200 for the run, transcript, timeline, prediction, relations, shots, issues, outputs, evaluation and settings. It exposes 462 files / 137.2 MB, with individual previews/downloads and an exact-byte original retention package download. Browser checks rendered the review and audio diagnostic preview. Live chat retrieved 8 passages, cited 3 moments and returned 3/3 verified quotes.

Whisper produced 83 segments and all 858 words aligned. OCR inspected 355 samples, produced 3,797 boxes and 746 tracks. Prediction: 66.9% average viewed, 47.6% at end, three drop moments; this remains an uncalibrated prior model. No issue candidates were accepted. Visual inference remains uninspected; a Colab job is available.

The Windows-command, lock-provenance and missing-predict status gaps described above were fixed. OCR qualification uses Mac fonts. Export version 6 preserves distinct spatial OCR tracks with otherwise identical text/timestamps. Final media tests: 49 passed; API: 4 passed; the OCR spatial-collision integration regression passed. The production website build passed.


## Analysis and review upgrade (2026-10-03)

Latest local review: http://127.0.0.1:8765/runs/09a2301a-4ebe-59c8-942b-5dc118b3d2d4

Text retention v2 is an exploratory, candidate-driven scenario: grouped mechanisms prevent duplicate penalties; fractional final bins and hazard integrals preserve actual duration. Text review has exact quotes, measurements, counter-explanations, preservation notes, semantic-risk candidates, and a promise ledger. Candidate acceptance is distinct from prediction. Immediate replies, framing/rhetorical questions, concrete similes and sub-five-second opening gaps suppress noisy findings. The example has four provisional text candidates, five scenario moments, and zero validated narrative findings.

`voice` reads PCM waveform pitch through normalized autocorrelation and combines aligned word timing with ten-second summaries. Voice pitch/range is not an emotion or engagement measure; source audio retains RMS, LUFS, silence, peak and clipping measurements. Example: 179.8 overall words/min, 115.1Hz median detected pitch, 7.44s silence. Qwen visual inference remains Colab only.

`jev` uses pinned jev-1.13.0 on the official TypeSafe endpoint, named questions sharing bounded context (12 passages per request, eight-call ceiling), strict probability/ID validation, 0.65 confidence review routing, and identical-request caching. Keys are server-side .env only. Cerebras supplies draft explanations/rewrites separately; shortening requires a verified earlier quotation and a lower word count. The example's earlier shortening opinion was rejected for unsupported duplication and routed to review. Model confidence is not editorial certainty or retention validation.

Chat retrieval now fuses offline multilingual E5 and BM25 over overlapping timed passages; corpus vectors and repeated query scores are cached. One below-normal-priority ASR subprocess runs at a time within the API encoder lock; six CPU threads. Cold model startup remains about 6–9s, and lexical fallback is explicit. Actual paraphrase/chat retrieval returned hybrid_e5_bm25 and a verified transcript quotation. It is not a broad retrieval benchmark.

Review defaults to Overview, with Text, Voice and Audio deep dives, cumulative assumed watch seconds, retention/baseline/sensitivity, lexical-risk, rate/pitch/variation/voicing, RMS and LUFS charts. Charts seek the player, preserve unknown gaps, and label assumptions. Text supports a selected-passage Jev question. Outputs includes the new diagnostics and readable reports; final run has 466 artifacts. API compatibility handles fractional timestamps and optional old-package diagnostics.

Validation: 67 media/pipeline tests plus six API tests passed; production frontend build and package self-validation passed; live API, semantic chat, selected Jev and browser chart rendering checked. Local server stays on port 8765. User PLANNER edits are preserved. Nothing committed or pushed. Retention calibration, editorial accuracy evaluation and visual Colab analysis remain outstanding.
