"""Inference backends: real Qwen3.5 (Colab) and a deterministic fake (tests).

QwenBackend follows COLAB_RUNBOOK §3: native Qwen3_5ForConditionalGeneration
+ AutoProcessor from a verified local snapshot, BF16 loaded directly (no
FP32 copy), explicit full-GPU placement {"": 0} (no silent CPU/disk
spill), placement/dtype verified after load, SDPA, eval + inference_mode,
batch 1, greedy decoding, bounded new tokens. No quantization.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field


class GpuOOM(RuntimeError):
    """Activation OOM during one clip (weights stay loaded)."""


@dataclass
class Prepared:
    inputs: object
    input_tokens: int
    image_count: int
    image_sizes: list[list[int]] = field(default_factory=list)


@dataclass
class Generated:
    text: str
    output_tokens: int
    elapsed_s: float
    hit_token_limit: bool


class QwenBackend:
    name = "qwen3_5"

    def __init__(self, snapshot_dir: str, *, attn: str = "sdpa", log=print):
        import torch
        from transformers import AutoProcessor, Qwen3_5ForConditionalGeneration

        t0 = time.time()
        processor = AutoProcessor.from_pretrained(snapshot_dir, local_files_only=True)
        torch.cuda.reset_peak_memory_stats()
        model = Qwen3_5ForConditionalGeneration.from_pretrained(
            snapshot_dir, dtype=torch.bfloat16, device_map={"": 0}, attn_implementation=attn,
            low_cpu_mem_usage=True, local_files_only=True)
        self._setup(model, processor, "cuda", time.time() - t0, log)

    @classmethod
    def from_parts(cls, model, processor, *, device: str = "cpu", log=print) -> "QwenBackend":
        """Same code path on an injected model (tests: tiny random Qwen3.5 on CPU)."""
        self = cls.__new__(cls)
        self._setup(model, processor, device, 0.0, log)
        return self

    def _setup(self, model, processor, device: str, load_s: float, log) -> None:
        import torch

        self.torch, self.log, self.device_type = torch, log, device
        self.processor, self.model = processor, model
        self.model.eval()
        self.load_s = load_s
        self.placement = self._verify_placement()
        self.template_info = self._probe_template()
        log(f"model loaded in {self.load_s:.0f}s; placement {self.placement['summary']}")

    # ------------------------------------------------------------------ checks
    def _verify_placement(self) -> dict:
        """Abort on any off-device parameter (silent CPU/disk offload) or if <90% of
        parameters are BF16 (an FP32 copy was loaded). Intentional FP32 parameters
        (e.g. Qwen3.5 DeltaNet state params, mamba_ssm_dtype=float32) are recorded."""
        torch = self.torch
        devices, dtypes, off_device, fp32_names = {}, {}, [], []
        for name, p in self.model.named_parameters():
            dev = str(p.device)
            devices[dev] = devices.get(dev, 0) + p.numel()
            dt = str(p.dtype).replace("torch.", "")
            dtypes[dt] = dtypes.get(dt, 0) + p.numel()
            if p.device.type != self.device_type:
                off_device.append(f"{name} on {dev}")
            elif p.is_floating_point() and p.dtype != torch.bfloat16:
                fp32_names.append(name)
        total = sum(devices.values()) or 1
        bf16_frac = dtypes.get("bfloat16", 0) / total
        if off_device:
            raise RuntimeError(f"placement check failed: {len(off_device)} parameters off {self.device_type}: {off_device[:5]}")
        if bf16_frac < 0.90:
            raise RuntimeError(f"precision check failed: only {bf16_frac:.1%} of parameters are bfloat16 ({dtypes})")
        return {"devices": devices, "dtypes": dtypes, "bf16_fraction": round(bf16_frac, 5),
                "non_bf16_parameters": fp32_names[:40], "non_bf16_count": len(fp32_names),
                "summary": f"{total / 1e9:.2f}B params on {list(devices)}, {bf16_frac:.2%} bf16"}

    def _probe_template(self) -> dict:
        msg = [{"role": "user", "content": [{"type": "text", "text": "ping"}]}]
        info = {"enable_thinking_kwarg": False, "generation_prompt_tail": None}
        try:
            text = self.processor.apply_chat_template(msg, tokenize=False, add_generation_prompt=True,
                                                      enable_thinking=False)
            info["generation_prompt_tail"] = text[-60:]
            plain = self.processor.apply_chat_template(msg, tokenize=False, add_generation_prompt=True)
            info["enable_thinking_kwarg"] = text != plain
        except Exception as exc:  # recorded, not hidden
            info["error"] = f"{type(exc).__name__}: {exc}"[:200]
        return info

    # --------------------------------------------------------------- inference
    def prepare(self, messages: list[dict]) -> Prepared:
        kwargs = {"enable_thinking": False} if self.template_info.get("enable_thinking_kwarg") else {}
        inputs = self.processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                                    return_dict=True, return_tensors="pt", **kwargs)
        n_images = sum(1 for m in messages for c in m["content"] if c.get("type") == "image")
        grid = inputs.get("image_grid_thw")
        sizes = []
        got = 0
        if grid is not None:
            got = int(grid.shape[0])
            patch = getattr(getattr(self.processor, "image_processor", None), "patch_size", 16) or 16
            sizes = [[int(w) * patch, int(h) * patch] for _, h, w in grid.tolist()]
        if got != n_images:
            raise RuntimeError(f"processor produced {got} image grids for {n_images} images: frames are not reaching the model")
        return Prepared(inputs=inputs, input_tokens=int(inputs["input_ids"].shape[-1]), image_count=got, image_sizes=sizes)

    def generate(self, prep: Prepared, max_new_tokens: int) -> Generated:
        torch = self.torch
        inputs = prep.inputs.to(self.model.device)
        t0 = time.time()
        try:
            with torch.inference_mode():
                out = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False,
                                          temperature=None, top_p=None, top_k=None)
        except torch.OutOfMemoryError as exc:
            del inputs
            self.release()
            raise GpuOOM(str(exc)[:300]) from exc
        new = out[0, inputs["input_ids"].shape[-1]:]
        text = self.processor.decode(new, skip_special_tokens=True)
        n = int(new.shape[-1])
        del out, inputs
        self.release()
        return Generated(text=text, output_tokens=n, elapsed_s=time.time() - t0, hit_token_limit=n >= max_new_tokens)

    def release(self) -> None:
        import gc

        gc.collect()
        if self.device_type == "cuda":
            self.torch.cuda.empty_cache()

    def memory(self) -> dict:
        if self.device_type != "cuda":
            return {"allocated_gib": 0.0, "reserved_gib": 0.0, "peak_reserved_gib": 0.0, "free_gib": 0.0, "total_gib": 0.0}
        c = self.torch.cuda
        gib = 1024 ** 3
        free, total = c.mem_get_info()
        return {"allocated_gib": round(c.memory_allocated() / gib, 3), "reserved_gib": round(c.memory_reserved() / gib, 3),
                "peak_reserved_gib": round(c.max_memory_reserved() / gib, 3), "free_gib": round(free / gib, 3),
                "total_gib": round(total / gib, 3)}

    def reset_peak(self) -> None:
        if self.device_type == "cuda":
            self.torch.cuda.reset_peak_memory_stats()


class FakeBackend:
    """Deterministic stand-in for tests: answers from the prompt itself.

    Never used for real packages (profile name FAKE is rejected on import).
    Behaviour can be scripted per clip: {"c001": ["oom", "bad_json", "ok"]}.
    """

    name = "fake"
    load_s = 0.0
    placement = {"summary": "fake"}
    template_info = {"enable_thinking_kwarg": True, "generation_prompt_tail": "fake"}

    def __init__(self, script: dict[str, list[str]] | None = None, tokens_per_image: int = 120):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.tpi = tokens_per_image
        self._peak = 1.0

    def prepare(self, messages: list[dict]) -> Prepared:
        imgs = [c for m in messages for c in m["content"] if c.get("type") == "image"]
        text = sum(len(c.get("text", "")) for m in messages for c in m["content"] if c.get("type") == "text")
        return Prepared(inputs=messages, input_tokens=len(imgs) * self.tpi + text // 4, image_count=len(imgs),
                        image_sizes=[[448, 256]] * len(imgs))

    def generate(self, prep: Prepared, max_new_tokens: int) -> Generated:
        messages = prep.inputs
        user_texts = [c["text"] for m in messages if m["role"] == "user" for c in m["content"] if c.get("type") == "text"]
        import re

        joined = "\n".join(user_texts)
        m = re.search(r'"clip_id": "([^"]+)"', joined) or re.search(r"for window (\S+?)\.", user_texts[-1])
        clip_id = m.group(1) if m else "c000"
        labels = [t.split(" ")[0] for t in user_texts if t[:1] == "F" and t[1:3].isdigit()]
        action = self.script.get(clip_id, ["ok"]).pop(0) if self.script.get(clip_id) else "ok"
        if action == "oom":
            raise GpuOOM("fake activation OOM")
        if action == "bad_json":
            return Generated("{not json", 3, 0.01, False)
        first, last = (labels[0], labels[-1]) if labels else ("F01", "F01")
        obj = {
            "clip_id": clip_id, "frames_reviewed": len(labels),
            "segments": [{"frames": [first, last], "scene_role": "talking_head", "shot_scale": "medium",
                          "visible_content": "Presenter in front of a plain wall.", "on_screen_text": "none"}],
            "information_flow": {"status": "same_information_restated", "evidence_frames": [first], "note": "Same framing."},
            "speech_visual_relation": {"status": "neutral_backdrop", "evidence_frames": [first], "transcript_quote": "",
                                       "note": "Picture does not show the topic being described."},
            "static_visual": {"is_static": True, "useful": "unclear", "reason": "Same framing in every frame."},
            "text_legibility": [], "technical_visual": [],
            "observations": [{"statement": "The presenter stays in the same medium shot across the core frames.",
                              "frames": [first, last], "polarity": "neutral", "certainty": "clear"}],
            "needs_closer_look": {"needed": False, "focus": "none", "reason": ""}, "unknowns": [],
        }
        return Generated(json.dumps(obj), 200, 0.01, False)

    def release(self) -> None:
        pass

    def memory(self) -> dict:
        return {"allocated_gib": 1.0, "reserved_gib": 1.0, "peak_reserved_gib": self._peak, "free_gib": 30.0,
                "total_gib": 40.0}

    def reset_peak(self) -> None:
        pass
