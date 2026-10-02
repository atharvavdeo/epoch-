"""Generate notebooks/epoch_visual_colab.ipynb (the only file you open in Colab).

The notebook is a thin, stable bootstrap. All logic (preflight, model fetch,
runner, prompts, lock) ships inside each *.visualjob.zip, so the notebook
never goes out of sync with the code that built the job.

  python scripts/build_notebook.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "notebooks" / "epoch_visual_colab.ipynb"
UV_VERSION = "0.10.7"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


CELLS = [
    md("""
# Epoch: visual analysis (Qwen3.5-9B on Colab)

This notebook runs only the video-understanding step. Everything else (ASR, cuts, audio, scoring) already ran on the laptop.

**Before you start**
1. *Runtime > Change runtime type > A100 GPU* (High-RAM if offered). L4/T4 will be refused in step 2.
2. Upload the `*.visualjob.zip` file made on the laptop to Google Drive folder **`MyDrive/epoch/jobs/`**.
3. Run the cells **in order, one at a time**. Each cell stops with a clear message if something is wrong.

**Output:** `MyDrive/epoch/results/<name>.Q35-9B-BF16.visualresult.zip`. Download it and give it to the laptop (`attach-visual`).

**If the runtime disconnects:** reconnect and run all cells again. Finished clips are kept in `MyDrive/epoch/checkpoints/` and are skipped.
"""),
    code("""
# 1. Settings (edit only if needed)
PROFILE = "Q35-9B-BF16"        # decided default (D17). "Q35-27B-BF16" only on an 80 GB GPU and only if the job allows it
JOB_ZIP = ""                   # leave empty to use the newest *.visualjob.zip in MyDrive/epoch/jobs/
ENABLE_REFINEMENT = True       # up to 8 closer looks, only where the first pass asks for them
DRIVE_ROOT = "/content/drive/MyDrive/epoch"
WORK = "/content/epoch"        # fast local disk (not Drive) for the model and frames
"""),
    code("""
# 2. Mount Drive, copy the job to local disk, and run preflight (no downloads happen before this passes)
import os, sys, glob, json, shutil, zipfile, subprocess
from google.colab import drive
drive.mount("/content/drive")
for d in ("jobs", "results", "checkpoints"):
    os.makedirs(f"{DRIVE_ROOT}/{d}", exist_ok=True)
src = JOB_ZIP or (sorted(glob.glob(f"{DRIVE_ROOT}/jobs/*.visualjob.zip"), key=os.path.getmtime) or [None])[-1]
assert src and os.path.exists(src), f"No *.visualjob.zip found in {DRIVE_ROOT}/jobs/. Upload it there first."
name = os.path.basename(src)[:-len(".visualjob.zip")]
JOB_DIR = f"{WORK}/jobs/{name}"
if not os.path.exists(f"{JOB_DIR}/job.json"):
    os.makedirs(JOB_DIR, exist_ok=True)
    shutil.copyfile(src, f"{WORK}/{os.path.basename(src)}")
    zipfile.ZipFile(f"{WORK}/{os.path.basename(src)}").extractall(JOB_DIR)
job = json.load(open(f"{JOB_DIR}/job.json"))
assert job["bootstrap_protocol"] == 1, "This job needs a newer notebook: rebuild notebooks/epoch_visual_colab.ipynb from the same commit."
assert PROFILE in job["profiles_allowed"], f"Job allows {job['profiles_allowed']}, not {PROFILE}."
sys.path.insert(0, f"{JOB_DIR}/runtime")
from epoch_vlm.preflight import run_preflight
report = run_preflight(PROFILE, {PROFILE: job["profiles"][PROFILE]}, f"{WORK}/models", os.path.getsize(src))
print(json.dumps({k: v for k, v in report.items() if k != "all_gpus"}, indent=1))
print(f"\\nJob {name}: {len(job['clips'])} clips, {len(job['refinements'])} refinement windows. Preflight PASSED.")
"""),
    code(f"""
