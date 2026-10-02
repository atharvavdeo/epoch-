# Architecture — Phase 1 (Diagnose)

The authoritative specifications live in `PLANNER/` (PRD, TRD, Schema, RETENTION_MODEL, COLAB_RUNBOOK). This file describes what was **built**, how data moves through it, and every implementation decision that the planner didn't fix. Each decision is phrased so it can be challenged: *why X rather than Y, and what evidence would reopen it*.

## 1. End-to-end flow

```
                         ┌──────────────────────── this laptop (CPU) ───────────────────────┐
 video.mp4 ──► analyze ─► probe ─► proxy ─► audio ─► video_scan ─► frames ─► asr ─► align ─► visual_job
                         │  (media env)                                     (asr env)        │ *.visualjob.zip
                         └──────────────────────────────────────────────────────────────────┘      │
                                                                                                    ▼
                         ┌────────────── Google Colab (A100, other account) ──────────────┐   Drive upload
                         │ notebooks/epoch_visual_colab.ipynb                               │
                         │  preflight → hashed venv (vlm lock) → pinned snapshot fetch →    │
                         │  epoch_vlm.runner: qualify → 20 s clips → JSON → refinements     │
                         └──────────────────────────────────────── *.visualresult.zip ──────┘
                                                                                                    │
 attach-visual ◄────────────────────────────────────────────────────────────────────────────────────┘
      │ (re-validates every record; rejects FAKE/unpinned models)
      ▼
 finish ─► embed (asr env) ─► narrative (Cerebras, strict JSON) ─► score ─► export ─► <asset>.retention.zip
                                                                                         │
 outputs ─► outputs/<slug>_<sha8>/ (CSV/TXT/JSON, proxy, colab zip, package copy)         │
                                                                                         ▼
                                   FastAPI importer (validate → staging → one SQLite txn) ─► React review site
```

Commands (all via `.venvs/media/Scripts/python.exe -m pipeline.cli`): `analyze`, `status`, `outputs`, `attach-visual`, `finish`. The API runs as `.venvs/api/Scripts/python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8765` and serves the built site from `apps/web/dist`.

## 2. Code map

| Path | Role |
|---|---|
| `contracts/` | Pydantic entities (extra=forbid), deterministic IDs (`det_uuid`, `evidence_id`), canonical JSON, fingerprints, and `validate_package`, shared by the exporter **and** the importer. |
| `pipeline/orchestration/` | Settings (.env), workspace layout, content-addressed stage runner, subprocess launcher (below-normal priority), stage graph. |
| `pipeline/media/` | ffmpeg/PyAV measurements: probe, 720p proxy, loudness/clipping/silence/VAD, cuts/black/freeze, PTS-exact frames. |
| `pipeline/speech/` | Chunked, checkpointed faster-whisper ASR (CPU FP32) and WhisperX alignment. |
| `pipeline/text_vision/` | PaddleOCR text tracks. **Opt-in only** (D18). |
| `pipeline/visual/` | Builds the Colab job (clip plan, frames, prompt, runtime, lock) and imports the result. |
| `epoch_vlm/` | Self-contained Colab runtime shipped inside the job zip (stdlib preflight, hashed fetch, Qwen backend, runner). |
| `pipeline/reasoning/` | Transcript chunks + embeddings, Cerebras client, candidate/evidence book, narrative stage. |
| `pipeline/scoring/` | RETENTION_MODEL formulas: risk bins, coverage bounds, survival scenario, exact AVD. |
| `pipeline/package_export.py` | Assembles and self-validates the immutable `.retention.zip`. |
| `pipeline/outputs.py` | Human-readable copies in `outputs/` (not hidden). |
| `apps/api/` | SQLite schema, importer, REST API under `/api/v1`. |
| `apps/web/` | React 19 + Vite review UI: player, transcript, findings, risk lanes, retention scenario, provenance. |
| `prompts/` | Versioned VLM and narrative prompts (part of the stage fingerprints). |
| `locks/`, `requirements/` | Hashed uv locks per isolated environment. |

## 3. Stage runner contract

* Each stage writes to `work/<asset16>/stages/<name>/<fp16>/`. Its fingerprint = stage name + version + schema version + config + extra inputs + lock digest + the output digests of its dependencies. Changing any of these produces a new directory, and the old output is never mutated.
* Work happens in `<fp16>.partial/`, which is atomically renamed on success. Unit-level checkpoints (ASR chunks, VLM clips) survive crashes, so `--retry-partial` resumes from them.
* `current.json` points at the accepted output, and `journal.jsonl` records every attempt.
* Heavy stages run in their own interpreter (`run_subprocess`, `BELOW_NORMAL_PRIORITY_CLASS`), so process exit frees RAM/VRAM and the laptop stays responsive.

## 4. Environments

