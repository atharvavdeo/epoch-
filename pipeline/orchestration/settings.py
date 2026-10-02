"""Paths, .env loading and environment interpreters (no third-party deps)."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_NAMES = ("media", "asr", "ocr", "api")


@lru_cache(maxsize=1)
def load_dotenv() -> dict[str, str]:
    """Minimal KEY=VALUE parser for REPO_ROOT/.env; real env vars win."""
    values: dict[str, str] = {}
    path = REPO_ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    for k in list(values):
        if k in os.environ:
            values[k] = os.environ[k]
    return values


def setting(name: str, default: str = "") -> str:
    return os.environ.get(name) or load_dotenv().get(name) or default


def data_dir() -> Path:
    p = Path(setting("EPOCH_DATA_DIR", str(REPO_ROOT.parent / "epoch-data")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def models_dir() -> Path:
    p = data_dir() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def env_python(env: str) -> Path:
    if env not in ENV_NAMES:
        raise ValueError(f"unknown environment {env}")
    base = REPO_ROOT / ".venvs" / env
    for cand in (base / "Scripts" / "python.exe", base / "bin" / "python"):
        if cand.exists():
            return cand
    raise FileNotFoundError(f"environment '{env}' missing; run scripts/setup_envs.sh {env}")


def current_env() -> str | None:
    exe = Path(sys.executable).resolve()
    for env in ENV_NAMES:
        if (REPO_ROOT / ".venvs" / env).resolve() in exe.parents:
            return env
    return None


def lock_path(env: str) -> Path:
    return REPO_ROOT / "locks" / f"{env}.txt"
