# HANDOFF — PS5 Retention Predictor, Phase 1 → next phases

Written 2026-10-03 at commit `db430eb` (plus this file), on the Windows laptop where everything so far was built and run.
> **Update (same day): the user cancelled the Mac move. All work continues on this Windows laptop.** §4 (Phase A) is kept only for reference and is NOT planned. Ignore Mac paths below; use `.venvs/<env>/Scripts/python.exe`.
>
> **Done since this file was first written (commit after `b5545e7`):**
> - F40 speech rate now uses aligned word times (pauses excluded): 188–236 WPM on the test video.
> - F52 filler density and F47 language-switch signals.
> - F58 `cold_open` span kind.
> - Near-exact quote snapping (recovered the 3:28 open loop).
> - UI rebuilt to the design system: bundled Inter, Source Serif 4 and Noto Sans Devanagari; sticky player with a full-width timeline (chapters, finding markers in lanes, combined risk, playhead, current chapter); findings filters; accept/undo/dismiss/restore; an **Edit plan** tab with text/CSV export; a pipeline status strip; and a dock.
> - The run API now returns the project title.
> - Still NOT built: Evaluation page, chat panel, transcript correction, paraphrase repetition, OCR.


> **Refocus (owner, 2026-10-03, later):**
> 1. **Vision is ON HOLD** and becomes a separate optional feature. Full honest record: [`docs/VISION_STATUS.md`](docs/VISION_STATUS.md). Two real A100 runs produced 1 valid clip answer out of 4; nothing from the VLM reaches the product.
> 2. **The #1 priority is the text-based retention predictor**, the core USP that is **not built yet**. Today's curve is an assumption-driven heuristic scenario, not a prediction.
> 3. **Next:** the full text pipeline (audio → transcript when no subtitles are supplied), stronger edit guidelines, all analytics, and a cleaner UI per the product spec the owner supplied (Projects / New analysis / Review / Edit plan / Evaluation / Settings).
>
> **Built since the last update:**
> - Review workspace on one shared selection model:
>   - video + transcript canvas (word follows playback, search, marker layers)
>   - full-width timeline with Retention / Risk / Findings / Shots / Speech / On-screen-text lanes and a hover readout
>   - findings list + five-question finding detail
>   - Shots filmstrip (shipped per-shot stills)
> - Edit plan page with conflicts, a duration/payoff shift, and the **hypothetical edit scenario** (RETENTION_MODEL §5: cuts transform the timeline; APV and AVD shown together; no winner)
> - Evaluation page (reviewer decisions per type, coverage, stage times, the unvalidated list)
> - Settings page (key status only, what is sent to Cerebras, models)
> - New analysis page (three start routes; three-state Colab handoff read from the real workspace; import from outputs/)
> - Projects cards with true pipeline state
>
> **Known gaps right now:**
> - **Script-only mode backend is NOT built.** The "I have a transcript/script" route previews and parses the file client-side, but `POST /projects/{id}/script` and the `analyze-script` CLI do not exist yet.
> - The vision runner's contiguous-label fix is unit-level only.

Read §0 and §3 before touching anything.

Reading order for the new machine:

1. This file.
2. `CLAUDE.md` (owner rules + gotchas).
3. `ARCHITECTURE.md` (pipeline, code map, decision log D16–D18, R*, N*, E-01…).
4. `PLANNER/` for the original specs. `PRD.md`, `TRD.md`, `RETENTION_MODEL.md` and `FEATURES.md` are the ones you'll need most.

---

## 0. One-paragraph truth

The local pipeline (media measurement → transcript → word alignment → Cerebras narrative → scoring → validated package → API → website) **works end to end on one real video** ("How MrBeast Solved YouTube", 14:10, English). The result is in the website as a **partial analysis**.

Three things are **not done**:
- **The visual (Qwen VLM on Colab) stage has never run on a real GPU.** The code path is tested on CPU with tiny random weights only.
- **OCR is shelved.**
- **Several P1 transcript features are not implemented** (§5).

The **UI is a functional skeleton, not a product UI** (§7). The retention curve is an **uncalibrated scenario** built on assumed numbers, not a prediction. Only **one English video** has ever been analysed; Hindi/Hinglish paths are untested on real content.

