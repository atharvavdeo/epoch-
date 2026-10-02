# Vision (VLM) track — honest status, 2026-10-03

**Decision (owner, 2026-10-03): vision is ON HOLD.** It becomes a separate, optional feature. The product must work end to end
without it. Nothing a creator sees today comes from a vision model.

## 1. What actually ran on a real GPU

Both runs used Colab A100, Qwen/Qwen3.5-9B BF16 at revision `c202236…`, transformers 5.7, SDPA attention, and
`epoch_vlm` from the job zip. Both stopped at the **qualification gate** before the 43-clip run, exactly as designed.

| Run | Job | Inferences | Valid answers | Why it stopped |
|---|---|---|---|---|
| 1 (22:39 UTC) | `8f1941e1…` (prompt v1, 768 output tokens, no transcript) | 2 clips + repairs | **0** | Every answer ran past 768 tokens mid-JSON; the repair asked for the same long object and was cut off again |
| 2 (23:17 UTC) | `c34df842…` (prompt v2 compact JSON, 1024 tokens, with transcript) | 2 clips + 3 repeats | **1** (clip c011) | c019: the model cited frame labels it was never shown, and wrote 8 segments where the schema allowed 4 |

**Total: 4 distinct clip inferences, 1 valid answer, 0 observations imported.**

### What worked
- **Infrastructure:** sha-verified model download, hashed environment, preflight, and placement. The model was 9.41B parameters,
  100% BF16, on `cuda:0`, with a 20 GiB peak and 19 GiB headroom on the A100. No OOM. Checkpointing and result packaging worked.
- **The validator caught every bad answer.** Nothing invalid was ever accepted.
- **The one valid answer (c011, ~3:40–4:00)** is plausible:
  - talking-head segments
  - "Text overlays emphasize key terms like 'MATCH' and 'EFFORT'"
  - speech-visual relation "illustrates speech"
  - text legibility "large and clear"

### What did not work
1. **Output length/format.** v1 answers were too long for the token cap.
2. **Label hallucination.** With prompt v2, the model cited frame labels that were never shown. This was partly our bug: labels had gaps because only ≤32 of up to ~49 candidate frames are shown. A fix is coded (contiguous labels F01..Fn, mapped back) but **never run on a GPU**.
3. **Accuracy problems even in the valid answer:**
   - `frames_reviewed: 43` when 32 frames were shown
   - on-screen text stitched across frames with stutters ("MATCH MATCH TITLE THUMBNAIL THROUGH THROUGH THE ROOF…")
4. **Speed:** 89–101 s per clip, an estimated 64–72 min per 14-min video. Qwen3.5 uses Gated DeltaNet linear attention; without the optimised kernels (flash-linear-attention / causal-conv1d, excluded by D05) it falls back to slow PyTorch code.
5. **Method limit:** sampled stills (≤32 frames per 20 s at 448 px) cannot see motion, timing, transitions or anything between stills. For retention, *when* and *how fast* things change matters more than single-frame descriptions.

## 2. Is c011 good enough to ship?
**No.** One valid clip out of four is not a feature. The descriptions are generic, and the OCR is unreliable. The deterministic
measurements already in the product (cuts, shot lengths, motion, black/freeze, brightness, blur) say more about visual pacing.

## 3. Recommendation for when vision resumes
- **Don't keep Qwen3.5-9B on still frames.** Its architecture is slow without extra kernels, and still-frame VQA is the wrong tool.
- **Native video understanding instead of stills.** Models that take a video tensor with temporal position encoding: Qwen2.5-VL / Qwen3-VL "video" input, or a hosted model with native video input. Ask for **timestamped events** (scene changes, on-screen text appearance, B-roll vs talking head), not free descriptions.
- **Schema-constrained decoding** (grammar/JSON-schema guided generation) so invalid JSON is impossible. This needs a reopened D05 (vLLM/SGLang currently excluded).
- **Deterministic tools before any VLM:**
  - PySceneDetect (already used)
  - OCR with timestamps (RapidOCR / Windows OCR)
  - face/person detection
  - motion/optical flow
  - The VLM should only label what these cannot.
- The GitHub "native video parsing" pipelines the owner mentioned are **not recorded in this repo**. Add their links here when resuming, so the evaluation is concrete.

## 4. What is in the code now
- `epoch_vlm/` runtime, `pipeline/visual/` job builder and importer, `notebooks/epoch_visual_colab.ipynb`. Kept, not deleted.
- Latest uncommitted-then-committed change (2026-10-03): contiguous frame labels with remapping, and a segment limit of 8.
  Unit-level only; **not validated on a GPU**.
- The product treats the visual track as **"not inspected"** everywhere (hatched, never "healthy"). Packages are `partial_analysis`
  with `visual` listed as missing.
