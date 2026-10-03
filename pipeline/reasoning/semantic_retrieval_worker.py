"""One bounded CPU query job; only imported by the ASR subprocess."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def run(request: dict) -> dict:
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(min(6, max(1, int(os.environ.get("EPOCH_ASR_THREADS", "6")))))
    model = SentenceTransformer(request["model_dir"], device="cpu", local_files_only=True)
    model.max_seq_length = 512
    cache = Path(request["cache"])
    if cache.exists():
        vectors = np.asarray(json.loads(cache.read_text(encoding="utf-8"))["vectors"], dtype=np.float32)
    else:
        texts = ["passage: " + t for t in request["texts"]]
        # Truncation is recorded, rather than claiming all long-passage content was embedded.
        truncated = [i for i, t in enumerate(texts) if len(model.tokenizer(t)["input_ids"]) > 512]
        vectors = model.encode(texts, batch_size=8, normalize_embeddings=True, convert_to_numpy=True)
        tmp = cache.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"vectors": vectors.tolist(), "truncated_passages": truncated,
                                  "model": "intfloat/multilingual-e5-base", "prefix": "passage: "}), encoding="utf-8")
        tmp.replace(cache)
    q = model.encode(["query: " + request["query"]], normalize_embeddings=True, convert_to_numpy=True)[0]
    return {"scores": (vectors @ q).astype(float).tolist()}


if __name__ == "__main__":
    args = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    Path(args["output"]).write_text(json.dumps(run(args)), encoding="utf-8")
