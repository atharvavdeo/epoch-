"""embed stage (subprocess in asr env): multilingual-e5-base retrieval.

Paragraphs are encoded with the model's documented 'passage: ' prefix,
L2-normalised; for each paragraph the top-3 non-adjacent neighbours with
cosine >= 0.85 become repetition *candidates* (similarity is retrieval,
not a verdict: FEATURES F50).
"""

from __future__ import annotations

from pathlib import Path

from pipeline.orchestration.io import read_json, write_json
from pipeline.orchestration.stage import subprocess_main
from pipeline.reasoning.chunks import make_chunks

TOP_K, MIN_COS = 3, 0.85


def run(args: dict, out: Path) -> dict:
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(int(args.get("threads") or 4))
    segs = read_json(args["transcript"])["segments"]
    chunks = make_chunks(segs)
    model = SentenceTransformer(args["model_dir"], device="cpu", local_files_only=True)
    model.max_seq_length = 512
    texts = ["passage: " + c["text"] for c in chunks]
    tok = model.tokenizer
    truncated = [c["chunk_id"] for c, t in zip(chunks, texts) if len(tok(t)["input_ids"]) > 512]
    emb = model.encode(texts, batch_size=8, normalize_embeddings=True, convert_to_numpy=True) if chunks else np.zeros((0, 768))
    sim = emb @ emb.T if len(chunks) else np.zeros((0, 0))
    pairs = []
    for i in range(len(chunks)):
        cand = [(float(sim[i, j]), j) for j in range(len(chunks)) if abs(i - j) > 1]
        for cos, j in sorted(cand, reverse=True)[:TOP_K]:
            if cos >= MIN_COS and i < j:
                pairs.append({"earlier": chunks[i]["chunk_id"], "later": chunks[j]["chunk_id"], "cosine": round(cos, 4)})
    write_json(out / "chunks.json", {"chunks": chunks, "pairs": pairs, "truncated_chunks": truncated,
                                     "config": {"top_k": TOP_K, "min_cos": MIN_COS, "prefix": "passage: "}})
    print(f"{len(chunks)} paragraphs, {len(pairs)} repetition candidates (cos>={MIN_COS})", flush=True)
    return {"status": "complete", "summary": {"chunks": len(chunks), "pairs": len(pairs)}}


if __name__ == "__main__":
    subprocess_main(run)
