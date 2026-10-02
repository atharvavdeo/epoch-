"""Exercise the exact Colab code path without running Qwen-9B.

Run in the VLM twin env (transformers 5.7.0), CPU only:
  CUDA_VISIBLE_DEVICES= .venvs/vlmtest/Scripts/python.exe -m pytest tests/test_vlm_codepath.py -s

- real Qwen3.5-9B processor/tokenizer/chat template (config files only, no weights)
- every clip of the real job through QwenBackend.prepare(): token cap, image grids
- a tiny *randomly initialised* Qwen3_5ForConditionalGeneration built from the 9B
  config (same classes, DeltaNet + full attention + vision tower) driven through
  QwenBackend.generate(), the repair call, qualification and result packaging.
Random weights produce garbage text, so clips are expected to *fail validation*;
the test asserts the plumbing, not the answers.
"""

import copy
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

transformers = pytest.importorskip("transformers")
if not transformers.__version__.startswith("5."):
    pytest.skip("needs the vlm env (transformers 5.x)", allow_module_level=True)

DATA = Path(os.environ.get("EPOCH_DATA_DIR", "C:/Epoch/epoch-data"))
SNAP = DATA / "models/hf/models--Qwen--Qwen3.5-9B/snapshots/c202236235762e1c871ad0ccb60c8ee5ba337b9a"
JOBS = sorted(Path("C:/Epoch/epoch-/outputs").glob("*/colab/*.visualjob.zip"))
pytestmark = pytest.mark.skipif(not (SNAP / "chat_template.jinja").exists() or not JOBS, reason="needs 9B config files + a job")


@pytest.fixture(scope="module")
def job_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("job")
    zipfile.ZipFile(JOBS[0]).extractall(d)
    sys.path.insert(0, str(d / "runtime"))  # import the SHIPPED runtime exactly as Colab does
    for m in [m for m in sys.modules if m.startswith("epoch_vlm")]:
        del sys.modules[m]
    yield d
    sys.path.remove(str(d / "runtime"))


def tiny_model():
    import torch
    from transformers import AutoConfig, Qwen3_5ForConditionalGeneration

    cfg = AutoConfig.from_pretrained(SNAP, local_files_only=True)
    t, v = cfg.text_config, cfg.vision_config
    t.hidden_size, t.intermediate_size, t.num_hidden_layers = 64, 128, 4
    t.layer_types = ["linear_attention", "linear_attention", "linear_attention", "full_attention"]
    t.num_attention_heads, t.num_key_value_heads, t.head_dim = 2, 1, 64
    t.linear_num_key_heads, t.linear_num_value_heads, t.linear_key_head_dim, t.linear_value_head_dim = 2, 2, 32, 32
    t.mtp_num_hidden_layers = 0
    v.depth, v.hidden_size, v.intermediate_size, v.num_heads, v.out_hidden_size = 1, 64, 128, 2, 64
    torch.manual_seed(0)
    m = Qwen3_5ForConditionalGeneration(cfg).to(torch.bfloat16)
    return m


def test_real_processor_and_token_budget(job_dir):
    from transformers import AutoProcessor

    from epoch_vlm.backends import QwenBackend
    from epoch_vlm.prompting import build_messages, load_template, select_frames
    from epoch_vlm.runner import Runner

    proc = AutoProcessor.from_pretrained(SNAP, local_files_only=True)
    be = QwenBackend.from_parts(tiny_model(), proc, device="cpu")
    tpl = load_template(job_dir / "runtime/prompts/visual_observation.v2.md")
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    print("template:", be.template_info)
    print("placement:", {k: be.placement[k] for k in ("bf16_fraction", "non_bf16_count")}, be.placement["non_bf16_parameters"][:6])
    r = Runner.__new__(Runner)
    r.job_dir, r._images = job_dir, {}
    tokens = []
    for clip in job["clips"]:
        frames = select_frames(clip, job["limits"]["frame_cap"])
        prep = be.prepare(build_messages(job, clip, frames, tpl, r.image))
        assert prep.image_count == len(frames)  # every frame reaches the model as an image
        tokens.append(prep.input_tokens)
    print(f"input tokens over {len(tokens)} clips: min {min(tokens)} median {sorted(tokens)[len(tokens) // 2]} max {max(tokens)}"
          f" (cap {job['limits']['max_input_tokens']}); image sizes e.g. {prep.image_sizes[:2]}")
    assert max(tokens) <= job["limits"]["max_input_tokens"]
    assert be.template_info.get("enable_thinking_kwarg") is True or "error" not in be.template_info


def test_full_runner_path_with_tiny_random_model(job_dir, tmp_path):
    from transformers import AutoProcessor

    from epoch_vlm.backends import QwenBackend
    from epoch_vlm.runner import Runner, verify_job

    # two-clip copy of the real job (same files, same hashes) to keep CPU time small
    small = tmp_path / "job2"
    shutil.copytree(job_dir, small)
    job = verify_job(small)
    keep = job["clips"][:2]
    job2 = copy.deepcopy(job)
    job2["clips"], job2["refinements"] = keep, [r for r in job["refinements"] if r["clip_id"] in {c["clip_id"] for c in keep}][:1]
    job2["limits"] = {**job["limits"], "max_new_tokens": 48}
    (small / "job.json").write_text(json.dumps(job2), encoding="utf-8")

    proc = AutoProcessor.from_pretrained(SNAP, local_files_only=True)
    be = QwenBackend.from_parts(tiny_model(), proc, device="cpu")
    out = tmp_path / "out"
    runner = Runner(small, out, be, profile="Q35-9B-BF16", model_info={"repo": "tiny-random", "revision": "test"},
                    env_info={"gpu": {"name": "cpu-test"}}, mirror=tmp_path / "drive")
    res = runner.run()
    result = res["result"]
    print("qualification:", result["qualification"]["passed"], result["qualification"]["reasons"])
    print("counts:", result["counts"], "repairs used:", result["repairs_used"])
    # garbage weights => outputs fail validation; the plumbing must still work end to end
    assert Path(res["zip"]).exists()
    assert result["qualification"]["worst_input_tokens"] > 1000
    rec = runner.call("probe", keep[0], keep[0]["frames"], 8)
    assert rec["input_tokens"] and rec["raw_output"] is not None and rec["output_tokens"] > 0
    assert rec["repair_used"] or rec["status"] == "complete"
    assert (tmp_path / "drive" / "qualification.json").exists()
