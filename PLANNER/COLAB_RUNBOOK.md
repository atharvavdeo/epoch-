# Colab execution, loading and recovery specification

This specifies the notebook to build later. It has not been executed in Colab. The goal is **one bounded qualification, then cached reproducible batches**, not an unrealistic guarantee of zero failures. Google explicitly varies GPU availability and runtime resources. [S04]

## 1. Hardware profiles and stop rules

| Profile | Requirements before model download/load | Permitted use |
|---|---|---|
| Q35-27B-BF16 | 80GB-class NVIDIA GPU; total memory≥75GiB and free≥68GiB at preflight; CUDA/BF16 support verified; recommended host RAM≥32GiB with low-memory shard loading; disk computed below. | Preferred full analysis. Weight metadata ≈55.56GB /51.75GiB, leaving activation/workspace/KV budget. These thresholds are a gate, not proof of fit. |
| Q35-9B-BF16 | 40GB-class GPU; total≥37GiB, free≥32GiB; same runtime/driver checks. | Explicit lower-capacity fallback. Weight metadata≈19.31GB /17.98GiB. Must pass task rubric and report model identity. |
| L4-24GB | Insufficient validated headroom for the chosen9B video profile. | Optional later reduced-input experiment only; not a promised fallback or demo dependency. |
| T4/CPU/no GPU | Primary profiles cannot run as specified. | Perform CPU preprocessing or inspect cached results. Stop VLM stage with hardware_unavailable; no repeated 27B attempts. |

Colab Pro is a subscription, not an80GB reservation. If primary unavailable, select the declared9B profile once or postpone primary processing; do not cycle runtimes hoping to disguise this limitation. CPU/disk offload and4/8bit quantization are disabled. Quantization may be proposed later only as a new explicit design decision, with independent quality/memory comparison and run label.

Disk preflight uses actual files: required free bytes = uncached model snapshot bytes + planned media/proxy/frame bytes + environment install estimate + temporary copy/decode space +20GiB safety reserve. For27B, a practical initial budget is about120GiB free before first setup when staging only one copy of weights and a small batch. If downloading an archive and extracting it simultaneously, add archive size again. Do not assume120GiB suffices for every upload. Estimate assets from ffprobe/byte size before download. Host RAM is measured during smoke test; memmap/shard loading reduces but does not eliminate demand.

## 2. Fixed notebook sections

1. Configuration: choose profile, batch input list, title/category/language, Drive checkpoint root, optional rerun request. Show exact configuration hash.
2. Preflight: hardware/driver/runtime/OS/python, disk/RAM, dependency-lock compatibility, source file hashes, model access. **Fail before large download** on impossible capacity.
3. Environment setup: isolated venvs, frozen wheels/locks, import probes, CUDA/ASR/OCR tiny smoke tests. Controller calls the correct interpreter explicitly.
4. Cache preparation: retrieve pinned model revisions, verify files and digests; prepare runtime-local media/cache.
5. Qualification: one representative clip through ASR/OCR/VLM and schema validation, then a worst-case clip token-budget probe. Record measured peakVRAM and processing time.
6. Batch execution: stages across all videos, checkpoint after each unit.
7. Review: stage coverage, rejected proposals, unresolved errors; optional one targeted refinement pass.
8. Export: build/validate ZIP, copy final ZIP/checkpoints to persistent storage, provide download links and manifest summary.
9. Resume/rerun: load request, compare fingerprints and execute only invalidated units/dependents; never blindly “run all” again.

## 3. Model cache and loading

Pinned revisions researched on2026-10-03:

| Model | Revision |
|---|---|
| Qwen/Qwen3.5-27B | fc05daec18b0a78c049392ed2e771dde82bdf654 |
| Qwen/Qwen3.5-9B | c202236235762e1c871ad0ccb60c8ee5ba337b9a |
| Qwen/Qwen3-VL-32B-Instruct (contingency only) | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| Systran/faster-whisper-large-v3 | edaa852ec7e145841d8ffdb056a99866b5f0a478 |
| theainerd/Wav2Vec2-large-xlsr-hindi | 062f7f566e2671336992b011dcb9387cd3cffe5e |
| facebook/wav2vec2-base-960h | 22aad52d435eb6dbaf354bdad9b0da84ce7d6156 |
| intfloat/multilingual-e5-base | d128750597153bb5987e10b1c3493a34e5a4502a |

Download only necessary inference weights/config/tokenizer/processor files for the selected profile using snapshot_download pinned revision; do not download all alternatives. Exact allowed filenames derived from model index, not a wildcard that omits tokenizer/chat template files. Record snapshot manifest digest. Cache skips verified files/resumes interrupted downloads. No forced redownload. Snapshot directories are runtime-local for inference. Persistent Drive stores archives/manifests/checkpoints; avoid high-frequency random reads of thousands of small files through the Drive mount.

If moving cache between sessions, archive/copy once and verify digest after extraction. Prefer one local snapshot location; avoid a second full copy caused by `.save_pretrained`. In a live session, run offline/local_files_only after verification so inference does not unexpectedly contact mutable upstream metadata.

Load `Qwen3_5ForConditionalGeneration` with its matching AutoProcessor, safetensors and BF16 low-memory loading; use a complete explicit GPU placement rather than allowing `device_map=auto` to silently spill onto CPU/disk. Inspect the device map and dtype after loading; abort if placement/precision differs. Do not load an FP32 copy first and then convert. Use eval/inference_mode, batch1, bounded inputs and output tokens. Default SDPA; no FlashAttention compilation. Qwen's DeltaNet layers have separate optional kernels; SDPA does not solve their performance. [S03,S05]