| env | key pins | used by |
|---|---|---|
| media | av 15.1, scenedetect 0.7.1, opencv 4.11, imageio-ffmpeg 0.6 (ffmpeg 7.1), httpx, pydantic 2.12.5 | CLI, media, visual job/import, reasoning (HTTP), scoring, export |
| asr | torch 2.8 CPU, whisperx 3.8.6, faster-whisper 1.2.1, ctranslate2 4.6, transformers 4.57.6, sentence-transformers 5.1.2, setuptools<81 | asr, align, embed |
| ocr | paddle 3.3.1, paddleocr 3.7 | ocr (opt-in) |
| api | fastapi 0.135.1, sqlalchemy 2.0.48, uvicorn | importer + API |
| vlm | torch 2.8 cu126, transformers 5.7.0, hub 1.5, accelerate 1.10.1 (linux) | Colab only |
| vlmtest | Windows twin of vlm + pytest | `tests/test_vlm_codepath.py` |

## 5. Data invariants

* **Time zero** = container start (ffmpeg origin), and all intervals are half-open `[start_ms, end_ms)`. Frames are addressed by exact PTS, never `index / avg_fps`.
* IDs are UUIDv5 over stable keys, so re-running identical inputs yields identical records and identical package bytes.
* Evidence is a ledger. Issues reference `E##` evidence and never invent times. The narrative LLM picks among candidate intervals (`O#` options) that the pipeline computed, and quotes must be exact transcript substrings.
* Missing analysis is **unknown**, not healthy. Coverage records drive the lower/upper risk bounds, and the scenario shows a central curve only when coverage is complete.

## 6. Visual stage (Colab)

* Clips are 20 s with ±2 s of context, carrying ≤32 frames at 448 px. A final tail shorter than 2 s merges into the previous clip. The input token cap is 12288, max_new_tokens is 768, decoding is greedy, and `enable_thinking=False`.
* Failure policy:
  * one JSON repair
  * on OOM, retry at half the frames and a 6144-token cap
  * stop if >20% of clips fail or OOM happens twice
* **Qualification before the run:** a worst-case clip, then 3 warm repeats checking for memory leaks, requiring ≥2 GiB of headroom. A placement verifier aborts if any parameter is off-device or if <90% of parameters are bf16. FP32 parameters are recorded.
* Checkpoints are mirrored to Drive after every clip, so a disconnected runtime resumes.
* Measured on the real 9B processor (CPU test, tiny random weights): prompt tokens min 5147 / median 5782 / max 11851, all under the 12288 cap.
* Not testable without an A100: real weight load time, true VRAM, and 9B JSON quality. Qualification gates exactly these, on the first minutes of the Colab run.

## 7. Reasoning and scoring

* Cerebras via `httpx`. A probe selects the model (currently `gpt-oss-120b`). Output uses a strict `json_schema`, gets 2 retries within a 45 s deadline, and is never retried on 401/403. The key lives only in `.env`.
* Two passes:
  1. Structure: chapters, hook, first substance, title promises.
  2. Adjudication of pre-built candidates: accept or reject, with severity, explanation, counter-explanation and suggestions.
* Validators drop anything citing unknown evidence or non-substring quotes.
* Scoring follows `PLANNER/RETENTION_MODEL.md`: 5 s bins; severity × evidence weight × overlap; the max per cause group/track; coverage-bounded combination; a survival hazard against an assumed baseline; exact AVD integration. Golden fixtures pin the numbers.

## 8. Package and website

* The exporter writes `manifest.json` plus JSONL tables plus the proxy/frames, then runs `validate_package` on its own output.
* The importer runs the same validator, then:
  * unpacks into staging
  * renames into place
  * inserts in one transaction
* Duplicate bytes return the existing run. The same run_id with different bytes is rejected.
* The site never computes diagnostics. It renders what the package says, and the only server-side recompute is the scenario, which requires the acknowledged assumptions.

## 9. Decision log (implementation-level)

Planner decisions D01–D15 are in `PLANNER/DesignDecisions.md`, which also carries D16–D18 below.

