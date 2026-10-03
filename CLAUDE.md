# CLAUDE.md — working notes for this repo

PS5 Retention Predictor, Phase 1 (Diagnose). **Start with `HANDOFF.md`** (state, dummies, next phases on the Mac). Specs: `PLANNER/`. What was built and why: `ARCHITECTURE.md` (keep its pipeline diagram and decision log current after every major iteration).

## Rules from the owner
- Never push to GitHub unless asked. Commits: ≤100 words, past tense, human voice, author Kawaljeet Singh Bharaj. **No Co-Authored-By line, ever.**
- The Cerebras key lives only in git-ignored `.env`. Never echo, commit, log or package it.
- Only VLM inference runs on Colab (another laptop/account). Everything else runs locally. **Never run Qwen locally** except the tiny-random-weights code-path test.
- One heavy local job at a time (the laptop crashed from running OCR and ASR concurrently). Subprocesses run at below-normal priority, with `EPOCH_ASR_THREADS=6`.
- Don't call anything "done" unless it was exercised end to end. State plainly what is untested and why.
- Human-readable outputs go in `outputs/<slug>_<sha8>/`, never hidden folders.

## Commands
```bash
# local stages up to the Colab job
.venvs/media/Scripts/python.exe -m pipeline.cli analyze "<video>" --title "<exact title>" --category education --language en
.venvs/media/Scripts/python.exe -m pipeline.cli status <asset-prefix>
.venvs/media/Scripts/python.exe -m pipeline.cli outputs <asset-prefix>
.venvs/media/Scripts/python.exe -m pipeline.cli attach-visual <asset-prefix> <file.visualresult.zip>
.venvs/media/Scripts/python.exe -m pipeline.cli finish <asset-prefix>
# API + site (build the site first: cd apps/web && npx vite build)
.venvs/api/Scripts/python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8765
# tests
.venvs/media/Scripts/python.exe -m pytest tests/test_contracts.py tests/test_scoring_golden.py tests/test_pipeline_e2e.py
.venvs/api/Scripts/python.exe -m pytest tests/test_api.py
.venvs/vlmtest/Scripts/python.exe -m pytest tests/test_vlm_codepath.py
```
Rebuild the Colab notebook with `scripts/build_notebook.py`. Environments: `scripts/setup_envs.sh` (hashed uv locks, `UV_LINK_MODE=copy`).

## Gotchas
- Bash heredocs mangle `` in regexes (it becomes a backspace). Write patch scripts with the Write tool.
- Windows consoles are cp1252: the CLI reconfigures stdout to UTF-8. Keep it that way.
- On Windows, close `mkstemp` fds before reopening or unlinking.
- Excel locks CSVs: `outputs` skips locked files with a notice instead of failing.
- Stage outputs are content-addressed. Change a prompt, config or lock, and the dependants recompute. Don't hand-edit `stages/`.
- The job zip embeds `epoch_vlm/`. After editing it, rebuild the job (`analyze` re-runs `visual_job`) and tell the user to replace the zip on Drive.
- PaddleOCR on Windows needs `enable_mkldnn=False` (oneDNN PIR bug).
- faster-whisper can emit repetition loops. The align stage's `loop_guard` drops impossible-rate segments (ARCHITECTURE A-01). Never de-dup by text similarity.
- Every edit suggestion must be checked against its original text (ARCHITECTURE E-01). Never propose an edit that drops new points, examples, questions or transitions.
- Restart the API after any `contracts/` change (the running process keeps the old schema).
- Screenshots of the browser pane are unreliable while a `<video>` is playing. Verify the UI through the DOM/JS instead.