---

## 1. Owner rules (non-negotiable, from the user)

- **Never push to GitHub** unless the user explicitly asks. When pushing: **no `Co-Authored-By` line**.
- **Commits:** ≤100 words, past tense, human voice, author `Kawaljeet Singh Bharaj <kawaljeetsinghbharaj.jsb@gmail.com>`.
- **Cerebras API key:** only in git-ignored `.env`. Never print, log, commit or put it in a package.
- **Only VLM inference runs on Colab** (a different Google account). Everything else runs locally. **Never run Qwen locally.** On a 16 GB Mac, the 9B BF16 model (~19 GB of weights) cannot fit anyway.
- **One heavy local job at a time.** Running OCR and ASR concurrently crashed the Windows laptop.
- **Never call something "done" unless it was exercised end to end.** Say plainly what is untested.
- **Readable outputs go in `outputs/<slug>_<sha8>/`**, never in hidden folders.
- **After each major iteration:** update `CLAUDE.md`, `ARCHITECTURE.md` and memory.
- **Every edit suggestion must be checked against its original transcript text** (ARCHITECTURE E-01). The user rejected a rewrite that replaced 35 s of new material, including the transition to the next section, with one line.

---

## 2. What is DONE and verified (with evidence)

### 2.1 Real video run — workspace `5234018afef0e99a`

Source: `C:\Users\Hardeep singh\Downloads\vidssave.com How MrBeast Solved YouTube 1080P.mp4`. Data lives in `C:\Epoch\epoch-data\work\5234018afef0e99a` (1.8 GB, of which `stages/export` is 1.1 GB of superseded packages).

| Stage | Result | Time (Windows CPU) |
|---|---|---|
| probe | 850.208 s, 1920×1080, 24 fps CFR | 0.7 s |
| proxy | 720p MP4, used by the website player | 107 s |
| audio | −14.0 LUFS integrated, true peak **+1.5 dBFS**, 14 clipped windows, 0 waveform silences, 96.5 % speech (VAD) | 9 s |
| video_scan | 373 cuts, 374 shots (mean 2.27 s, longest 19.8 s), 1 black interval (13:21.9–13:22.7), 33 freeze/still intervals | 117 s |
| frames | 1566 PTS-exact JPEGs (1 fps grid + cut boundaries) | 160 s |
| asr | faster-whisper large-v3, CPU FP32, 217 segments, 4 checkpointed chunks, RTF 2.1–3.9 | 2452 s (41 min) |
| align | WhisperX wav2vec2: **207 segments, 2790/2790 words aligned** after the loop guard dropped 10 hallucinated segments (A-01) | 98 s |
| visual_job | `5234018afef0e99a_8f1941e177e44a81.visualjob.zip`, 49.7 MB, 43 clips, **built without transcript context** | 61 s |
| visual | **NOT RUN** (needs the Colab result) | — |
| ocr | **NOT RUN** (shelved, D18) | — |
| embed | multilingual-e5-base: 20 paragraphs, paragraph pairs + per-segment cosines + title relevance | 25 s |
| narrative | Cerebras `gpt-oss-120b`, strict JSON schema. Final: 6 candidates → 5 accepted, 1 dismissed, 0 unadjudicated | ~60 s (incl. one ~50 s rate-limit wait) |
| score | 171 bins of 5 s; central curve **not available** (coverage partial) | <1 s |
| export | `ac789d14_270676b4-21f9-595f-8bb3-a06d4a775fdd.retention.zip` (115.9 MB), `partial_analysis`, missing `visual`, `ocr` | 2 s |

**Final findings in the website** (run `270676b4`):

1. **Slow intro** 0:00–0:29.3, medium. *No safe edit proposed:* the model's rewrite failed the retention guard, so it was dropped.
2. **Audio clipping** 0:17–0:18, 1:14–1:17 and 1:28–1:31, medium. Fix: adjust audio. These come from measured clipping windows.
3. **Repetition** 5:45.3–6:08.6, low. The creator replays their own intro ("see if you can spot them in the hook to this video"), so it's very likely intentional. No safe edit proposed.
4. **Dismissed by the model:** the 0.8 s black frame at 13:21.9 (judged a transition).

