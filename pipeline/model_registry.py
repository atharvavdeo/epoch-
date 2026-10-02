"""Pinned model identities (COLAB_RUNBOOK §3, researched 2026-10-03).

Changing any entry is a profile change: it alters stage fingerprints and so
creates new runs; it never relabels old results.
"""

from __future__ import annotations

MODELS: dict[str, dict] = {
    "asr": {"repo": "Systran/faster-whisper-large-v3", "revision": "edaa852ec7e145841d8ffdb056a99866b5f0a478",
            "weights": ["model.bin"], "dtype": "float32", "device": "cpu"},
    "align_en": {"repo": "facebook/wav2vec2-base-960h", "revision": "22aad52d435eb6dbaf354bdad9b0da84ce7d6156",
                 "weights": ["model.safetensors", "pytorch_model.bin"], "dtype": "float32", "device": "cpu"},
    "align_hi": {"repo": "theainerd/Wav2Vec2-large-xlsr-hindi", "revision": "062f7f566e2671336992b011dcb9387cd3cffe5e",
                 "weights": ["model.safetensors", "pytorch_model.bin"], "dtype": "float32", "device": "cpu"},
    "embed": {"repo": "intfloat/multilingual-e5-base", "revision": "d128750597153bb5987e10b1c3493a34e5a4502a",
              "weights": ["model.safetensors", "pytorch_model.bin"], "dtype": "float32", "device": "cpu"},
}

# Colab VLM profiles (COLAB_RUNBOOK §1). Thresholds are a gate, not proof of fit.
VLM_PROFILES: dict[str, dict] = {
    "Q35-27B-BF16": {"repo": "Qwen/Qwen3.5-27B", "revision": "fc05daec18b0a78c049392ed2e771dde82bdf654",
                     "min_total_gib": 75.0, "min_free_gib": 68.0, "weight_bytes": 55_562_872_800},
    "Q35-9B-BF16": {"repo": "Qwen/Qwen3.5-9B", "revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
                    "min_total_gib": 37.0, "min_free_gib": 32.0, "weight_bytes": 19_306_216_416},
}

# File selection lives in epoch_vlm.fetch (shared with the Colab runtime).
from epoch_vlm.fetch import select_files  # noqa: E402,F401