Start parallel shard loading disabled. On a high-RAM runtime, the one-time qualification may compare `HF_ENABLE_PARALLEL_LOADING=true`, workers4; retain only if measured load time improves without unacceptable peakRSS. This is a loading optimisation, not quantization. Do not assume advertised speedups apply to Colab storage. Log cold download, cold load and warm per-clip times separately.

Load each model once per batch stage. ASR/alignment may switch language aligners serially; cache downloads. Exit the ASR process before starting VLM; process termination is the reliable GPU release boundary. Inside a stage, clear clip tensors after each inference, but retain model weights. Memory growth across clips is a failure, not an excuse to reload27B each clip.

## 4. Qualification gate before four-video batch

Run a30–60s representative clip with Hindi/English text, speech and a cut, plus a worst-case20s clip at max allowed frame/token settings. Check decode, timestamp mapping, ASR/alignment, OCR, actual image tensors reaching VLM, schema output, supported citations, peakVRAM, CPU RAM and throughput. Repeating a warm clip three times is a leak check, not a quality benchmark. Fail if peak reserved GPU memory leaves less than2GiB headroom or grows across equivalent warm runs without explanation.

Estimate full batch runtime from measured stage durations and number of clips. Target ≤90min/video warm; if estimate exceeds allotted runtime/compute budget, reduce number of videos processed that session or adopt validated9B profile. Do not reduce coverage without changing the sampling profile and labels. Quality acceptance uses VALIDATION; faster output alone is insufficient.

If reference DeltaNet is too slow: one planned review may evaluate prebuilt compatible `causal-conv1d`/`flash-linear-attention` kernels in a **separate candidate lock** after verifying architecture, Torch/CUDA ABI and licenses. No exact kernel pin is claimed verified here. If no compatible prebuilt wheel is qualified, retain the reference profile or change to the declared model contingency; do not spend the hackathon compiling unknown kernels repeatedly. Any new profile restarts the small qualification gate only, not all videos.

## 5. Checkpoint and download lifecycle

Every completed clip/ASR chunk is written to a temporary file, schema-validated, atomically renamed, hashed and appended to a stage journal. Copy checkpoint bundles to Drive after each completed clip or at most every2min, depending on transfer overhead. After checkpoint copy, verify receipt/hash; local completion and persistent completion are distinct. A disconnection may lose work since the last verified persistent checkpoint.

Rerun request upload includes base manifest hash, video hash, stages and intervals. On resume, check persistent completed units against current fingerprints. Reuse only matching verified outputs. Corrupted/missing units are recomputed; downstream units affected by changed context are invalidated. Whole-video narrative/risk is recomputed when any relevant local issue changes. Export immutable run ID and parent_run_id, never replace the old ZIP with different bytes under the same name.

Operator loop: upload video once → copy to runtime disk → record source hash → process/checkpoint → download analysis ZIP → import website → export targeted request or external edit plan → upload request and matching video if runtime reset → reuse cache/checkpoints → download child ZIP. Browser does not download weights or run Python inference. For demo, store packages and proxies locally before judges arrive.

## 6. Bounded recovery policy

| Failure | Automatic budget | Required result/action |
|---|---|---|
| Download transient network failure | 2 retries after initial,2s/8s backoff; honour service headers | Resume verified cache; then stop download stage and preserve partial cache. |
| Dependency resolver/import failure | 0 blind retries | One deliberate researched lock revision allowed during qualification; fail gate if unresolved. |
| GPU weight load OOM | 0 retries with same profile | Stop, record preflight miss; choose declared smaller profile in a new run or defer. |
| Clip activation OOM | 1 reduced-input retry | Halve frame cap32→16 (or24→12) and cap input tokens6,144; record degraded sampling; do not quantize. If still fails, mark interval unknown and continue other clips only after memory is healthy. |
| Invalid VLM/LLM JSON or invented refs | 1 schema repair | Then quarantine output and mark partial. Never accept invalid data to finish a batch. |
| ASR word alignment failure | 1 suitable language-aligner attempt per span | Keep ASR segment times, null word times, disable exact-word cut suggestions. |
| OCR engine/model unavailable | 0 install loops midbatch | Mark text track unknown; maintain other outputs; targeted rerun after qualified fix. |
| Media decode error | 1 explicit transcode/reprobe attempt | Keep mapping if verified; otherwise reject corrupted asset/mark incomplete region. |
| Cerebras429/5xx/network | Max2 retries after initial, within45s total request deadline | Honour Retry-After if within budget; then partial narrative/offline UI.401/403/no model access: no retry. |
| Colab disconnect | No hidden automatic runtime reconnect | Resume verified persistent checkpoints in a fresh runtime with matching qualified profile. |
| Export hash/import schema failure | 0 blind retries | Identify broken artifact, rebuild affected export once; no whole-video rerun unless source artifact corrupted. |

Per-video repair budget: at most8 additional semantic repair/refinement calls beyond the defined base analysis and8 planned refinement intervals. Individual failures still obey row budgets. Stop semantic stage early if >20% base clips fail validation or hardware faults recur twice; show partial coverage rather than consume quota. Do not let an LLM drive retry policy.