**Title promise:** "How MrBeast Solved YouTube", fulfilled, with delivery from 0:29.3 and completion at 13:29.4. Hook at 0:07.7.

### 2.2 Code that is built and tested

- **Contracts** (`contracts/`): every P1 entity, deterministic IDs, and `validate_package`, which is shared by the exporter and the importer.
- **Stage runner:**
  - content-addressed fingerprints (code version + config + lock digest + dependency output digests)
  - `.partial` resume
  - journal
  - subprocesses at below-normal priority on Windows (no-op elsewhere)
- **Colab runtime** (`epoch_vlm/`) and notebook (`notebooks/epoch_visual_colab.ipynb`, generated by `scripts/build_notebook.py`):
  - stdlib preflight
  - hashed venv
  - sha256-verified model fetch at a pinned revision
  - qualification gate
  - OOM retry
  - stop rules
  - Drive checkpoints
  - ≤8 refinements
- **Narrative stage hardening, all from the real run** (ARCHITECTURE N-02…N-06, E-01, A-01, R-02):
  - Whisper loop guard
  - payoff = first delivery
  - quiet-only dead air
  - title-only obligations
  - Cerebras rate-limit waiting
  - per-candidate salvage
  - `finish` stops on a failed stage
  - lexical repetition with sentence-only edits
  - sentence-snapped edit boundaries
  - hook-safe intro edits
  - no audio cut for visual faults
  - outlier-gated tangents
  - rewrite content-retention ≥40 %
- **API** (FastAPI + SQLite, `apps/api/`): import with validation, staging and one transaction; idempotent by sha; runs, transcript, timeline, issues, evidence (incl. frames for visual signals), review PATCH, scenario POST (requires acknowledgement), artifacts with HTTP Range.
- **Website** (`apps/web/`, React 19 + Vite 7 + TS 5.9): see §7 for its state.

**Tests (all passing at handoff):**

| Env | Files | Count |
|---|---|---|
| media | `test_contracts.py`, `test_scoring_golden.py`, `test_pipeline_e2e.py`, `test_narrative_units.py` | 32 |
| api | `test_api.py` | 2 |
| vlmtest | `test_vlm_codepath.py` (Windows only, real 9B processor + tiny random model) | 2 |

### 2.3 Git

Commits so far:

```
db430eb Stopped edit suggestions from deleting content
97edd12 Added the review site and fixed issues found on the real video
b67c426 Built the Phase 1 local pipeline and Colab runner
```

Nothing has been pushed.

---

## 3. What is DUMMY, PLACEHOLDER, SHORTCUT or UNVERIFIED — be honest about these