| ID | Decision | Why not the alternative? | Reopen if… |
|---|---|---|---|
| D16 | Everything except the VLM runs on this laptop. Colab does only visual inference. | Colab sessions are ephemeral and on another account; moving ASR there would double the fragile surface. CPU FP32 ASR is slow (RTF ≈2–3.5) but deterministic and resumable. | A video >15 min makes local ASR exceed ~1 h, or a local GPU becomes available. |
| D17 | Default VLM profile is Qwen3.5-9B BF16; 27B only by explicit opt-in. | 27B BF16 needs ~54 GB of weights plus activations; on a 40 GB A100 it can't run unquantized, and quantization violates D05. 9B leaves headroom for 32-frame clips. | Colab reliably allocates 80 GB A100/H100 **and** the 9B fails the frozen clip rubric. |
| D18 | OCR is opt-in (`--with-ocr`). Without it, the text track's coverage is limited to VLM-observed windows and labelled as such. | CPU PaddleOCR took ~85 min/video and, run alongside Whisper, exhausted RAM and crashed the laptop. The GPU Paddle index was unreachable. | A faster OCR (e.g. RapidOCR/ONNX) meets <10 min on CPU, verified on the bilingual probe. |
| R1 | The media lock pins one opencv distribution. | Two opencv wheels overwrite each other's `cv2` and break silently. | — |
| R2 | The asr env pins `setuptools<81`. | ctranslate2 imports `pkg_resources`, which setuptools 81 removed. | ctranslate2 drops the import. |
| R-01 | `Artifact.bytes ≥ 0` (was > 0). | An honest empty JSONL (e.g. no aligned words) is valid output; forcing >0 would make the exporter lie or fail. | — |
| P-01 | Placement verifier: abort if any param is off-device or <90% bf16; record FP32 params instead of aborting on them. | Qwen keeps some norms/rotary buffers in FP32 by design. Aborting on any FP32 param rejected a correct model, and ignoring it would hide CPU offload. | A model legitimately needs >10% non-bf16 params. |
| T-01 | Time zero = container start, not first video PTS. | Audio and video can start at different PTS. One origin keeps transcript and frames aligned. | — |
| C-01 | A final clip tail <2 s merges into the previous clip; longer tails stay a shortened clip. | A sub-2 s clip has 1–2 frames, too little for any visual claim, yet still costs a full model call. Merging longer tails would push clips past the 20 s/32-frame budget. | Clip-level recall drops at video ends. |
| N-01 | An `unresolved_promise` interval spans from the promise's setup to the end of the video; evidence = the setup window + the final 60 s; the suggested fix rewrites the closing chunk. | Absence has no single timestamp. The honest claim is "from here on, this was never paid", and the ending is where the fix belongs. | Reviewers find the long interval inflates risk across the whole video. |
| S-01 | Technical-track coverage = 1.0 when both the decode/visual checks and the waveform checks ran, 0.5 when audio is missing. | Half-measured is neither unknown nor complete; a half weight keeps the bounds honest instead of claiming the track is clean. | Per-detector coverage becomes available. |
| X-01 | `run_id = det_uuid("run", export fingerprint)`. | Same inputs → same run, so re-imports are idempotent. Different inputs → a new run, never an overwrite. | — |
| N-02 | Payoff time = first paragraph that delivers on a title promise (partial or full), not the final summary. Same-type, same-interval candidates merge into one. | The first real run flagged "payoff at 13:29" three times because the LLM cited the closing recap as fulfilment. | Reviewers see real late payoffs being missed. |
| N-03 | A no-speech gap is dead air only if ≥60% of its RMS windows are below max(−45 dBFS, speech median − 20 dB). | A 25 s played clip at speech loudness was reported as "dead air". | Quiet-but-intentional beats get missed. |
| N-04 | Cerebras 429s are waited out at stage level (≤120 s each, ≤300 s total); the per-call 45 s deadline is unchanged. Invalid candidates/spans are salvaged per item, not per batch. | Free-tier Retry-After was ~50 s; one bad quote had discarded 4 batch-mates. | Paid tier removes the limits. |
| N-05 | `finish` stops at the first failed stage. | Later stages would otherwise reuse the failed stage's last *good* output and present a stale package as current. | — |
| N-06 | Narrative prompt v2: title obligations come from the title words alone; visuals described only as far as the evidence states. Open reopen trigger: the adjudicator accepted 11/11 candidates (0 dismissals) on the test video. | v1 invented a "step-by-step guide" promise and claimed "no visual information" without visual evidence. | Dismiss rate stays at 0 across videos, which means adjudication isn't discriminating. |
| W-01 | Website risk lanes hatch the unknown fraction of each bin instead of colouring it green. | A track with no evidence must not look healthy (PRD). | — |
| A-01 | Before alignment, drop ASR segments with >10 words/s over ≥6 words (Whisper repetition loops). Each drop is listed in `transcript.json → dropped_segments` and `outputs/…/07_transcript_dropped.csv`. Repeated text at a normal rate is **never** dropped. | On the test video, faster-whisper emitted 3 loops (10 segments, up to 417 words/s). Real speech measured 3.6 words/s median, 4.8 at p90. Left in, the loops would surface as a false `unnecessary_repetition` against the creator. A text-similarity de-dup would also erase genuine repetition, which is the very defect we detect. Validation: after the guard, 2790/2790 remaining words aligned, versus 2790/2986 before; every unaligned word was loop text. | A real speaker exceeds 10 words/s (e.g. auctioneer-style content), or loops appear at plausible rates (then add a decode-time `hallucination_silence_threshold` and re-run ASR). |
| W-02 | Evidence for a **visual** signal (freeze/black) returns the sampled stills inside its interval (≤8, evenly spaced), or the nearest still. | A reviewer can't judge a "frozen picture" claim from numbers alone. Frames are the cheapest proof already in the package. | Packages start carrying dedicated per-finding thumbnails. |

## 10. Known open items

* Script-only (no video) mode: provisional in P1, not built.
* RapidOCR swap for D18.
* Frames-stage hash mismatch seen once after a crash: the cache verifier rebuilt the stage correctly, but the root cause is unexplained (suspect: a partial write before the crash, then a stale `current.json`).
