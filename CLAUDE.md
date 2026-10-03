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
- Not built: script-only backend, Hindi/Hinglish validation, OCR run, retention validation against real audience data. Light-theme UI redesign in progress.
