# Epoch — retention review for long-form video

Epoch reads a 5–15 minute video (or just its audio, or a script) and tells a creator **where viewers are likely to leave, why, and what to change without losing content**. Everything runs locally on a Windows laptop. The only cloud call is to Cerebras (`gpt-oss-120b`), for narrative structure and the assistant. Optional visual analysis runs on Colab and is currently **on hold** (see [docs/VISION_STATUS.md](docs/VISION_STATUS.md)).

> **Honesty first.** The retention numbers come from a **rule-based text model with no audience data** (uncalibrated). Every screen says so. Nothing here has been checked against a real YouTube retention curve yet. That is the first validation step (see *Validation* below).

- Status, next steps and dummies: [HANDOFF.md](HANDOFF.md)
- What was built and why: [ARCHITECTURE.md](ARCHITECTURE.md)
- Working rules: [CLAUDE.md](CLAUDE.md)

---

## Quick start

```bash
# 1. audio or video -> transcript only (SRT, VTT, TXT, word timings) when you have no subtitles
.venvs/media/Scripts/python.exe -m pipeline.cli transcribe "talk.mp3" --language en --allow-out-of-scope

# 2. full analysis of a video: local stages (probe, proxy, audio, scenes, frames, ASR, alignment)
.venvs/media/Scripts/python.exe -m pipeline.cli analyze "video.mp4" --title "Exact title" --category education --language en
# 3. narrative (Cerebras) -> text retention model -> scoring -> package
.venvs/media/Scripts/python.exe -m pipeline.cli finish <asset-prefix>

# 4. website (build once, then serve with the API)
cd apps/web && npx vite build && cd ../..
.venvs/api/Scripts/python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8765
# open http://127.0.0.1:8765 and import outputs/<video>/package/*.retention.zip from "New analysis"
```

- Put the Cerebras key in a git-ignored `.env` as `CEREBRAS_API_KEY=...`. It is never logged, packaged or shown.
- Readable outputs (CSV, TXT, JSON, SRT) land in `outputs/<video>_<sha8>/`.

---

## Pipeline

```
video/audio ─ probe ─ audio (loudness, clipping, silence) ─ ASR (faster-whisper, CPU) ─ alignment (wav2vec2, word times)
            └ proxy ─ scene scan (cuts, black, freeze) ─ frames ─ [visual job → Colab, ON HOLD]
                                      ↓
   embed → narrative (Cerebras: structure, promises, adjudicated findings + safe edits)
         → predict (text retention model) → score (risk bins, scenario) → export (.retention.zip)
                                      ↓
                 FastAPI + SQLite + React review site (local)
```

- Every stage is content-addressed: change code, config or a prompt and only its dependants recompute.
- A failed stage stops `finish`, so a stale package is never shipped.

---

## What the website shows, and how each number is made

The legend for every item below:
- **Source:** what the number is computed from.
- **Kind:** *measured* (software measurement), *model* (rule-based model), *LLM* (Cerebras, validated) or *assumption* (user-editable).

### Projects
Cards per video show the title, the real pipeline state and one next step. The state comes from the workspace and the outputs folder:
- not started
- running locally
- ready for Colab
- package ready
- imported

### New analysis
There are three start routes: a video, a transcript/script, or importing a finished package.
- Pipeline status is read from the real workspace.
- "Import from outputs/" copies a package into the site.
- ⚠ The script-only backend is **not built yet** (the page parses the file, but nothing processes it).

### Review: header summary
| Item | Meaning | Kind |
|---|---|---|
| predicted N% viewed (a–b%, uncalibrated) | Average percentage viewed from the text model. The range is the sensitivity band. | model |
| high/medium-priority findings | Count of open findings at those severities | LLM-adjudicated |
| earliest title payoff | First moment the title's promise starts being delivered | LLM, quote-checked |
| speech coverage | Share of the video with transcript evidence | measured |
| visual / on-screen text coverage | "not inspected" while vision and OCR are on hold. **Never shown as healthy.** | — |
| Transcript ↓ | Download the transcript as SRT, WebVTT or text with timestamps | measured |
| Ask about this video | Opens the grounded assistant (closed by default) | LLM |

