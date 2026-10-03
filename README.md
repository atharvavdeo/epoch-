# Epoch — retention review for long-form video

Epoch reads a 5–15 minute video (or just its audio) and shows a creator **where viewers are likely to leave, why, and what to change without losing content**.

- **Where it runs:** everything runs locally (Windows today, macOS instructions below).
- **The one cloud call:** Cerebras (`gpt-oss-120b`), for narrative structure and the assistant.
- **Visual analysis:** an optional Colab VLM. It is **on hold**; see [docs/VISION_STATUS.md](docs/VISION_STATUS.md).

> **Read this first.**
> - Every retention number comes from a **rule-based text model with no audience data**. It is *uncalibrated* and every screen says so.
> - Nothing has been compared with a real YouTube retention curve yet.
> - Visuals and on-screen text are **not inspected**. They always show as "not inspected", never as "fine".

**Docs map:**
- [HANDOFF.md](HANDOFF.md): status, what is left, how to continue.
- [ARCHITECTURE.md](ARCHITECTURE.md): pipeline, code map, decision log.
- [CLAUDE.md](CLAUDE.md): working rules.
- [PLANNER/](PLANNER/): the original specs.

---

## Contents
1. [Current status in one screen](#1-current-status-in-one-screen)
2. [Run it on Windows](#2-run-it-on-windows)
3. [Run it on a Mac](#3-run-it-on-a-mac-apple-silicon)
4. [Pipeline](#4-pipeline)
5. [What the retention prediction uses](#5-what-the-retention-prediction-uses)
6. [The website, page by page](#6-the-website-page-by-page) (every section, label, number and its layout)
7. [Visual system: fonts, colours, layout rules](#7-visual-system)
8. [Brand and UX critique](#8-brand-and-ux-critique-honest)
9. [Planner feature status](#9-planner-feature-status-done--partial--not-done) (every F/X feature from `PLANNER/FEATURES.md`)
10. [Validation done](#10-validation-done)
11. [Known limitations](#11-known-limitations)
12. [Tests](#12-tests)

---

## 1. Current status in one screen

| Area | State |
|---|---|
| Local media pipeline (probe, proxy, loudness/clipping, cuts/black/freeze, frames) | **Working**, run end to end on the test video |
| Speech to text (faster-whisper large-v3, CPU) + word alignment (wav2vec2) | **Working** for English. All 2790 words aligned. Punctuation drift fixed with `condition_on_previous_text=False` (A-03); re-verification on the full video is in progress. |
| Hindi / Hinglish | **Code paths exist, never run end to end** |
| Narrative pass (Cerebras): chapters, hook, promises, findings, safe edits | **Working**, with quote checking and edit-safety rules (E-01, E-02) |
| Text retention model (predictor v1) | **Working, uncalibrated.** Test video: 58.9% average viewed (band 57.0–60.5%) |
| Transcript relations (question → answer, abstract stretches, load, rhythm) | **Working** (deterministic) |
| Grounded assistant (RAG over transcript + findings + prediction) | **Working.** Quotes are verified and edit warnings are server-side. |
| `transcribe` command (audio/video → SRT/VTT/TXT) | **Working** |
| Website: Projects, New analysis (4 steps), Review, Edit plan, Evaluation, Settings | **Working** locally. A light-theme redesign is in progress. |
| Visual analysis (Qwen3.5-9B on Colab) | **On hold**: 1 valid answer out of 4 clips |
| OCR (on-screen text) | Stage exists (PaddleOCR, `--with-ocr`); **not run**, not in packages |
| Script-only analysis (transcript without media) | **Not built.** The UI checks the file and says so. |
| Validation against real audience retention | **Not done** |

---

## 2. Run it on Windows

**Prerequisites:**
- Python 3.11
- [uv](https://docs.astral.sh/uv/)
- Node 20+
- Git Bash
- About 15 GB free disk for models and the work folder

```bash
# 1. environments (hashed locks; media, api, asr, ocr)
bash scripts/setup_envs.sh media api asr
# 2. models (whisper large-v3, wav2vec2 aligners, embeddings) into ../epoch-data/models
.venvs/asr/Scripts/python.exe scripts/setup_models.py asr align_en align_hi embed
# 3. key for the narrative pass and assistant: create a git-ignored .env in the repo root
echo CEREBRAS_API_KEY=your-key-here > .env
# 4. analyse a video (local stages), then narrative + prediction + package
.venvs/media/Scripts/python.exe -m pipeline.cli analyze "C:\path\video.mp4" --title "Exact title" --category education --language en
.venvs/media/Scripts/python.exe -m pipeline.cli finish <first-8-chars-of-asset>
# 5. website
cd apps/web && npm install && npx vite build && cd ../..
.venvs/api/Scripts/python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8765
# open http://127.0.0.1:8765, then New analysis -> drop outputs/<video>/package/*.retention.zip
```

**Transcript only** (no subtitles? use this):
```bash
.venvs/media/Scripts/python.exe -m pipeline.cli transcribe "talk.mp3" --language en --allow-out-of-scope
# -> outputs/<name>/transcript.srt, transcript.vtt, 07_transcript.txt, 07_transcript_words.json
```

**Useful commands:**
- `pipeline.cli status <asset>` shows stage status.
- `pipeline.cli outputs <asset>` rewrites the readable CSV/TXT/JSON files.
- Everything lands in `outputs/<video>_<sha8>/`. Work files live in `../epoch-data/`; set `EPOCH_DATA_DIR` to move them.

---

## 3. Run it on a Mac (Apple Silicon)

The code is cross-platform. Interpreters are resolved as `.venvs/<env>/bin/python` when `Scripts/python.exe` does not exist. The **locks in `locks/` were compiled on Windows**, so on a Mac you compile your own from `requirements/*.in`.

```bash
brew install python@3.11 uv node git
cd epoch-
for env in media api asr; do
  uv venv --python 3.11 .venvs/$env
  uv pip compile requirements/$env.in -o locks/$env.mac.txt          # mac-specific lock (do not overwrite the Windows ones)
  uv pip sync --python .venvs/$env/bin/python locks/$env.mac.txt
  uv pip install --python .venvs/$env/bin/python --no-deps -e .
done
.venvs/asr/bin/python scripts/setup_models.py asr align_en align_hi embed
echo "CEREBRAS_API_KEY=your-key-here" > .env
echo "EPOCH_ASR_THREADS=8" >> .env                                    # M-series performance cores
.venvs/media/bin/python -m pipeline.cli analyze ~/Movies/video.mp4 --title "Exact title" --category education --language en
.venvs/media/bin/python -m pipeline.cli finish <asset8>
cd apps/web && npm install && npx vite build && cd ../..
.venvs/api/bin/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8765
```

**What to expect on a Mac:**
- **ffmpeg** comes from the `imageio-ffmpeg` wheel; no Homebrew ffmpeg is needed.
- **Speech to text** runs on the CPU. CTranslate2 has no Metal backend, and the pipeline pins FP32 (D16) for reproducibility. An M3 is roughly as fast as this Windows laptop or faster: plan for about 1–2.5× the video length.
- **Never run the Qwen VLM locally** (owner rule); Colab only.
- **Untested on a Mac:** nothing has been run on macOS yet. The likely friction points are `torch`/`torchaudio` wheel versions in `asr.in` and `soundfile`'s libsndfile (bundled in the wheel on arm64).

---

## 4. Pipeline

```
video/audio ─ probe ─ audio: loudness (EBU R128), clipping windows, silence, 16 kHz WAV
            ├ proxy (playback copy for the site)
            ├ video_scan: cuts → shots, black and frozen frames, per-shot motion/brightness/sharpness
            ├ frames (≈1 fps stills)
            ├ asr: faster-whisper large-v3 on CPU, VAD, 5-min chunks, loop guard (A-01), no self-conditioning (A-03)
            ├ align: wav2vec2 word timings (EN; HI model registered)
            └ visual_job → Colab (ON HOLD)
                     ↓  `finish`
  embed (sentence embeddings, retrieval only)
  → narrative (Cerebras): structure (hook, substance, chapters, spans, title promises), candidate findings from
    measurements, adjudication with counter-explanations, safe edits (E-01/E-02 validators, quote snapping)
  → predict: text retention model (rule-based, uncalibrated)
  → score: risk bins per track + findings-based scenario
  → export: validated *.retention.zip (manifest, JSONL data, proxy, stills)
                     ↓
  FastAPI + SQLite (import, review status, scenarios, chat, relations, retrieval) → React site (Vite)
```

- Every stage is **content-addressed**: a change in code version, config, prompt or lock recomputes only its dependants.
- A failed stage **stops** `finish` (N-05), so stale packages are never exported.

---

## 5. What the retention prediction uses

**The model:** proportional hazards over 1-second bins, `h(t) = h0(t) · exp(Σ wₖ · xₖ(t))`.
- `h0` is set so that an *assumed average video* keeps **80% at 30 s** and **45% at the end**. Both are editable assumptions.
- **Band:** every weight ×0.5 and ×1.5. This is a sensitivity range, not a confidence interval.

| Feature (weight) | Measured from | Meaning |
|---|---|---|
| Setup before the first point (0.6) | narrative structure | from the end of the hook to the first substantive point (never over the hook, M-03) |
| No hook yet (0.5) | narrative structure | before the opening question/claim lands |
| Title payoff delayed (0.5) | promise ledger | ramps up while the title's promise is still unpaid |
| Little new information (0.5) | transcript | 20 s window novelty below 0.6× the video's median for ≥10 s |
| Repeated wording (0.7) | transcript | ≥2 consecutive sentences reusing earlier wording; announced replays excluded (E-02) |
| Slower than usual (0.4) / faster than usual (0.3) | word timings | local words/min vs the speaker's own median |
| Filler words (0.3) | transcript | ≥2 true fillers ("um", "you know"…) in 20 s; Hindi discourse words never counted |
| Dead air (1.0) | waveform + VAD | quiet gaps only; loud clips are not dead air (N-03) |
| Mid-video CTA / sponsor (0.8) | narrative spans | subscribe/sponsor before the end |
| Outro (0.6) | narrative spans | closing section |
| Long sentences (0.2) | transcript | >30 words |
| Open question (−0.4) | narrative spans | holds viewers, decaying over 60 s |
| Concrete example (−0.2) | transcript | numbers, names, "for example" |

**Outputs:**
- the per-second curve with its band
- average watch time and % viewed, and % still watching at the end
- loss beyond the average video, attributed to each feature
- the 8 largest 10-second "drop moments", each with reasons, a quote and linked findings

**What the transcript is used for beyond the model:**
- chapters, hook, title promises and payoff (LLM, quote-checked)
- findings and safe edits
- transcript relations: Q→A gaps, abstract stretches, new ideas per minute, rhythm (displayed, **not yet fed into the model**)
- retrieval for the assistant

**Not used:** visuals, on-screen text, thumbnails, real audience data.

---

## 6. The website, page by page

**Global frame:**
- A centred content column: 1168 px on Review, 820 px for New analysis, 1480 px elsewhere.
- A floating **dock** at the bottom: Projects · Review · Edit plan · Evaluation · Settings · **+ New analysis**.
- **Hierarchy rule:** one primary (coral, becoming black in the new theme) action per screen. Amber (blue in the new theme) means *selected / worth inspecting*. Severity always appears as **word + dot**, never colour alone.
- **Hatched** means *not inspected*.

### 6.1 Projects (`/`)
1. **Header:** title "Projects", subtitle "Local analysis · evidence you can check · runs offline", and the primary button **+ New analysis** on the right.
2. **Empty state** (no projects): a card reading "Start with one video — Tell us the title it promises, run the local analysis, and land in Review", with **+ New analysis**.
3. **API down:** a banner showing the exact command to start the API.
4. **Project cards** (grid), each with:
   - a thumbnail (first shot still) or "no preview yet"
   - the title
   - a meta line: category · language · source kind · run count · last activity
   - one **status pill**: Waiting for local analysis / Local analysis in progress / Ready for Colab / Analysis package ready to import / Ready to review (· visual analysis incomplete)
   - buttons: **Open review**, Resume / Import package, Edit plan

### 6.2 New analysis (`/new`): four steps
A **stepper** at the top: Goal → Sources → Check → Process. Done steps show ✓ and future steps are disabled, with a tooltip saying why.
1. **Goal — "What does the video promise?"**
   - Fields: exact video title (required, explained: "a delayed payoff is judged against it"), intended audience (optional), category (Education / Tech review / Other), primary language (English / Hindi / Hinglish).
   - Primary action: **Continue**, which creates the project.
   - Escape hatch: "Already have a finished analysis package? Import it directly."
2. **Sources — "What do you have?"**
   - A large central **drop zone**: "Drop a file here, or click to choose", accepting video (MP4/MOV/MKV), audio (MP3/WAV/M4A…), transcript (SRT/VTT/TXT/MD) or a package (.zip). Hint: "No subtitles? Drop the video or audio: speech is transcribed locally".
   - Once a file is chosen, the zone collapses into a **file summary**: kind pill · name · size · duration (read by the browser) · Change.
   - Video/audio asks for the **full path** (browsers never reveal folders), with a "Copy as path" tip.
   - A package shows **Import result ZIP** (primary).
3. **Check:** a checklist with ✓ / ! / i rows:
   - title and source
   - out-of-scope length warning
   - what will run here
   - expected time (≈2–3× media length on CPU, computed for this file)
   - what is not analysed (visuals on hold, OCR off)
   - for transcripts: line, word and timing check plus a preview, and the honest "Script-only analysis is not built yet"
4. **Process:**
   - the exact command (`analyze` for video, `transcribe` for audio) with **Copy command**
   - live **pipeline status** for the project: Ready for Colab → Waiting for analysis package → Analysis imported, with the stage list while running
   - the Colab handoff box
   - **Import result ZIP** (primary) once a package exists

### 6.3 Review (`/runs/:id`): the main workspace
Top to bottom:
1. **Header:**
   - back ‹, then the video title (h1)
   - a sub-line: category · length · run selector · analysis completeness ("visuals not inspected" in accent)
   - on the right: **Ask about this video** (secondary) and **Open edit plan** (the screen's one primary action)
2. **Summary line** (three values only):
   - **N% estimated viewed** (uncalibrated)
   - **N findings to look at first**
   - **title payoff starts m:ss**
3. **Workspace row** (video ≈60% / panel ≈40%; stacks on narrow screens):
   - **Video player** (proxy). Every click elsewhere on the page seeks it.
   - **At this moment**: follows the playhead, top to bottom:
     - time and current chapter label
     - **Being said:** the current sentence, a "Next:" link, and an unpunctuated-ASR notice where relevant
     - **Predicted:** "N% still watching (band)", **Why viewers leave here** (top 2 causes) and **Holding viewers**, with an *uncalibrated* tag
     - **In the narration:** "A question is asked here · it is picked up at m:ss" / "a framing question: the whole video answers it" / "never returned to in words", and "No concrete example for N s here"
     - **Findings here:** severity dot · type · severity · time · **View evidence ›**. Empty state: "None at this moment. That only means nothing was flagged, not that it was all inspected."
     - **Ask about this moment** opens the assistant scoped to the selection
4. **Timeline** (full width). Lanes, top to bottom:
   - **Chapters:** LLM labels and roles
   - **Predicted:** curve + band. Hover shows still-watching, why viewers leave and what holds them.
   - **Risk:** heuristic 0–100 per bin; unknown share hatched
   - **Findings:** markers by severity; provisional ones hatched
   - **Shots:** measured; long low-motion shots tinted
   - **Speech:** VAD
   - **On-screen text:** "not inspected"

   It also has a playhead, the selected interval band, chapter names, and a hover tooltip.
5. **Look at these first:** three **priority cards** ranked by severity then evidence. Each card shows:
   - severity word + dot and a time chip
   - the finding type (title) and a three-line explanation
   - **View evidence**
   - "in edit plan" / "dismissed" status

   **See all N findings ›** opens the findings drawer.
6. **Tabs** (accent underline): Retention · Transcript · Transcript relations · Shots · Method and data.
   - **Retention:**
     - heading "Estimated retention" with an **Uncalibrated · rule-based text model** tag, and a switch **Estimated retention | Drop-off risk**
     - **one large chart**:
       - retention mode: curve, band, dashed average video, numbered markers for the top 5 drops, playhead, selected band
       - drop-off mode: share of current viewers leaving per second (5 s average) vs the average video
     - **three values:** average % viewed (band) · still watching at the end · average watch time (vs average video)
     - **Riskiest moments:** 5 ranked rows: number · time range · main reason (+ secondary) · before→after %
     - **Method and data** (collapsed):
       - what costs the most viewers (bars in points)
       - all 8 drop moments with quotes
       - assumptions (at 30 s / at the end, plus a "These are assumptions" checkbox gating **Recompute**, with the reason shown when disabled)
       - the "How this model works" table (feature · ×effect on leaving · rationale), notes and inputs used
   - **Transcript:** a wide reading column (max 860 px):
     - download buttons: SRT · VTT · TXT
     - search, and layer chips (Structure / Findings / Timing)
     - the current word follows playback; click a word to seek
     - markers for findings, structure spans and promises in a narrow rail
   - **Transcript relations:**
     - method note; the unpunctuated-transcript warning when relevant
     - four stats: questions asked · left open > 1 min · never returned to · % sentences with a concrete marker
     - **Question → answer** table (asked · question · returns to it · gap · meaning, plus shared words)
     - **Abstract stretches**
     - **Explained after first use**
     - **New ideas per minute** bar chart (dense / thin minutes flagged)
     - **Rhythm:** flat stretches and section lengths as proportional blocks
   - **Shots:**
     - horizontal **filmstrip**: neutral borders, accent on the selected tile, "·●" when a finding overlaps
     - a **shot inspector**:
       - "Shot N", time chip, length
       - large still
       - **Why this shot matters:** measured reasons, e.g. "over three times this video's typical shot", "among the stillest 10%", overlapping findings, or "Nothing measured stands out here. A long or static shot is not a problem by itself."
       - what was said over the shot
       - sub-tabs **Measurements** (boundaries, motion mean/max, brightness, sharpness, samples) and **Sampled frames & observations** (sampling note; "Not inspected: visual analysis is on hold")
   - **Method and data:**
     - **What was analysed:** not analysed + reasons, coverage, run, code revision, models, stages
     - **Export findings (CSV)**
     - **Risk by track** chart (hatched = not inspected)
     - **Findings-based scenario** (the older assumption curve, kept for comparison)
7. **Drawers** (right side, one at a time, closed by default, Esc closes):
   - **Evidence**, for one finding, shows five questions:
     - What happened?
     - Where? (time, track, compare-with interval, "Uninspected here: …")
     - What supports this? (quotes, measurements, frames, each seekable)
     - What might explain it? (counter-explanation)
     - What edit is proposed? (operation, the exact original text it removes or rewrites, the proposed text, the rationale, and "needs reanalysis"; or "No safe edit proposed …")

     Actions: **Add to edit plan** / Remove from plan · Dismiss / Restore.
   - **All findings:** filter chips (severity × status) and ranked rows.
   - **Assistant ("Ask about this video"):**
     - header "ASSISTANT · GROUNDED IN THIS ANALYSIS" and a note on what is sent to Cerebras
     - four starter questions
     - each answer shows:
       - the text
       - an amber **Check before editing** callout (an edit touching a question, the hook, a transition or a quoted clip)
       - **Quoted lines** rows with "✓ In transcript" / "✕ Not found" and seekable times
       - **Transcript passages retrieved** (BM25, matched words)
       - **Cited moments**

     Input box plus **Ask** (primary within the drawer).

### 6.4 Edit plan (`/runs/:id/plan`)
- **Header:** "Edit plan" and the video title.
- **Summary:** duration now → after cuts · title payoff now → after cuts · unresolved findings · visual coverage.
- **Conflict banner** when two accepted edits touch the same time.
- **Queue card:** accepted findings in timeline order; each edit shows its operation (Cut / Move / Rewrite / Add visual / Fix audio), time, original text and proposed text. **Download as text** · **Download CSV**.
- **Compare card:**
  - **Hypothetical** (assumed audience):
    - inputs: at 30 s / at end and "These are assumptions"
    - optionally assume some concerns are resolved (separate from review status)
    - **Compute hypothetical** gives a table: duration, assumed average watch time, % viewed, still watching at end — Current vs With this plan — plus what was removed and what is not modelled
  - **Reanalysed video:** make the edits, analyse the edited file as a new run, compare in the run selector.

### 6.5 Evaluation (`/evaluation`)
- **Not validated yet:** the server's honest list.
- **Reviewer decisions by finding type:** total · accepted · dismissed · not reviewed · precision so far.
- **Videos analysed:** video (link), kind (complete/partial + missing), length, coverage (speech / visual / text), findings (supported/accepted/dismissed), slowest stages.

### 6.6 Settings (`/settings`)
- **Creator defaults:** creator name, default category and language (stored in this browser, pre-filling New analysis).
- **Connections & storage:**
  - local data folder
  - Cerebras key status ("key configured" / "no key"; the key is never shown)
  - exactly what is sent to Cerebras
  - ASR CPU threads
  - local models with ✓/✗ and pinned revisions
  - the visual model note

---

## 7. Visual system

**Layout rules (current, kept in the redesign):**
- 8 px spacing rhythm: 8 between related items, 16 inside cards, 24 between groups, 32–48 between sections.
- Cards have a 20 px radius. Analytical rows are flat with dividers, never a card inside a card.
- Click targets are ≥44 px. Focus rings are a visible 2 px accent.
- Motion is ≤200 ms and only explains state changes (drawer, selection, tab).
- No pulsing badges. `prefers-reduced-motion` is respected.

**Fonts** (bundled locally for offline use via @fontsource):
- Source Serif 4: headings; the redesign uses it throughout.
- Inter: UI and data in the dark theme.
- Noto Sans Devanagari: the Hindi fallback.
- Tabular numerals for times and percentages.

**Type sizes:**
| Element | Size |
|---|---|
| Page heading | 28 px |
| Section heading | 20–22 px |
| Card heading | 16–18 px |
| Body / transcript | 15–16 px |
| Controls and chart labels | 13–14 px |

**Theme:**
- **Current (dark editorial):**
  - surfaces: background `#0B0B0C`, canvas `#1C1C1E`, cards `#242426`, hover `#2B2B2E`, inputs `#18181A`, borders `#3A3A3D`
  - text: `#F5F2EE` / `#A9A5A0` / `#85817D`
  - amber `#F2A93B` for selection, coral `#FF7B7B→#E8506A` for the one action, mint `#72C9A0` reserved for real observed data
- **In progress (owner direction, 2026-10-03):** a light theme with an off-white page, white cards, black primary buttons with a blue glow, black and blue charts, serif throughout, hover lift, and loading feedback (a top progress bar, button spinners and skeletons). This README section will be updated with the final tokens when it lands.

---

## 8. Brand and UX critique (honest)

What is wrong with the current look and copy, from a brand perspective. Some of it is fixed in the layout pass; the rest is the redesign's job.
- **The palette reads as heavy and generic.** Dark charcoal with amber and coral looks like a developer tool, not a creator studio. It is low-energy for a product whose promise is "make your video better".
- **Too many colours carry meaning.** Amber, coral, mint, red and grey all compete. The redesign narrows this to ink plus one blue accent, with red and ochre only for severity.
- **Text hierarchy was weak:** many 12–13 px grey "faint" lines, honest but tiring to read. The Review page now shows three summary values instead of six, but captions are still too frequent and too long.
- **The copy is engineer-voiced in places:** "provisional", "coverage", "uncalibrated scenario", "VAD". The honesty must stay, but the words should be creator-native (e.g. "rough estimate — not from your real audience"). Not yet rewritten.
- **No brand identity:** there is no logo, wordmark, product voice or empty-state illustration, and "Epoch" appears nowhere on screen except the browser tab.
- **Density:** before the layout pass, Review showed the video, transcript, timeline, findings list, finding detail and six tabs at once. It is now video + one panel + timeline + three cards, with the rest one click away. Still dense below the fold.
- **There was no loading feedback.** Clicks that call the API (import, recompute, ask) gave no immediate response. The redesign adds a progress bar, spinners and skeletons.

---

## 9. Planner feature status (done / partial / not done)

Source: [PLANNER/FEATURES.md](PLANNER/FEATURES.md). P1/P2/B are the planner's phases. "Done" means it runs in the pipeline and is visible or used; nothing visual has run in production.

**Measured video features:**
| ID | Feature | Status |
|---|---|---|
| F01 | Hard cuts | **Done**: `video_scan` cuts → shots |
| F02 | Dissolve/fade/wipe | Not done (P2) |
| F03 | Jump cuts | Not done (P2) |
| F04 | Shot length | **Done**: per-shot length, used in the shot inspector |
| F05 | Scene vs shot | Partial: chapters group by topic; shots kept separately |
| F06 | Black/blank | **Done**: blackdetect, `technical_visual_fault` |
| F07 | Freeze/static | **Done**: freeze filter + motion measurement |
| F08–F10, F12 | Zoom / pan / shake / speed ramp | Not done (P2/B) |
| F11 | Motion energy | **Done**: per-shot motion mean/max |
| F13 | Angle/shot type | On hold (VLM) |
| F14–F16, F20, F22 | Captions, title cards, lower thirds, progress cues, text density | Code exists (OCR stage), **not run** |
| F17–F19, F21, F29–F37 | Stickers, arrows, PIP, watermark, clutter, faces, A/B-roll, screen recording… | On hold (VLM) or B |
| F23 | Brightness | **Done**: per-shot luma |
| F24, F25 | Colour / colour jump | Not done |
| F26 | Blur | **Done** (proxy): Laplacian variance per shot |
| F27, F28 | VQA, saliency | B (not planned) |

**Audio and speech:**
| ID | Feature | Status |
|---|---|---|
| F38 | Speech presence | **Done**: Silero VAD |
| F39 | Silence | **Done**: waveform-quiet pauses (N-03) |
| F40 | Speech rate | **Done**: words/min from aligned words |
| F41 | Loudness/energy | **Done**: EBU R128 integrated/short-term, RMS |
| F42 | Pitch variation | Not done (P2) |
| F43–F45 | Music, sound effects, beat sync | B (not planned) |
| F46 | Audio quality | **Done** (clipping); noise proxy not done |
| F47 | Language switches | **Done** (signal); Hinglish untested |

**Narrative (transcript):**
| ID | Feature | Status |
|---|---|---|
| F48 | Hook | **Done** |
| F49 | Title payoff | **Done**: promise ledger, first delivery |
| F50 | Repetition | **Done**: lexical, ≥2 consecutive sentences; announced replays excluded. Paraphrase repetition not done. |
| F51 | Tangent | **Done**: relevance outlier + LLM |
| F52 | Fillers | **Done**: language-aware |
| F53 | Viewer questions | **Done**: plus the question→answer relation |
| F54 | Open loops | **Done** |
| F55 | CTA/sponsor | **Done** |
| F56 | Information density | Partial: windowed novelty in the predictor plus new ideas per minute |
| F57 | Sentiment words | B (not planned) |
| F58 | Cold open | **Done** |
| F59 | Greeting / time to substance | **Done** |
| F60 | Logo sting | Not done (needs visuals) |
| F61 | Chapters | **Done** |
| F62 | Sponsor section | **Done** (span kind) |
| F63 | Recap | **Done** (also suppresses repetition) |
| F64 | Outro | **Done** (transcript); visual end-card not done |

**Cross-cutting requirements:**
| ID | Feature | Status |
|---|---|---|
| X01 | Evidence coverage | **Done**: unknown is hatched, never healthy |
| X02 | Promise ledger | **Done** |
| X03 | Modality agreement | Not done (needs visuals/OCR) |
| X04 | Useful static visual | Partial: the shot inspector refuses to call long shots bad by themselves; no VLM check |
| X05 | Text dwell/occlusion | Not done (OCR) |
| X06 | Prerequisite continuity | Partial: E-01/E-02 edit validators and chat edit warnings; no entity-dependency check |
| X07 | Intro payoff timeline | **Done**: hook, first substance and payoff markers |
| X08 | Risk + retention | **Done**: risk bins + text retention model |
| X09 | Why not a problem | **Done**: counter-explanations, dismissed candidates |
| X10 | Action plan / before-after | Partial: edit plan + hypothetical; the reanalysed comparison is manual (new run) |
| X11 | Grounded chat | **Done**: RAG, verified quotes, citations |
| X12 | Resumable package loop | **Done**: checkpoints, import/export, lineage |
| X13 | Evaluation and provenance | Partial: Evaluation page; no authentic metric overlay, no labelled set |

**Issue types in use:**
- `slow_intro`, `delayed_payoff`, `unnecessary_repetition`, `tangent`, `unresolved_promise`, `dead_air`, `rushed_delivery`, `technical_audio_fault`, `technical_visual_fault`, `disruptive_cta`
- `visual_stagnation` is on hold
- `weak_transition`, `visual_speech_mismatch`, `unreadable_text`, `visual_overload` are not done (P2)

---

## 10. Validation done

**Suggestions audit** (test video "How MrBeast Solved YouTube", 14:10):
| Suggestion | Verdict | Action |
|---|---|---|
| Cut 5:45–6:08 as repetition | Wrong, destructive: an announced replay that the next minute analyses | E-02 rule; the cut is gone |
| Slow intro 0:00–0:29 | Partly right: the hook is strong, the setup costs | Setup penalty starts after the hook (M-03) |
| Clipping "audible distortion" | Overclaimed: 0.1–0.44% clipped samples on a −14 LUFS master | "Not verified audible" (N-07) |
| Black frame at 13:22 | Plausible but likely an intentional beat | Low severity, counter-explanation kept |
| Assistant: "replace the opening lines" | Destructive: it dropped the hook question | Hook/setup context + edit warnings (C-02) |

**Transcription quality** (no reference subtitles, so no word error rate yet):
- Median segment log-probability −0.115; 0/217 segments below −0.5; 8 temperature fallbacks; 3 repetition loops removed.
- 2790/2790 words aligned.
- **Defect:** 426 s with no punctuation or casing (chunks 3–4).
- **Experiment** on the same 90 s: shipped settings gave 46 punctuated words; an initial prompt gave 21 (worse); no self-conditioning gave 46 and ran faster.
- **Fix:** A-03. Full-video re-run in progress.

**Retrieval** (`scripts/rag_eval.py`):
- 10 hand-written questions: hit@3 **10/10**, hit@1 **8/10**.
- This is a small set written after reading the transcript, so it is a smoke test, not a benchmark.

---

## 11. Known limitations
- **Retention:** the weights are reasoned priors with no audience data. The next step is to compare with YouTube Studio retention exports for 3–5 videos.
- **Visual analysis** is on hold; OCR is not run.
- **Hindi and Hinglish** have never been run end to end. `mixed` forces Whisper's Hindi mode and the Hindi aligner for the whole video, which is wrong for English words in Hinglish.
- **Script-only analysis** has no backend.
- **ASR on CPU** takes about 40 minutes for a 14-minute video.
- **Chat** depends on Cerebras rate limits (free tier ~50 s Retry-After).
- **macOS** is untested.

## 12. Tests
```bash
.venvs/media/Scripts/python.exe -m pytest tests/test_relations.py tests/test_predict.py tests/test_hypothetical.py tests/test_contracts.py tests/test_scoring_golden.py tests/test_pipeline_e2e.py tests/test_narrative_units.py
.venvs/api/Scripts/python.exe -m pytest tests/test_api.py
.venvs/media/Scripts/python.exe scripts/rag_eval.py ../epoch-data/validation/mrbeast_transcript.json   # third-party transcript, not in git
```