## Current state (2026-10-03)
- Status, priorities and what is unverified: `HANDOFF.md` §2–4. Every page and feature: `README.md`.
- Test video workspace `5234018afef0e99a` (C:\Epoch\epoch-data\work). Imported run `cc4af68b` (58.9% predicted, uncalibrated). An end-to-end re-run with the ASR fix (A-03) was started 2026-10-03; log `../epoch-data/logs/e2e_run.log`.
- Historical snapshot: superseded by the final browser integration below. Hindi/Hinglish and retention ground-truth validation remain open.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**This project has a knowledge graph. Start with the code-review-graph
MCP tools to narrow scope, then read the source.** The graph is cheaper than scanning files and
gives you structural context (callers, dependents, test coverage) that file search cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes_tool` or `query_graph_tool` instead of Grep
- **Understanding impact**: `get_impact_radius_tool` instead of manually tracing imports
- **Code review**: `detect_changes_tool` + `get_review_context_tool` instead of reading entire files
- **Finding relationships**: `query_graph_tool` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview_tool` + `list_communities_tool`

### Verify in the source

- Narrow scope with the graph, then read the source. Do not change code from graph output alone.
- For any non-trivial change, read the implementation and the relevant tests before concluding.
- Verify the exact source when touching behavior, database logic, migrations, retries, fallbacks,
  recovery, or compatibility code.
- When the graph and the source disagree, the source wins. The graph may be stale or may not
  model that relationship.
- An empty graph result can mean "not indexed" or "not statically visible", not "does not exist".

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes_tool` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context_tool` | Need source snippets for review — token-efficient |
| `get_impact_radius_tool` | Understanding blast radius of a change |
| `get_affected_flows_tool` | Finding which execution paths are impacted |
| `query_graph_tool` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes_tool` | Finding functions/classes by name or keyword |
| `get_architecture_overview_tool` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes_tool` for code review.
3. Use `get_affected_flows_tool` to understand impact.
4. Use `query_graph_tool` pattern="tests_for" to check coverage.
<!-- /code-review-graph MCP tools -->

## Verified Mac continuation (2026-10-03)
- Local run `5a80ca3b-788c-551f-bb5f-0a4cc2fc546b`, workspace `3dfd563a2bbae40c`: Ontology vs Metadata, 286 s. All local stages including OCR passed; visual inference was not run.
- 83 transcript segments, 858/858 words aligned, 37 shots, 355 OCR frames, 746 text tracks. Text prediction: 66.9% average viewed, 47.6% at end, 3 drop moments (uncalibrated). No candidate findings accepted.
- Outputs: 462 files, 137.2 MB. Exact package bytes retained by importer for repeatable downloads/re-imports. Export version 6 prevents OCR IDs colliding when the same text occurs at the same timestamp in different positions.
- Mac locks selected for stage fingerprints; platform-specific commands supplied to the UI. Run heavy commands with `nice -n 10` and six ASR threads.
- Final checks: media suite 49 passed, API suite 4 passed, OCR collision integration regression passed; website built; live assistant returned 3/3 verified quotes.


Current upgrade: HANDOFF.md Analysis and review upgrade (2026-10-03). New voice and Jev stages are optional diagnostics; text retention v2 remains candidate-driven/uncalibrated. Never label Jev confidence certainty, lexical callbacks semantic answers, pitch emotion, or scenario metrics audience analytics. Preserve the strict earlier-quotation/shorter-draft checks. Final run 09a2301a-4ebe-59c8-942b-5dc118b3d2d4.


## Final browser integration (2026-10-03)
- Kawal `3f954f4` integrated into `atharva-new-branch`. Browser video/audio uploads and pasted/file scripts now run, report progress, support cancellation and import validated packages.
- Final verification: 95 pipeline tests, 12 API tests, successful production web build; actual video, fresh audio and browser-script jobs completed. Details and run IDs: `docs/FINAL_INTEGRATION_2026-10-03.md`.
- Script timings are cues or estimates, never measured speech. Visual AI, retention calibration, editorial accuracy benchmarks and Hindi/Hinglish qualification remain outstanding. The serial worker is for one local API process; cloud narrative and optional Jev context are disclosed in Welcome and Settings.