### Review: video and transcript
- **Player:** a proxy of the source video. Every click anywhere seeks it, because the whole page shares one selection.
- **Transcript canvas:**
  - aligned words follow playback, and there is search
  - marker layers show findings, structure spans (hook, recap, CTA, open loop) and title promises
  - clicking a word seeks to it

### Review: timeline (full width)
| Lane | What it is | Kind |
|---|---|---|
| Chapters | LLM chapter labels and roles (cold open, setup, example, main, recap, CTA) | LLM |
| Predicted | The text model's predicted retention curve with its band. Hover: "still watching", "why viewers leave here" (top 2 causes) and "holding viewers" | model |
| Risk | Heuristic 0–100 risk per bin. The unknown share of a bin is **hatched**, never green. | measured + LLM |
| Findings | One marker per finding, coloured by severity, hatched if provisional | LLM |
| Shots | Measured shot boundaries; long, low-motion shots are tinted | measured |
| Speech | Where speech was detected | measured |
| On-screen text | "not inspected" (OCR off) | — |

### Review: findings and the five-question detail
- **Findings list:** ranked by severity, then evidence strength, then time. Each can be accepted, dismissed or restored.
- **Finding detail** answers five questions:
  1. What happened?
  2. Why might it matter?
  3. What is the evidence? (quotes, measurements and frames, each linked to its moment)
  4. What else could explain it? (the counter-explanation)
  5. What can I do? (the suggested edit, checked against the original text)

**Edit safety rules (ARCHITECTURE E-01, E-02):**
- No edit may drop new points, examples, questions or transitions.
- A rewrite must keep ≥40% of the original's content words, or no edit is offered at all.
- Repetition needs ≥2 consecutive sentences reusing earlier wording.
- A replay the speaker announces ("see if you can spot them in the hook…") is never treated as repetition.

### Lower tab: Predicted retention (the core feature)
**The model:** a proportional-hazards model over 1-second bins, `h(t) = h0(t)·exp(Σ wₖ·xₖ(t))`.
- **Baseline:** a neutral video keeps 80% at 30 s and 45% at the end. Both anchors are editable assumptions.
- **14 features**, each with its weight and rationale under "How this model works":

  | Feature | Effect | What it means |
  |---|---|---|
  | setup before the first point | raises leaving | measured from the hook end, never over the hook itself |
  | no hook yet | raises leaving | |
  | title payoff delayed | raises leaving | |
  | little new information | raises leaving | windowed novelty |
  | repeated wording | raises leaving | |
  | slower / faster than usual | raises leaving | speech rate vs the speaker's median, from word times |
  | filler words | raises leaving | |
  | dead air | raises leaving | waveform-quiet gaps only |
  | mid-video CTA / sponsor | raises leaving | |
  | outro | raises leaving | |
  | long sentences | raises leaving | |
  | open question | protects | |
  | concrete example | protects | |

- **Stats:** predicted average watch time, % viewed and % still watching at the end, each with a band, plus the assumed average video for comparison.
- **Chart:** the predicted curve (amber), sensitivity band (weights ×0.5 / ×1.5), the assumed average video (dashed) and numbered drop moments. Click anything to seek.
- **"Where viewers are predicted to leave, and why":** the 8 largest 10-second windows of loss beyond the average video. Each lists its causes with percentage shares, the quote at that moment, and any linked finding.
- **"What costs the most viewers overall":** loss beyond the average video, attributed to each feature (in points).
- **Assumptions:** change the anchors, tick "These are assumptions", then recompute. The features stay the same.

### Lower tab: Transcript relations (deterministic, no model)
- **Question → answer:**
  - every question the narrator asks, and the first later sentence that returns to its words
  - the gap, labelled as answered within 10 s, within a minute, open loop (over 1 min), framing (in the first minute, answered by the whole video) or never returned to in words
  - replayed questions are not counted twice
  - it's a pointer to check, not proof of a good answer
