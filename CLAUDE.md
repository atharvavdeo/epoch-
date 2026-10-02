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
- Test video: "How MrBeast Solved YouTube" (850 s), workspace `5234018afef0e99a` in `C:\Epoch\epoch-data\work`.
- Media, ASR (217 segments, 41 min CPU) and alignment (207 segments after the loop guard, 2790/2790 words aligned) are done locally. Colab job: `5234018afef0e99a_8f1941e177e44a81.visualjob.zip`. The user runs it on Colab; the result comes back via `attach-visual`, then `finish`.
- Narrative/score/export done (partial: visual + OCR missing). Imported run `270676b4` in the API at :8765 (`.claude/launch.json` at C:\Epoch). After the Colab result: `attach-visual`, then `finish`, then import the new package.
- Text retention predictor v1 (`pipeline/predict/`, uncalibrated) runs in `finish`; imported run `1cd55a87` shows it.
- Not built yet: script-only mode backend, RapidOCR, chat panel. Open question: the one-off frames hash mismatch after the crash.
