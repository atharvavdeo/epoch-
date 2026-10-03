"""Offline E5 scores through the ASR interpreter; API imports remain stdlib-only."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

from pipeline.orchestration.settings import REPO_ROOT, data_dir, env_python
from pipeline.local_models import manifest, offline_env

_ENCODER_LOCK = threading.Lock()


@lru_cache(maxsize=64)
def _score(query: str, texts: tuple[str, ...]) -> tuple[float, ...]:
    model = manifest("embed")
    cache = data_dir() / "retrieval_cache"
    cache.mkdir(exist_ok=True)
    key = hashlib.sha256(json.dumps([model["manifest_digest"], texts], ensure_ascii=False).encode()).hexdigest()
    with _ENCODER_LOCK, tempfile.TemporaryDirectory(prefix="query-", dir=cache) as temp:
        request, response = Path(temp) / "request.json", Path(temp) / "response.json"
        request.write_text(json.dumps({"query": query[:4000], "texts": texts,
                                      "model_dir": model["snapshot_dir"], "cache": str(cache / f"{key}.json"),
                                      "output": str(response)}, ensure_ascii=False), encoding="utf-8")
        cmd = [str(env_python("asr")), "-m", "pipeline.reasoning.semantic_retrieval_worker", str(request)]
        if os.name != "nt":
            cmd = ["nice", "-n", "10", *cmd]
        subprocess.run(cmd, cwd=REPO_ROOT, env={**os.environ, **offline_env(), "TOKENIZERS_PARALLELISM": "false"},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90, check=True)
        return tuple(json.loads(response.read_text(encoding="utf-8"))["scores"])


def local_semantic_scores(query: str, passages: list[dict]) -> tuple[float, ...]:
    return _score(query, tuple(p["text"] for p in passages))


def transcript_index(segments: list[dict]):
    """Ready-to-use hybrid index; model failures remain visible as lexical fallback."""
    from pipeline.reasoning.rag import TranscriptIndex
    return TranscriptIndex(segments, semantic_scorer=local_semantic_scores)