- **Abstract stretches:** 40 s or more with no number, example, named thing or "for example".
- **Explained after first use:** a named idea used before the sentence that defines it.
- **New ideas per minute:** cognitive load. Amber bars mark minutes over 1.5× the median, grey bars mark minutes under half. The first minute is never flagged.
- **Rhythm:** stretches of very even sentence lengths (monotone risk), and section lengths from the chapters.
- **Punctuation warning:** stretches of transcript without punctuation or casing are flagged, and sentence-based measures are switched off there. On the test video that is 426 s, from 7:42 on.

### Lower tabs: other views
- **Findings-based scenario:** the older risk-to-retention scenario, kept for comparison. It is an assumption-driven scenario, not a prediction.
- **Risk by track:** risk per track (speech, structure, technical, visual) with coverage-aware bounds.
- **Shots:** a filmstrip of measured shots with a still near each shot's middle. Visual notes appear only if the vision job ran.
- **What was analysed:** missing stages and why, model versions, code revision and stage status.

### Assistant ("Ask about this video")
- Answers **only** from this analysis: transcript, findings, text-model prediction and transcript relations.
- Every quoted line is **checked against the transcript** ("In transcript" / "Not found").
- Citations outside the video are dropped, and the drop is reported.
- An amber "Check before editing" callout flags any edit that would touch a question, the hook, a transition or a quoted clip.
- It says "Not measured in this analysis" for things it can't know (thumbnail colour, views).
- It sends transcript text to Cerebras.

### Edit plan
- Accepted suggestions become a queue, with conflicts marked next to the edits involved.
- **Hypothetical scenario:** accepted *cuts* transform the timeline and risk is recomputed. Average % viewed and average watch time are shown together, and no "winner" is declared.
- Exports to text and CSV.

### Evaluation
- Reviewer decisions per finding type.
- Coverage and stage times.
- The list of what has **not** been validated.

### Settings
- Key status only (never the key).
- What is sent to Cerebras.
- Models in use.

---

## Validation done so far (test video: "How MrBeast Solved YouTube", 14:10)

I checked the generated suggestions against the transcript and the audio measurements by hand:

| Suggestion | Verdict | Action taken |
|---|---|---|
| Cut 5:45–6:08 as repetition | **Wrong, destructive.** It is a replay the narrator announces ("See if you can spot them in the hook to this video"); the next passage analyses it. | Added the announced-replay rule (E-02); the finding and cut are gone |
| Slow intro 0:00–0:29 | **Partly right.** The hook (0:00–0:10) is strong; the cost is the credibility setup from 0:10 to 0:29. | The predictor's setup penalty now starts after the hook |
| Audio clipping at 0:17, 1:14, 1:28 ("audible distortion") | **Overclaimed.** 0.1–0.44% of samples hit full scale on a −14 LUFS master with a +1.5 dBFS true peak, which is typical limiter clipping and not proven audible. | Wording now says "not verified audible, listen to confirm" |
| Black frame 13:21.9–13:22.7 | **Plausible but likely intentional.** It falls on a spoken "…right but no" twist beat. | Kept as low severity, with that counter-explanation |
| Assistant: "replace the opening lines" | **Destructive.** It dropped the hook question. | Hook/setup structure is now in the assistant's context, plus server-side edit warnings |

After the fixes, the predictor gives average watch 501 s (**58.9%**, band 57.0–60.5%) and 42.9% at the end. The biggest drivers are setup before the first point and the missing early hook. All of this is still **uncalibrated**.

---

## Known limitations

- No real audience data. Weights are reasoned priors. The next step is to load YouTube Studio retention CSVs and fit or check them.
- Whisper lost punctuation and casing for half of the test transcript, which weakens sentence-level measures there.
- Script-only mode backend, OCR and transcript correction are not built.
- Vision (Qwen3.5-9B on Colab) is on hold: 1 valid answer out of 4 clips. See [docs/VISION_STATUS.md](docs/VISION_STATUS.md).
- ASR runs on CPU at about 1.8–2.9× real time on this laptop: a 14-minute video takes about 40 minutes.

## Tests

```bash
.venvs/media/Scripts/python.exe -m pytest tests/test_relations.py tests/test_predict.py tests/test_hypothetical.py tests/test_contracts.py tests/test_scoring_golden.py tests/test_pipeline_e2e.py tests/test_narrative_units.py
.venvs/api/Scripts/python.exe -m pytest tests/test_api.py
```
