"""Read verified local model manifests (written by scripts/setup_models.py)."""

from __future__ import annotations

import json

from pipeline.model_registry import MODELS
from pipeline.orchestration.settings import models_dir
from pipeline.orchestration.stage import StageError


def manifest(name: str) -> dict:
    m = MODELS[name]
    p = models_dir() / "manifests" / f"{m['repo'].replace('/', '__')}@{m['revision']}.json"
    if not p.exists():
        raise StageError("model_missing", f"pinned model '{name}' ({m['repo']}) is not downloaded",
                         recommended_action=f".venvs/asr/Scripts/python.exe scripts/setup_models.py {name}")
    return json.loads(p.read_text(encoding="utf-8"))


def model_fingerprint(name: str) -> dict:
    man = manifest(name)
    m = MODELS[name]
    return {"repo": m["repo"], "revision": m["revision"], "manifest_digest": man["manifest_digest"],
            "dtype": m["dtype"], "device": m["device"]}


def offline_env() -> dict[str, str]:
    """Inference after verification must not touch mutable upstream metadata."""
    return {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HOME": str(models_dir() / "hf_home"),
            "NLTK_DATA": str(models_dir() / "nltk")}
