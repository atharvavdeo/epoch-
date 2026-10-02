# Research ledger and evidence boundaries

Researched2026-10-03. Primary documentation, model metadata, release metadata and repository files were inspected. No weights were downloaded, inferenceAPI was invoked, ColabGPU was allocated or environment was installed during this planning task. Candidate pins and model choices require the one-time runtime qualification in COLAB_RUNBOOK.

## 1. Source-to-decision map

| ID | Primary source | What supports this plan / limit |
|---|---|---|
| S01 | [Qwen3.5-27B official model card](https://huggingface.co/Qwen/Qwen3.5-27B) and [9B card](https://huggingface.co/Qwen/Qwen3.5-9B) | Official checkpoint identities and inference inputs. Author benchmarks are broad tasks, not Hindi retention diagnosis. |
| S02 | [27B safetensors index](https://huggingface.co/Qwen/Qwen3.5-27B/raw/fc05daec18b0a78c049392ed2e771dde82bdf654/model.safetensors.index.json) and [9B index](https://huggingface.co/Qwen/Qwen3.5-9B/raw/c202236235762e1c871ad0ccb60c8ee5ba337b9a/model.safetensors.index.json) | Metadata total_size27B=55,562,872,800bytes;9B=19,306,216,416bytes. Weight storage does not include inference activations/KV/workspace. This makes27B all-GPU BF16 infeasible on40GB. |
| S03 | [Transformers Qwen3.5 documentation](https://huggingface.co/docs/transformers/model_doc/qwen3_5) and [v5.7.0 tagged implementation](https://github.com/huggingface/transformers/blob/v5.7.0/src/transformers/models/qwen3_5/modeling_qwen3_5.py) | Correct multimodal ConditionalGeneration class, distinct hybrid-attention kernel considerations; tagged class existence checked. Current docs can differ from selected release, so tagged source governs implementation. |
| S04 | [Colab FAQ](https://research.google.com/colaboratory/faq.html) | Resource types/limits vary; paid access is not a guarantee of a specific GPU. Runtime-local data is ephemeral; mountedDrive behaviour affects I/O. |
| S05 | [Accelerate big-model inference](https://huggingface.co/docs/accelerate/usage_guides/big_modeling) | Low-memory/sharded loading and device placement/offloading mechanisms. Our ban on automatic offload is a project design choice, not a limitation of Accelerate. |
| S06 | [Qwen3-VL-32B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-32B-Instruct) | Valid32B alternative checkpoint; not a memory-saving substitute for27B. No project-specific superiority established. |
| S07 | [LLaVA-OneVision-2-8B-Instruct](https://huggingface.co/lmms-lab-encoder/LLaVA-OneVision-2-8B-Instruct) | Distinct multimodal candidate with custom code; model card lists Transformers≥5.7/PyTorch≥2.4 and optional codec preprocessing. Defer to avoid introducing a second unqualified pipeline. |
| S08 | [WhisperX repository](https://github.com/m-bain/whisperX) and [published3.8.6 metadata](https://pypi.org/pypi/whisperx/3.8.6/json) | Alignment approach/limitations; published package requirements checked rather than assuming main branch equals release. Hub<1 and torch2.8-family dependencies drive environment isolation. |
| S09 | [Transformers5.7.0 metadata](https://pypi.org/pypi/transformers/5.7.0/json), [4.57.6 metadata](https://pypi.org/pypi/transformers/4.57.6/json) | VLM candidate requires Hub≥1.5,<2; ASR-compatible candidate uses Hub<1. Tokenizer range verified. Metadata compatibility is not runtime qualification. |
| S10 | [PyTorch previous-version wheel instructions](https://pytorch.org/get-started/previous-versions/) | Torch2.8.0, vision0.23.0, audio2.8.0 have aligned CUDA12.6 wheels. Actual driver/toolchain still checked in allocated runtime. |
| S11 | [Sentence-transformers5.1.2 metadata](https://pypi.org/pypi/sentence-transformers/5.1.2/json) | Transformers<5 requirement fits ASR/embedding environment; prevents accidental placement into VLM environment. |
| S12 | [PaddleOCR installation](https://www.paddleocr.ai/latest/en/version3.x/installation.html), [PP-OCRv5 multilingual models](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html), [PaddleOCR3.7.0 metadata](https://pypi.org/pypi/paddleocr/3.7.0/json) | CPU setup and multilingual recognition options; exact downloaded model/dictionary names and Hindi crop quality still need gate. |
| S13 | [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html), [ffprobe](https://ffmpeg.org/ffprobe.html), [PyAV documentation](https://pyav.org/docs/stable/) | Decode metadata, timestamps, black/freeze/silence/loudness measurements. Detection outputs alone do not establish editorial defects. |
| S14 | [PySceneDetect detectors](https://www.scenedetect.com/docs/latest/api/detectors.html) | Adaptive/content detector configuration and scene boundary candidates. Thresholds in FEATURES are project priors, not empirically established retention rules. |
| S15 | [Multilingual E5 base](https://huggingface.co/intfloat/multilingual-e5-base) | Embedding retrieval, multilingual support, prefix/token considerations. Similarity is not a repetition verdict or probability. |
| S16 | [Cerebras catalogue](https://inference-docs.cerebras.ai/models/overview), [structured outputs](https://inference-docs.cerebras.ai/capabilities/structured-outputs) | Current public model availability/strict-output interface. Account access untested; select exact model via capability probe. Public catalogue observed includes gpt-oss-120b and qwen3.8-27b, not proof the supplied account can use them. |
| S17 | [YouTube Analytics metrics](https://developers.google.com/youtube/analytics/metrics) | audienceWatchRatio/relativeRetentionPerformance have different meanings; replays prevent treating watch ratio as simple survival. |
| S18 | [YouTube Analytics dimensions](https://developers.google.com/youtube/analytics/dimensions#elapsedVideoTimeRatio) | elapsedVideoTimeRatio bins; native granularity must be preserved in validation. |
| S19 | [vRetention repository](https://github.com/flowtele/vRetention), [paper](https://yihchun.com/papers/vretention.pdf) | Public viewing/replay dataset and analysis notebooks. No ready project predictor; public YouTube heatmap provenance prevents using it as first-pass abandonment ground truth. |
| S20 | [Hub snapshot downloads](https://huggingface.co/docs/huggingface_hub/en/guides/download) | Revision pinning, file selection and local cache; informs resume/download lifecycle. |
| S21 | [Transformers loading environment variables](https://huggingface.co/docs/transformers/en/reference/environment_variables) | Parallel loading options exist; speed gain must be measured with Colab storage/RAM. |
| S22 | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and [CTranslate24.6.0 metadata](https://pypi.org/pypi/ctranslate2/4.6.0/json) | CUDA/cuDNN compatibility matters separately from PyTorch; verify CT2 inference rather than only torch.cuda. |
| S23 | [librosa0.11.0](https://pypi.org/pypi/librosa/0.11.0/json), [librosa latest metadata](https://pypi.org/pypi/librosa/json) | Selected0.11 supportsPython3.11; observed1.0 requiresPython≥3.12. Avoid latest-by-default setup. |
| S24 | [FastAPI](https://fastapi.tiangolo.com/), [Pydantic](https://docs.pydantic.dev/latest/), [SQLAlchemy SQLite](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html) | Local API/schema/persistence mechanisms, not mandatory architecture prescriptions. |
| S25 | [Vite7.1.7 metadata](https://registry.npmjs.org/vite/7.1.7), [React19.2.0 metadata](https://registry.npmjs.org/react/19.2.0) | Candidate release availability and Vite Node minimum verified. Full frontend dependency lock remains build-time qualification. |
| S26 | [Tailwind](https://tailwindcss.com/docs/installation/using-vite), [TanStack Query](https://tanstack.com/query/latest/docs/framework/react/overview), [Zustand](https://zustand.docs.pmnd.rs/), [Recharts](https://recharts.org/), [shadcn](https://ui.shadcn.com/docs) | Planned UI tools; native video remains authoritative player. Tool availability does not imply UX work has been done. |

## 2. Specific research findings that changed the design

The proposed unquantized27B model's weight index alone exceeds40GB. Therefore “ColabPro + A100” is insufficient specification: actual allocation matters. SmallerBF16 fallback preserves the no-quantization preference but changes capability, so results cannot retain the27B label.

Published WhisperX3.8.6 and Transformers5.7.0 cannot share the chosen Hub dependency. Even if the latest WhisperX main branch relaxes constraints, building against that moving branch would defeat reproducibility. Separate environments are a deliberate engineering solution to inspected metadata, not unnecessary infrastructure.

vRetention notebook interpolation produces convenient time-series samples, not new measurements at those timestamps. Its replay signal is useful for a different research question. Availability of a large public CSV does not make it the required label for viewer abandonment. The current plan therefore preserves the actual-retention validation gap instead of building a falsely supervised predictor.

A32B fallback is not a memory fallback. An8B LLaVA challenger may be feasible on smaller hardware, but changing processor/custom code and evaluating Hindi video behaviour adds work. No source establishes that expressions or cinematic polish from any model translate to calibrated retention estimates.

## 3. Evidence classification

**Verified by reading metadata/source:** listed checkpoint identities/revisions, inspected weight sizes, existence of selected model class in tagged Transformers, specified dependency conflicts, official metric definitions and dataset provenance.

**Design choices:** three phases, feature disposition, clip/frame/token caps, runtime threshold targets, ZIP limits, UI structure, risk weights, retention anchors and retry budgets. These are reasoned starting policies, not claims endorsed by model vendors or scientific studies.

**Unverified until implementation:** successful complete environment resolution, GPU fit at maximal clip settings, actual Colab throughput, Hindi transcription/OCR/grounding quality, inference provider account access, all frontend compatibility/security patches, and empirical retention accuracy.

## 4. Use of user-provided material

The original PS and script failure ideas,64-signal list and UI guide were read. The UI guide is copied verbatim to UI_REFERENCE. The earlier model/framework/sample-code recommendations are treated as proposals rather than trusted technical facts. No credential from the attachments is copied into this planning pack. Frameworks such as VideoAgent/VideoTree/OmAgent/OpenMontage may inspire bounded decomposition but are not dependencies: the current pipeline needs measured extraction, evidence validation and a small controller, not their full production/editing stacks.
