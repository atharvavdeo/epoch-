# Running the visual analysis on Colab (Qwen3.5-9B)

Only the video-understanding step runs on Colab. Everything else runs on the laptop.
The notebook never needs editing between videos: all code ships inside the job zip.

## On the laptop (before Colab)

1. Run the local stages for the video (it stops after making the Colab job):

   ```bash
   .venvs/media/Scripts/python.exe -m pipeline.cli analyze "C:/path/video.mp4" --title "Exact YouTube title" --category education --language en
   ```

   `--category`: `tech_review | education | other`. `--language`: `en | hi | mixed | unknown`.
   If it is interrupted, run the same command again: finished stages are reused.

2. Open `outputs/<video>/README.txt`. The last lines name the job file:
   `outputs/<video>/colab/<asset>_<job>.visualjob.zip` (about 30–90 MB).

## On the Colab account

1. Upload that zip to Google Drive at **`MyDrive/epoch/jobs/`** (create the folders once).
2. Upload `notebooks/epoch_visual_colab.ipynb` to Colab (*File > Upload notebook*).
3. *Runtime > Change runtime type* → **A100 GPU**, and High-RAM if offered.
4. Run the cells **one at a time, top to bottom**:

| Cell | What it does | Typical time | If it stops |
|---|---|---|---|
| 1 Settings | `PROFILE = "Q35-9B-BF16"` (default) | instant | — |
| 2 Preflight | mounts Drive, copies + unzips the job, checks GPU/disk **before any download** | 1 min | "insufficient_gpu_memory" → you got an L4/T4: change runtime to A100. "No *.visualjob.zip" → upload to `MyDrive/epoch/jobs/` |
| 3 Environment | isolated Python 3.11 venv from the hashed lock | 3–5 min | read the error; do not loop-retry. A second run reuses the finished venv |
| 4 Model | downloads Qwen3.5-9B at the pinned revision, sha256-verifies every file | 3–8 min (~19 GB) | network errors retry twice automatically |
| 5 Run | qualification (4 inferences) → ~43 clips → ≤8 refinements | ~20–45 min | see "Recovery" |
| 6 Save | copies the result to `MyDrive/epoch/results/` and downloads it | 1 min | — |

The qualification prints headroom and an estimate, e.g. `qualification PASSED: headroom 12.3 GiB, 28.4s/clip, est. 20.4 min for 43 clips`.

## Back on the laptop

```bash
.venvs/media/Scripts/python.exe -m pipeline.cli attach-visual <sha-prefix> "C:/Downloads/<name>.Q35-9B-BF16.visualresult.zip"
.venvs/media/Scripts/python.exe -m pipeline.cli finish <sha-prefix>
```

`<sha-prefix>` is the 8 characters in the outputs folder name (e.g. `5234018a`).

## Recovery (no blind retries)

- **Disconnect / runtime reset:** reconnect, run all cells again. Each finished clip was copied and hash-verified on Drive (`MyDrive/epoch/checkpoints/`) and is skipped.
- **"qualification FAILED":** the result zip still downloads with the reason. Do not rerun the same settings hoping it passes; report the reason.
- **Some clips `failed`:** normal in small numbers; they become *visual unknown* in the report (never "clean"). If more than 20% fail, the run stops early on purpose.
- **OOM on a clip:** retried once with half the frames automatically; a second failure marks that window unknown.
- **Exit code 2:** read `fatal_error.json` in `/content/epoch/out/<name>/`.

## What is guaranteed

- Same frames the laptop hashed (no video decoding on Colab), same prompt, pinned model revision, BF16, no quantization or CPU offload.
- Every claim the model makes must cite frames it was shown; invalid output is repaired once, then recorded as failed, never silently accepted.