| Item | Status | Where |
|---|---|---|
| Visual / VLM stage on real GPU | **Never run.** Only tiny-random-weights CPU test. Real VRAM, speed, and 9B JSON quality unknown; qualification gate exists to catch it. | `epoch_vlm/`, `tests/test_vlm_codepath.py` |
| Retention curve | **Uncalibrated scenario.** Baseline is *assumed* (80 % at 30 s, 45 % at end, κ=1). Not a prediction, not fitted to any real audience data. UI says so. | `pipeline/scoring/scenario.py` |
| Risk score 0–100 | **Ordinal heuristic**: severity weights 1/3, 2/3, 1; evidence weight 1.0 supported / 0.5 provisional; max per cause group. Not a probability. | `pipeline/scoring/risk.py` |
| Speech rate (F40, `rushed_delivery`) | **Shortcut:** words ÷ *segment* duration; aligned word times are NOT used (`speech_rates(chunks, {}, …)` always gets `{}`). Pauses inside segments dilute WPM. | `pipeline/reasoning/candidates.py:speech_rates`, called in `narrative.py` |
| OCR (F14/F15/F22) | **Shelved.** PaddleOCR code exists but was never completed on the real video (85 min CPU + crash). Text track coverage is a labelled substitute (VLM-observed windows). | `pipeline/text_vision/` |
| Fixture video + sample package | **Synthetic**: colour bars, generated tones, transcript "Sentence number N explains…". Its findings are artificial; use only for tests/UI smoke. | `scripts/make_fixtures.py`, `fixtures/generated/sample.retention.zip` |
| `FakeBackend` | Test-only VLM. Importer **rejects** FAKE results. | `epoch_vlm/backends.py` |
| "Prepare analysis" on website | **Does not analyse anything**: creates a project and shows the CLI command (by design, D01). No video upload. | `apps/web/src/pages/Projects.tsx`, `apps/api/main.py` analysis-request |
| Script-only mode (no video) | **Not built.** | — |
| Hindi / Hinglish | **Untested on real content.** Aligner `theainerd/Wav2Vec2-large-xlsr-hindi` downloaded and pinned; language hints exist; no real Hindi video run. | `pipeline/speech/` |
| Paraphrased repetition (same idea, new words) | **Out of scope** after E-01: embeddings scored same-topic and repeated sentences alike (~0.85), so only *lexical* repeats are flagged. | `candidates.py:repeated_run` |
| Tangent detection | Gated on e5 title-relevance outlier; on the test video it now produces none. Discrimination is weak (all paragraphs 0.81–0.89). | `candidates.py` tangent block |
| Model adjudication quality | First runs accepted 11/11 (0 dismissals). The final run dismissed 1/6. Only one video seen, so not established. | ARCHITECTURE N-06 |
| Chapter labels / hook / structure | Cerebras output, validated only for ids/quotes, not for editorial quality. | `narrative.py` |
| Frames hash mismatch after crash | Happened once; verifier rebuilt the stage; root cause unknown. | ARCHITECTURE §10 |
| Qwen3.5-0.8B in model cache | Downloaded, unused. Safe to delete. | `epoch-data/models/hf` |
| Lock files | **Windows x86_64 only** (`--python-platform x86_64-pc-windows-msvc`). Will NOT install on the Mac (§4). | `locks/*.txt` |
| Model manifests | Contain **absolute Windows paths** (`snapshot_dir`). Do not copy `epoch-data/models` to the Mac; re-download. | `epoch-data/models/manifests` |

---

## 4. PHASE A — Move to the MacBook M3 (16 GB)

### 4.1 Decide what travels

| Thing | Copy? | Why |
|---|---|---|
| Git repo (`C:\Epoch\epoch-`) | yes (git clone/copy) | code |
| `.env` | **re-create by hand** | contains the key; paths change |
| `epoch-data/work/5234018afef0e99a/` | **yes, needed for the Colab result** (skip `stages/export/*` old packages to save 1 GB) | `attach-visual` only accepts a result whose exact `stages/visual_job/<fp16>/` exists in the workspace (`pipeline/visual/attach.py:select_job_for_result`). Rebuilding on the Mac would produce a different job fingerprint (different locks → different digests), and the Colab result would be rejected as `unknown_job`. |
| `epoch-data/models/` (7.2 GB) | **no** | manifests hold Windows absolute paths; re-download with pinned revisions |
| `outputs/how-mrbeast-solved-youtube_5234018a/` | optional | readable copies only; includes the Colab job zip and the latest package |
| `epoch-data/app/` (website DB) | no | just re-import the package |

**Simplest safe alternative:** if the Windows laptop is still available, do the Colab run + `attach-visual` + `finish` **there** first, then move only the final `.retention.zip` to the Mac and import it.

### 4.2 Set up the Mac

```bash
# 1. tools
brew install uv            # or: curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.11
# Node 20+ for the website
brew install node

# 2. repo
cd ~/Epoch/epoch-          # wherever you put it
cp .env.example .env       # then edit .env (below)
```

`.env` on the Mac:

```
CEREBRAS_API_KEY=<paste — never commit>
CEREBRAS_BASE_URL=https://api.cerebras.ai/v1
CEREBRAS_MODEL=
EPOCH_DATA_DIR=/Users/<you>/Epoch/epoch-data
EPOCH_ASR_THREADS=4        # M3: 4 performance cores; start at 4, measure, maybe try 6
```

**3. Re-compile the locks for macOS arm64.** This is a required, deliberate change: it changes lock digests and therefore stage fingerprints. Generate Mac locks alongside the Windows ones; don't overwrite them. Then point `scripts/setup_envs.sh` (one line) at the platform-appropriate file.

