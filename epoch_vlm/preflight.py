"""Hardware/disk/RAM preflight with stop rules (COLAB_RUNBOOK §1–§2).

Standard library only: runs in the notebook kernel before any environment
is created or any weight is downloaded. Fails fast on impossible capacity.
Profile selection is explicit and recorded; "auto" picks the strongest
profile whose gate passes, and the choice is printed and stored.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess

GIB = 1024 ** 3
SAFETY_RESERVE_GIB = 20.0
ENV_INSTALL_GIB = 12.0  # torch cu126 + deps in a venv, generous


class PreflightError(RuntimeError):
    def __init__(self, code: str, message: str, action: str):
        super().__init__(f"[{code}] {message}\n  -> {action}")
        self.code = code
        self.action = action


def query_gpus() -> list[dict]:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version,compute_cap",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    gpus = []
    for line in out.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4:
            gpus.append({"name": parts[0], "total_gib": round(float(parts[1]) / 1024, 2),
                         "free_gib": round(float(parts[2]) / 1024, 2), "driver": parts[3],
                         "compute_capability": parts[4] if len(parts) > 4 else None})
    return gpus


def host_ram_gib() -> float | None:
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1024 / 1024, 2)
    except OSError:
        return None
    return None


def choose_profile(requested: str, gpus: list[dict], profiles: dict) -> tuple[str, dict]:
    if not gpus:
        raise PreflightError("hardware_unavailable", "no NVIDIA GPU visible (CPU/TPU runtime)",
                             "Runtime > Change runtime type > GPU (A100/H100). Do not retry hoping for a different result.")
    g = gpus[0]
    cc = g.get("compute_capability")
    if cc and float(cc) < 8.0:
        raise PreflightError("bf16_unsupported", f"{g['name']} (compute {cc}) lacks BF16; profiles need Ampere or newer",
                             "Select an A100/L4/H100 runtime; T4/V100 cannot run the BF16 profiles.")
    order = [k for k in profiles]  # strongest first
    candidates = order if requested == "auto" else [requested]
    for name in candidates:
        if name not in profiles:
            raise PreflightError("unknown_profile", f"profile {name} is not offered by this job", f"use one of {order}")
        p = profiles[name]
        if g["total_gib"] >= p["min_total_gib"] and g["free_gib"] >= p["min_free_gib"]:
            return name, {"gpu": g, "gate": {"min_total_gib": p["min_total_gib"], "min_free_gib": p["min_free_gib"]}}
    need = ", ".join(f"{k}: total>={profiles[k]['min_total_gib']} free>={profiles[k]['min_free_gib']} GiB" for k in candidates)
    raise PreflightError("insufficient_gpu_memory",
                         f"{g['name']} has {g['total_gib']} GiB total / {g['free_gib']} GiB free; gates: {need}",
                         "Use an 80 GB (27B) or 40 GB (9B) GPU runtime. Quantization/offload are disabled by design.")


def check_disk(path: str, required_gib: float) -> dict:
    os.makedirs(path, exist_ok=True)
    free = shutil.disk_usage(path).free / GIB
    if free < required_gib:
        raise PreflightError("insufficient_disk", f"{path} has {free:.1f} GiB free; need {required_gib:.1f} GiB",
                             "Delete old model copies from /content, or use a runtime with a larger disk.")
    return {"path": path, "free_gib": round(free, 1), "required_gib": round(required_gib, 1)}


def run_preflight(requested_profile: str, profiles: dict, model_cache_dir: str, job_bytes: int,
                  cached_weight_bytes: int = 0) -> dict:
    gpus = query_gpus()
    name, sel = choose_profile(requested_profile, gpus, profiles)
    weights_gib = max(0, profiles[name]["weight_bytes"] - cached_weight_bytes) / GIB
    required = weights_gib + ENV_INSTALL_GIB + 2 * job_bytes / GIB + SAFETY_RESERVE_GIB
    disk = check_disk(model_cache_dir, required)
    ram = host_ram_gib()
    report = {"profile": name, "requested_profile": requested_profile, **sel, "disk": disk, "host_ram_gib": ram,
              "python": platform.python_version(), "os": platform.platform(), "all_gpus": gpus}
    if ram is not None and ram < 24 and name.startswith("Q35-27B"):
        report["warning"] = f"host RAM {ram} GiB is below the 32 GiB recommendation; shard loading may be slow"
    return report
