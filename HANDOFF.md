# HANDOFF — Epoch (PS5 Retention Predictor)

Rewritten 2026-10-03 on the Windows laptop where everything was built and run. The Mac move was cancelled; macOS setup instructions are in [README §3](README.md#3-run-it-on-a-mac-apple-silicon) (untested on a Mac).

**Reading order:**
1. This file.
2. [README.md](README.md): what every page shows, feature status, how to run.
3. [CLAUDE.md](CLAUDE.md): owner rules and gotchas.
4. [ARCHITECTURE.md](ARCHITECTURE.md): code map and decision log (A-, C-, E-, M-, N-, T-, X- entries).
5. `PLANNER/`: the original specs. PRD, FEATURES, RETENTION_MODEL and UI_REFERENCE matter most.

---

## 0. The truth in one paragraph

Epoch takes a 5–15 minute video and runs locally:
- media checks, loudness/clipping, cuts/black/freeze
- speech to text (faster-whisper large-v3, CPU) and word alignment
- a narrative pass on Cerebras (chapters, hook, title promises, findings with counter-explanations, edits validated never to drop content)
- a **rule-based, uncalibrated text retention model**
- transcript relations, and a grounded assistant with retrieval

The package is imported into a local website (FastAPI + React) with a Review workspace, edit plan, evaluation and settings. **Nothing has been compared with real audience retention.** Visual analysis is on hold (1/4 valid VLM answers). OCR is not run. Hindi/Hinglish has never been run end to end. Script-only analysis has no backend.

---

## 1. Owner rules (non-negotiable)
- **Pushing:** push to GitHub only when the owner asks. Commits are ≤100 words, past tense, human voice, author **Kawaljeet Singh Bharaj <kawaljeetsinghbharaj.jsb@gmail.com>**. **Never a Co-Authored-By line.**
- **The key:** the Cerebras key lives only in the git-ignored `.env`. Never echo, log, commit or package it.
- **Where things run:** everything runs locally except the VLM (Colab only). Never run Qwen on the laptop.
- **One heavy CPU job at a time;** the laptop crashed when OCR and ASR ran together.
- **Every edit suggestion must keep content:** no dropped points, examples, questions, transitions or announced replays (E-01, E-02).
- **Honesty:** say plainly what is untested. Never call something done unless it ran end to end.
- **Where outputs go:** readable outputs go in visible `outputs/<video>_<sha8>/` folders.
- **Docs:** update README, HANDOFF, ARCHITECTURE, CLAUDE.md and memory after every major iteration.

---

## 2. Done, with evidence

### 2.1 Real video run: "How MrBeast Solved YouTube" (850 s, workspace `5234018afef0e99a`)

| Stage | Result |
|---|---|
| probe / proxy / audio | −14.0 LUFS, +1.5 dBFS true peak; 14 one-second windows with 0.1–0.44% clipped samples |
| video_scan | cuts → shots; 1 black interval (13:21.9–13:22.7); per-shot motion, brightness, sharpness |
| asr | 217 segments, 4 chunks, about 41 min on CPU. The loop guard removed 3 Whisper repetition loops (A-01). Chunks 3–4 lost punctuation; fixed by A-03, full re-run **in progress** at the time of writing. |
| align | 2790/2790 words aligned |
| narrative | 5 accepted findings after validation (slow intro, 3 clipping, 1 black frame); repetition false positive removed (E-02) |
| predict | 501 s average watch (**58.9%**, band 57.0–60.5%), 42.9% at the end, 8 drop moments |
| export → import | run `cc4af68b` in the local site |

### 2.2 Code that exists and is tested
- **Pipeline** (`pipeline/`): content-addressed stages; `analyze`, `transcribe`, `attach-visual`, `finish`, `status`, `outputs` CLI.
- **Predictor** (`pipeline/predict/`): `features.py`, `model.py`, `stage.py`. 14 features (README §5).
- **Reasoning** (`pipeline/reasoning/`):
  - `narrative.py`: Cerebras pass, PacedLLM rate-limit handling, quote snapping, salvage
  - `candidates.py`: measured candidates; repetition rule; announced-replay guard
  - `transcript_signals.py`: speech rate, fillers, language switches, replay cues
  - `relations.py`: question→answer, abstract stretches, term dependency, load, rhythm
  - `rag.py`: BM25 over 3-segment passages
- **Scoring** (`pipeline/scoring/`): risk bins, findings-based scenario, hypothetical edit plan.
- **API** (`apps/api/main.py`):
  - import (validated, idempotent)
  - runs, transcript (+ `.srt/.vtt/.txt`), timeline, issues, evidence, review
  - scenarios, prediction (GET + recompute), relations, search, chat
  - hypothetical, evaluation, settings, pipeline state, local import
- **Website** (`apps/web/`): Projects, New analysis (4 steps), Review (At this moment, timeline, priority cards, 5 tabs, drawers), Edit plan, Evaluation, Settings. Every element is described in README §6.
- **Tests:** media env 49 passing (relations, predict, hypothetical, contracts, scoring golden, pipeline e2e, narrative units); api env 3 passing. Retrieval smoke test: `scripts/rag_eval.py` (hit@3 10/10 on 10 questions).

### 2.3 Git
- Pushed to `main` (owner-approved): `b7141bc`, `390af07`, plus this docs commit.
- The working branch is `kawal`; pushes go as `HEAD:main`.

---

## 3. Dummy, shortcut or unverified — read before trusting anything

| Item | Status |
|---|---|
| Retention numbers | Rule-based priors, **no audience data**. The band is a sensitivity range (weights ×0.5/×1.5), not a confidence interval. |
| Findings-based scenario (Method and data tab) | Older assumption-driven curve, kept only for comparison |
| Transcript relations "answer" | First later sentence reusing the question's words: a lexical pointer, not proof of a good answer |
| Assistant | LLM output. Quotes are verified and edit warnings come from fixed rules, but the advice itself can still be wrong. In testing it twice proposed cutting the hook or the quoted clip; the server warnings caught both. |
| Retrieval eval | 10 hand-written questions written after reading the transcript; a smoke test only |
| Clipping findings | Measured, **not verified audible** |
| Hindi / Hinglish | Never run. `mixed` forces Whisper Hindi + the Hindi aligner for the whole video. |
| Visual analysis | On hold; nothing from the VLM reaches the product |
| OCR | Stage code exists; not run; on-screen text shows "not inspected" |
| Script-only route | UI checks the file; **no backend** (`POST /projects/{id}/script` and `analyze-script` do not exist) |
| macOS | Instructions written, never run |
| Light-theme redesign | In progress at the time of writing (owner's latest direction) |

---

## 4. What to do next, in priority order

1. **Confirm the ASR fix (A-03)** from the end-to-end re-run. Compare punctuation coverage before (426 s unpunctuated) and after. Re-import and spot-check the relations tab after 7:43.
2. **Validate retention against reality.** Get YouTube Studio retention CSVs for 3–5 of the creator's videos and run them through the pipeline. Compare curves: correlation of drop positions, error in average % viewed. Then refit or adjust weights. Until then, keep every "uncalibrated" label.
3. **Transcript quality card and name hints:**
   - per-run punctuation coverage, low-confidence segments, alignment rate
   - pass names from the title to Whisper `hotwords` ("MrBeast")
   - add a word-error-rate script for when reference subtitles exist
4. **Script-only backend:**
   - `POST /projects/{id}/script` (save the text)
   - an `analyze-script` command
   - a `script` stage producing `transcript.json` (source user, segment precision, no words)
   - script branches through embed, narrative, predict and export (pace and dead-air features off)
5. **Feed transcript relations into the predictor:** long Q→A gaps as open loops, abstract stretches as low-novelty evidence. Then make relations a stage.
6. **Hindi / Hinglish:**
   - per-chunk language detection instead of forcing one language
   - per-segment aligner choice
   - keep each word in the script it was spoken in
   - test on 2–3 real clips
7. **Copy pass:** creator-native wording for honesty labels (README §8), a wordmark and an empty-state voice.
8. **Paraphrase repetition, `weak_transition`, prerequisite continuity (X06):** the P2 narrative features.
9. **Vision** (only if revived): native video models or schema-constrained decoding; see `docs/VISION_STATUS.md`.

---

## 5. How to run
See [README §2 (Windows)](README.md#2-run-it-on-windows) and [§3 (Mac)](README.md#3-run-it-on-a-mac-apple-silicon). In short:
- `analyze` → `finish` → build the site → run the API
- import the package from **New analysis** (or Projects → Import package)
- the API dev server for the in-app browser is in `C:\Epoch\.claude\launch.json` (name `api`, port 8765)
- restart the API after any change to `contracts/` or `apps/api/main.py`

---

## 6. Gotchas learned the hard way
- **Whisper failure modes:**
  - It hallucinates repetition loops. The loop guard handles them by speech rate; never de-duplicate by text similarity.
  - It drifts into unpunctuated lower case when conditioning on its own output over long chunks. Conditioning is now off (A-03). An initial prompt made it worse.
- **"No speech" is not silence:** dead air requires a quiet waveform (N-03).
- **LLM habits to guard against:**
  - padding title promises and citing the final recap as "payoff"; the payoff is timed from the first delivery (N-02)
  - calling limiter clipping "audible distortion" (N-07)
  - proposing to cut a hook question or a quoted clip; hence the server-side warnings (C-02)
- **Embeddings can't tell "same topic" from "repeated"** (all paragraphs scored about 0.85). Repetition is lexical (E-01).
- **Announced replays are examples, not padding** (E-02).
- **A cached downstream stage reuses the last good upstream output** if an upstream stage fails; `finish` stops at the first failure (N-05).
- **Bash heredocs turn `\b` into a backspace and mangle `\n`** in patched Python/TS. Use the Edit/Write tools or write patch scripts to files.
- **Browser pane:** while it is hidden, page JS timers are throttled (scripts with `setTimeout` hang); read the DOM synchronously. Screenshots are unreliable while a `<video>` plays.
- **The site's database is global:** IDs from cached stages can collide across runs. Scenario IDs are scoped per run (X-02).
- **Excel locks CSVs in `outputs/`;** the writer skips them with a notice.
- **On Windows,** PaddleOCR needs `enable_mkldnn=False`, and ctranslate2 needs `setuptools<81`.
