# Final integration verification — 2026-10-03

Kawal’s `ui final` commit `3f954f4fe857ef851dcfbb8f1ff327b9f97b36f4` was fast-forwarded into `atharva-new-branch`, starting from `9045c979d67ea72f050462824855bd92e9537eb6`. The following integration changes and checks were completed in that checkout. No existing local changes were present at the start.

## What changed

The incoming UI called analysis and polling endpoints that did not exist. Browser media uploads and pasted/file scripts now submit durable jobs through `/api/v1/analyses` and `/analyses/text`. `/jobs` provides polling and cancellation. One worker launches the shared pipeline in the isolated media environment at reduced priority with six ASR threads. Sources and atomic status persist locally. Cancellation stops the child process group; API shutdown stops active jobs and marks interrupted work failed. Retrying reuses valid stage caches. This worker is intended for one local API process.

Only packages that pass the existing validator and match the requested project are imported. Existing immutable run identity and idempotent import behavior remain in use. Identical media uploaded into a different project gets a separate scoped workspace.

Script analysis now runs parsing → embeddings → narrative → prediction → optional Jev → scoring → validated export/import. Plain-text timestamps are estimates at 150 WPM; subtitle cues are retained. Word alignment, measured speech rate, voice, waveform and shots are absent. Narrative version 15 excludes speech-rate/filler-rate signals for scripts; export version 9 records user-script inspection with no sampled frames or VLM. Script coverage records text evidence and unknown unmeasured modalities.

Existing-project resume loads the saved title/category/language. Partial stages remain visible as partial. Welcome and Settings disclose Cerebras and optional TypeSafe context calls. Retention charts and project summaries visibly label uncalibrated estimates.

One incoming prediction test failed because it compared a static-shot case to a no-shot case, changing several features at once. The test now compares the same feature set with and without the static-shot penalty. Prediction weights were not changed to satisfy the test.

## Automated checks

| Check | Result |
|---|---|
| Media/pipeline suite, excluding API-environment and optional VLM tests | 95 passed |
| API suite including analysis upload/worker regressions | 12 passed |
| TypeScript + Vite production build | Passed |
| Git whitespace/error check | Passed |

Commands:

```sh
.venvs/media/bin/python -m pytest --ignore=tests/test_api.py --ignore=tests/test_predict_api.py --ignore=tests/test_analysis_api.py --ignore=tests/test_vlm_codepath.py
.venvs/api/bin/python -m pytest tests/test_api.py tests/test_predict_api.py tests/test_analysis_api.py
# from apps/web:
npm run build
# from repository root:
git diff --check
```

API regressions exercise rejection of unsupported/empty/oversize/invalid-text inputs without creating projects, valid package commit/progress, real-child cancellation without import, and wrong-project rejection. Script integration exercises the actual parser, predictor, scorer, exporter and validator with mocked narrative responses; live checks below supply separate model evidence. API tests emit one upstream Starlette/httpx deprecation warning. The optional tiny-random VLM test was excluded; no local Qwen inference was run.

Code-review-graph was used first for scope, architecture, relationships, affected flows and review context, followed by implementation and test reads. The graph was rebuilt after integration. Automatic git-diff discovery in the MCP host was unreliable on this Mac, so review calls used explicit changed-file lists; empty graph coverage was checked against source tests. The combined 58-code-file review received a high graph risk score (0.88), reflecting its broad reach; graph test-gap counts are static hints, not measured coverage. Direct worker, cancellation, package and script tests were read and run to verify paths that the graph did not resolve.

## Actual local runs

| Source / exercised path | Job | Imported run | Evidence boundary |
|---|---|---|---|
| 286-second Ontology vs Metadata MP4, actual multipart upload into the existing project | `23255f0b-6394-4935-8205-876f938bbb79` | `de3d436e-3243-53bd-a952-cdb989de78a2` | Cached extraction/ASR/alignment/OCR retained; changed finish stages reran with real embeddings and cloud reasoning. Valid partial package; visual AI is missing. This was not a fresh full transcription. |
| Fresh 40-second English WAV excerpt, actual multipart upload | `3cc2acff-1f7b-4289-ad8f-e360571dfbf1` | `932cae17-a4f4-5653-80d7-da7a47d0fd44` | Fresh probe/proxy/waveform, Whisper (57.23 s), alignment (6.77 s), embedding, narrative, prediction, voice, Jev, score and validated import. Blank picture for playback. Package is partial because visual/frame/OCR stages are not run. |
| Script entered and started through the browser form | `a4c8ed5f-487e-4da7-b1ec-bd7e1eb2568c` | `13317284-05f9-56f6-aa6d-9761cdcd8fbc` | Form submission, polling and automatic Review navigation worked. Real models produced a validated script package. |
| Same script/project after the final speech-measurement correction | `e6827201-cb50-46d4-b322-76fba0d8c83c` | `f2ab5388-7bf5-5dbf-ad54-d505a4b9946b` | Narrative and dependent stages reran; valid cached embedding/Jev reused. Complete script package, no F40/F52 speech signals, all narrative signals text-only, user-script provenance, no missing required script stages. |

Review DOM/rendering was checked on actual imported runs. The script shows uncalibrated estimates and unavailable voice/audio. Browser console inspection at the completed script review returned no warnings/errors. Test-generated runs were retained locally for inspection. Export provenance honestly records the tested uncommitted source tree; those packages are not presented as clean-commit release artifacts.

Local video review: http://127.0.0.1:8765/runs/de3d436e-3243-53bd-a952-cdb989de78a2

Final script review: http://127.0.0.1:8765/runs/f2ab5388-7bf5-5dbf-ad54-d505a4b9946b

## Readiness

The exercised local English video/audio/script workflow is ready for a local demonstration and continued creator review. The server remains on loopback port 8765; configured models and cloud credentials are required.

This is not production or scientific qualification. Retention remains assumption-based and uncalibrated; editorial accuracy has no frozen human-reference benchmark. Visual AI was not exercised, Hindi/Hinglish remains unqualified, the new worker was not run on Windows, and broad media-format/long-duration stress coverage was not performed. These are explicit boundaries, not hidden successful checks. Audio intentionally has no visual evidence. No deployment or main-branch release was requested.