```bash
for e in media asr api; do
  uv pip compile requirements/$e.in --python-version 3.11 \
     --python-platform aarch64-apple-darwin --generate-hashes -o locks/$e-macos.txt
done
```

Then edit `scripts/setup_envs.sh` to use `locks/$env-macos.txt` when `uname -s` is `Darwin`.

**4. Create the envs** (skip `ocr`; it's shelved):

```bash
bash scripts/setup_envs.sh media api asr
```

On the Mac, python lives at `.venvs/<env>/bin/python` (not `Scripts/python.exe`); the code already handles both.

**5. Download the models** (pinned revisions, sha-verified, ~7 GB):

```bash
.venvs/asr/bin/python scripts/setup_models.py asr align_en align_hi embed
```

**6. Check that ffmpeg ships for arm64:**

```bash
.venvs/media/bin/python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
```

**7. Run the tests:**

```bash
.venvs/media/bin/python -m pytest tests/test_contracts.py tests/test_scoring_golden.py tests/test_narrative_units.py tests/test_pipeline_e2e.py -q
.venvs/api/bin/python -m pytest tests/test_api.py -q
```

`test_vlm_codepath.py` needs the `vlmtest` env (Windows lock), so skip it on the Mac or compile a mac lock for `requirements/vlm.in` minus CUDA.

**8. Copy the workspace** into `$EPOCH_DATA_DIR/work/5234018afef0e99a/`, then:

```bash
.venvs/media/bin/python -m pipeline.cli status 5234018a
```

### 4.3 Expect on the Mac

- **Fingerprints change** because the lock digests change. **Do not run `analyze`** on the old video unless you want everything recomputed (ASR is the long one). `attach-visual` and `finish` resolve dependencies from `current.json`, so they should reuse the copied stages. **Verify with `status` before and after**; this path has not been exercised.
- **ASR speed on the M3 is unmeasured.** CTranslate2 runs on the CPU (no Metal). Expect the same order of magnitude as Windows, maybe faster. Measure on the 75 s fixture first: `python scripts/make_fixtures.py`, then `analyze` it.
- **RAM:** large-v3 FP32 ASR uses ~3–4 GB, and alignment ~1–2 GB. 16 GB is fine **if only one heavy stage runs at a time.** Close browsers or Docker during ASR.
- Windows-only code paths (below-normal priority, `Scripts/` paths in docstrings) are harmless on macOS. On a Mac, prefer running heavy stages under `nice -n 10`.

---

## 5. PHASE B — Colab visual run (the next real milestone)

Full guide: `COLAB_RUN.md`. Short version:

1. On the **Colab Google account**, upload `outputs/how-mrbeast-solved-youtube_5234018a/colab/5234018afef0e99a_8f1941e177e44a81.visualjob.zip` to Drive at `MyDrive/epoch/jobs/`.
2. Upload `notebooks/epoch_visual_colab.ipynb` to Colab and set the runtime to **A100** (High-RAM if offered).
3. Run cells 1→6, one at a time:

| Cell | Step | Time |
|---|---|---|
| 1 | Settings | instant |
| 2 | Preflight | ~1 min |
| 3 | Environment | 3–5 min |
| 4 | Model, ~19 GB, sha-verified | 3–8 min |
| 5 | Run (qualification + 43 clips + ≤8 refinements) | 20–45 min |
| 6 | Save to `MyDrive/epoch/results/` and download | ~1 min |

4. The file you get back is `5234018afef0e99a_8f1941e177e44a81.Q35-9B-BF16.visualresult.zip`.

### 5.1 What to watch for

| Output | Meaning | Action |
|---|---|---|
| `insufficient_gpu_memory` at cell 2 | got an L4/T4 | change the runtime to A100, re-run |
| `qualification PASSED: headroom X GiB, Y s/clip, est Z min` | good | let it run |
| `qualification FAILED` | 9B doesn't fit or leaks memory, or the JSON is bad | **don't retry blindly**; the zip downloads with the reason; read `qualification` in it |
| some clips `failed` | normal if a few | those windows become *visual unknown* (hatched in the UI) |
| >20 % clips failed / OOM twice | run stops on purpose | read `fatal_error.json`; likely a prompt/length issue |
| disconnect | Drive checkpoints | reconnect, run all cells again; finished clips are skipped |

**First real-GPU risks:**
- the 9B model's JSON compliance on the 768-token cap
- the true per-clip speed
- whether 32 frames at 448 px fit with headroom; the CPU test measured prompts of 5147–11851 tokens, all under the 12288 cap

**Note:** the job was built **without transcript context** (the transcript wasn't ready yet). The VLM can't relate speech to visuals in this run. A transcript-aware job can be built later with `analyze … --until visual_job`. That's a new job zip and a new Colab run; the old result stays valid for the old job.

---

## 6. PHASE C — Attach the visual result and finish

```bash
.venvs/media/bin/python -m pipeline.cli attach-visual 5234018a "<path>/…Q35-9B-BF16.visualresult.zip"
.venvs/media/bin/python -m pipeline.cli finish 5234018a
.venvs/media/bin/python -m pipeline.cli outputs 5234018a
# start the API and import the new package from outputs/…/package/
.venvs/api/bin/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8765
```

### 6.1 Expected changes in the results

- **`attach-visual`** re-validates every record. It rejects FAKE models, unpinned models, wrong jobs, and claims citing frames the model wasn't shown.
- **The narrative re-runs** (visual is a dependency) and costs ~1–2 min of Cerebras time, including rate-limit waits. Because it's an LLM, the findings may differ slightly from the current five.
- **New candidate types become possible:**
  - `visual_stagnation`: shots ≥15 s with low motion, **plus** VLM evidence. This video's longest shot is 19.8 s, so expect 0–2.
  - `technical_visual_fault` from VLM observations.
  - Visual evidence attached to existing findings: frames shown in the evidence panel.
  - Signals F13 (shot type), F36 (A/B-roll) and F37 (screen recording) appear.
  - P2 types (`visual_speech_mismatch`, `unreadable_text`, `visual_overload`, `weak_transition`) are **still excluded** (`P1_ISSUE_TYPES`).
- **Coverage:**
  - The visual track becomes "observed" on the cores of successful clips.
  - The text track becomes the VLM-observed windows, labelled "no OCR, D18".
- **Package kind:** OCR is not in `REQUIRED_VIDEO_STAGES`, so the package becomes **`analysis` (complete)** if `visual` completes.
- **Central retention curve** appears **only if every 5 s bin has full coverage on every track.** In practice that means **all 43 clips succeed and 0 candidates are unadjudicated.** One failed clip leaves a hatched gap, and only the lower/upper range is drawn. That's correct behaviour, not a bug.
- **Scenario numbers** (assumed average view duration / % viewed) stay **uncalibrated assumptions** whatever happens.

---

## 7. PHASE D — Website: honest state and what to build

**State:** a working but crude single-page review tool, about 670 lines.

**What works** (verified through DOM and network checks in the in-app browser, no console errors):
- project list and ZIP import with polling
- video player (720p proxy with Range requests)
- transcript with click-to-seek and active-line follow
- findings list (top 5 / all) with evidence expansion (transcript / signal / frames), suggestion cards (original vs proposed), and Accept / Dismiss (persisted)
- risk lanes per track, with hatched unknown regions and a playhead
- retention scenario with the assumptions confirmation gate → server recompute
- provenance / coverage tab
- missing-analysis banner

**Why it looks bad / what's missing** (the user called the UI "super shit"; agreed, it was built function-first per D13):

1. **No real design system applied.**
   - `PLANNER/UI_REFERENCE.md` / DesignDecisions "UI interpretation" specify tokens: bg `#0B0B0C`, canvas `#1C1C1E`, card `#242426`, text `#F5F2EE`/`#A9A5A0`, amber `#D98A1E`, coral `#FF7B7B`/`#E8506A`.
   - Fonts are specified as Inter / Source Serif 4 / Noto Sans Devanagari, **bundled locally** for offline use. **None are bundled**; it falls back to system fonts.
   - The glass/warm surfaces aren't implemented.
2. **Layout:**
   - The two-column grid is cramped.
   - Transcript and findings are short inner-scroll boxes.
   - Charts sit in a bottom tab and aren't visible while watching.
   - No sticky player, no keyboard shortcuts, no 44 px targets, no focus styling pass, no mobile check.
3. **Charts:**
   - SVG text is ~10 px and hard to read.
   - Findings aren't drawn as markers on the timeline.
   - No zoom/brush, no hover tooltips, no chapter band with readable labels.
   - Risk and retention aren't aligned to the same time axis under the video.
4. **Findings:**
   - no filter by type/track/severity
   - no grouping
   - the "no safe edit" state is plain text
   - Accept/Dismiss feed nothing: no edit plan, no export
5. **Missing views in the PRD/UI reference:**
   - **Edit plan** (accepted suggestions in order, with total time removed and export as a text/EDL/CSV list)
   - **Evaluation** page (VALIDATION metrics)
   - **compact dock** navigation (Projects / Review / Edit plan / Evaluation)
   - **chat panel** (opens beside the workspace and answers questions over the evidence ledger; must cite evidence ids, no new claims)
6. **Evidence:** frames show only for visual signals and observations. Transcript evidence doesn't highlight the quoted words in the transcript pane.
7. **Video upload / analysis start:** intentionally absent (D01). The UI should explain the manual flow better: a step indicator saying "local analysis done → Colab pending → attach".

**Recommended order:**
1. design tokens + bundled fonts
2. layout (sticky player, full-width synced timeline with issue markers)
3. findings filters + edit-plan view with export
4. chart readability + zoom
5. evaluation page
6. chat panel last

Keep the rules:
- never show a central curve without complete coverage
- the title "Estimated retention — uncalibrated scenario"
- risk and retention never merged into one score
- unknown is hatched, never green

---

## 8. PHASE E — Transcript NLP that is NOT done (the user is right that it's incomplete)

The features below come from `PLANNER/FEATURES.md`. The "P1" ones were in scope for Phase 1. Status reflects what code actually emits (`grep '"F[0-9][0-9]"' pipeline`).

| Feature | Planned (P1) | Status | Concrete next step |
|---|---|---|---|
| **F40 speech rate** | WPM over aligned speech | **Shortcut:** segment-based, words unused | pass `words_by_seg` (from `transcript.json` words with times) into `speech_rates`; compute WPM over voiced word spans; re-derive `rushed_delivery` thresholds from the per-video distribution |
| **F52 fillers** | language-aware lexicon + contextual check | **Not implemented** | lexicon for en (um, uh, like, you know, basically…) and hi (toh, matlab, yaani **only** when the LLM confirms filler use; see the SYSTEM prompt rule); per-minute rate signal; no issue unless dense |
| **F47 language switches** | ASR chunk hints + text analysis | only per-segment `language_hint`; **no signal emitted** | emit a switch-interval signal; use it to choose the Hindi aligner; needs a real Hinglish video |
| **F58 cold open** | structural + VLM context | **Not implemented** | add `cold_open` to the structure-pass spans; needs visual context (Phase C) |
| F53 viewer questions | rhetorical/direct questions | emitted via structure spans | validate quality on more videos |
| F54 open loops | tease → resolved/unresolved | emitted, but **the one real open loop was dropped** (inexact quote salvage) | allow fuzzy-to-exact quote snapping (find the closest exact substring) instead of dropping |
| F50 repetition | embeddings retrieve + LLM | **narrowed to lexical repeats only** (E-01) | add paraphrase detection only with a check that keeps edits non-destructive; consider sentence-level NLI rather than cosine |
| F51 tangent | topic relation + LLM | outlier-gated; produces nothing on the test video | needs labelled examples; reopen with more videos |
| F56 information density (P2) | claims/concepts per span | not built | — |
| F61 chapters | paragraph/topic segmentation | LLM labels per 20 paragraphs; boundaries = paragraph boundaries | sentence-level boundaries; YouTube-style chapter export |
| Transcript correction | versioned corrections (D12) | fields exist (`correction_revision`, `original_asr_text`); **no UI or flow** | edit-in-place in the transcript pane → new revision → re-run narrative |
| ASR quality | — | loop guard only | flag low-confidence segments (avg_logprob) in the UI; offer a re-decode of a region |
| Sentence segmentation | — | Whisper segments split sentences; edits snap via word punctuation only | proper sentence splitter over aligned words; use sentences as the unit for candidates and quotes |

**Cerebras notes:**
- The free tier hits HTTP 429 with `Retry-After` ≈ 50 s after ~5 calls/min. `PacedLLM` waits up to 120 s per wait and 300 s in total.
- The account offers `gpt-oss-120b` (selected) and `qwen-3.8-27b`.
- Prompt currently `prompts/narrative.v3.md`. Any byte change re-runs the narrative.

---

## 9. PHASE F — OCR (text on screen)

- **Current:** shelved. The text track uses the VLM-observed windows as a labelled substitute.
- **Options on the Mac, in order to evaluate:**
  1. **Apple Vision** (`VNRecognizeTextRequest`, via `ocrmac`/pyobjc). It runs on the Neural Engine and is likely fast. **Verify Devanagari/Hindi support before adopting**; it's not confirmed here.
  2. **RapidOCR** (ONNX PP-OCR models, CPU). Check that a Devanagari recognition model is available.
  3. **PaddleOCR**: existing code in `pipeline/text_vision/`; mac arm64 wheels exist; on Windows CPU it was too slow.
- **Acceptance:** <10 min CPU for a 15 min video, and pass `scripts/setup_ocr_models.py`'s bilingual probe. Then make `ocr` required again or keep it opt-in (D18 reopen trigger).

---

## 10. PHASE G — Validation (nothing in `PLANNER/VALIDATION.md` has been run yet)

- Only **1 real video** has run. The plan calls for 4–5 per category (tech_review, education), including Hindi/Hinglish.
- **Track per video:**
  - stage times
  - ASR loop drops
  - aligned-word %
  - candidates / accepted / dismissed / unadjudicated
  - **reviewer accept rate per issue type** (from Accept/Dismiss in the UI)
  - false-positive notes
  - VLM clip failure %
- **Model comparison policy:** six preselected clips, frozen rubric (DesignDecisions "Model comparison policy"). Not started.
- **Calibration of the retention scenario:** impossible without real audience-retention data from YouTube Studio. If the creator can export retention graphs for their own videos, that's the first real calibration source (D09).

---

## 11. Command cheat sheet (Mac paths)

```bash
# analyse a new video (local stages up to the Colab job)
.venvs/media/bin/python -m pipeline.cli analyze "/path/video.mp4" --title "Exact title" --category education --language en
.venvs/media/bin/python -m pipeline.cli status <sha8>
.venvs/media/bin/python -m pipeline.cli outputs <sha8>          # readable files + colab zip + package copy
.venvs/media/bin/python -m pipeline.cli attach-visual <sha8> <result.zip>
.venvs/media/bin/python -m pipeline.cli finish <sha8>            # embed -> narrative -> score -> export
# flags: --until <stage>, --force <stage...>, --retry-partial, --with-ocr (shelved), --allow-out-of-scope
# website
cd apps/web && npm ci && npx vite build && cd ../..
.venvs/api/bin/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8765   # serves apps/web/dist
# restart the API after any change in contracts/ (the running process keeps the old schema)
```

---

## 12. Gotchas learned the hard way

- **Whisper hallucinates repetition loops** (here, 3 loops / 10 segments, up to 417 words/s). The loop guard handles them. **Never** de-duplicate by text similarity, because that deletes genuine creator repetition.
- **A VAD "no speech" gap is not silence.** Played clips and music are loud. Dead air requires a quiet waveform (N-03).
- **LLMs pad title promises and cite final recaps as "fulfilment".** The payoff is timed from first delivery (N-02).
- **Sentence embeddings (e5) can't distinguish "same topic" from "repeated".** All paragraphs scored 0.81–0.89 against each other and the title.
- **A cached downstream stage silently uses the last *good* upstream output** if an upstream stage fails in this run. `finish` now stops (N-05).
- **Heredoc/sed edits corrupt `\n` escapes in Python sources;** use exact-string edit tools.
- **In-app browser screenshots are unreliable while a `<video>` plays.** Verify the UI via the DOM/JS.
- **Excel locks CSVs in `outputs/`;** the writer skips them with a notice.