# 3. Isolated Python 3.11 environment from the hashed lock (about 3-5 min; nothing global is touched)
VENV = f"{{WORK}}/vlmenv"
PY = f"{{VENV}}/bin/python"
def sh(cmd):
    print("$", cmd); r = subprocess.run(cmd, shell=True)
    assert r.returncode == 0, f"command failed (exit {{r.returncode}}). Do not retry blindly; read the error above."
if not os.path.exists(f"{{VENV}}/.ready"):
    sh("pip -q install uv=={UV_VERSION}")
    sh(f"uv venv --python 3.11 {{VENV}}")
    sh(f"uv pip sync --python {{PY}} --require-hashes --torch-backend cu126 {{JOB_DIR}}/runtime/locks/vlm.txt")
    open(f"{{VENV}}/.ready", "w").write("ok")
sh(f\"\"\"{{PY}} -c "import torch, transformers; from transformers import Qwen3_5ForConditionalGeneration; assert torch.cuda.is_available(); assert torch.cuda.is_bf16_supported(); print('torch', torch.__version__, 'transformers', transformers.__version__, torch.cuda.get_device_name(0))" \"\"\")
"""),
    code("""
# 4. Download the pinned model revision and verify every file's sha256 (9B: ~19 GB, a few minutes)
prof = job["profiles"][PROFILE]
MODEL_JSON = f"{WORK}/models/{PROFILE}.json"
fetch = f'''
import json, sys
sys.path.insert(0, "{JOB_DIR}/runtime")
from epoch_vlm.fetch import fetch_snapshot
m = fetch_snapshot("{prof["repo"]}", "{prof["revision"]}", "{WORK}/models", None)
json.dump(m, open("{MODEL_JSON}", "w"))
print("verified", m["repo"], m["revision"][:10], m["manifest_digest"][:12])
'''
open(f"{WORK}/fetch.py", "w").write(fetch)
sh(f"{PY} {WORK}/fetch.py")
SNAPSHOT = json.load(open(MODEL_JSON))["snapshot_dir"]
"""),
    code("""
# 5. Run: qualification -> all clips -> refinements. Progress prints per clip. Safe to re-run after a disconnect.
OUT = f"{WORK}/out/{name}"
MIRROR = f"{DRIVE_ROOT}/checkpoints/{name}.{PROFILE}"
env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONPATH=f"{JOB_DIR}/runtime", PYTHONUNBUFFERED="1")
cmd = [PY, "-m", "epoch_vlm.runner", "--job", JOB_DIR, "--out", OUT, "--profile", PROFILE,
       "--snapshot", SNAPSHOT, "--model-json", MODEL_JSON, "--mirror", MIRROR] + ([] if ENABLE_REFINEMENT else ["--no-refine"])
p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
for line in p.stdout:
    print(line, end="")
rc = p.wait()
print("\\nexit code", rc, "(0 = ok, 3 = no clip succeeded, 2 = fatal error: see fatal_error.json)")
"""),
    code("""
# 6. Save the result to Drive and download it
res = sorted(glob.glob(f"{WORK}/out/*.visualresult.zip"), key=os.path.getmtime)
assert res, "No result zip produced; read the log above."
dst = f"{DRIVE_ROOT}/results/{os.path.basename(res[-1])}"
shutil.copyfile(res[-1], dst)
r = json.load(open(f"{OUT}/result.json"))
print("counts:", r["counts"], "| stopped:", r["stopped_reason"], "| qualification passed:", r["qualification"]["passed"])
print("saved to", dst)
from google.colab import files
files.download(res[-1])
"""),
]


def main() -> None:
    nb = {"nbformat": 4, "nbformat_minor": 5, "cells": CELLS,
          "metadata": {"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "A100"},
                       "kernelspec": {"name": "python3", "display_name": "Python 3"},
                       "language_info": {"name": "python"}}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
