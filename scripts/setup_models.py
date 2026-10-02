"""Download and verify the pinned local models (run with the asr venv).

  .venvs/asr/Scripts/python.exe scripts/setup_models.py [asr align_en align_hi embed]

Each model gets a manifest (file sha256s + digest) under
<EPOCH_DATA_DIR>/models/manifests/. Re-running skips verified snapshots.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.hf_fetch import fetch_snapshot  # noqa: E402
from pipeline.model_registry import MODELS  # noqa: E402
from pipeline.orchestration.settings import models_dir, setting  # noqa: E402


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(names: list[str]) -> int:
    names = names or list(MODELS)
    token = setting("HF_TOKEN") or None
    for n in names:
        m = MODELS[n]
        man = fetch_snapshot(m["repo"], m["revision"], models_dir(), m["weights"], token=token)
        print(f"{n}: {man['snapshot_dir']} ({sum(f['bytes'] for f in man['files']) / 1e9:.2f} GB)")
    # WhisperX sentence splitting needs NLTK punkt_tab; fetch once so alignment runs offline.
    import nltk

    nltk_dir = models_dir() / "nltk"
    if not (nltk_dir / "tokenizers" / "punkt_tab").exists():
        nltk.download("punkt_tab", download_dir=str(nltk_dir), quiet=True)
    print(f"nltk punkt_tab: {nltk_dir}")
    return 0


if __name__ == "__main__":
    _utf8_console()
    sys.exit(main(sys.argv[1:]))
