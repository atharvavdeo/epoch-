"""Transcript paragraphs for retrieval and prompting (TRD §5), stdlib only.

Segments are accumulated in order into paragraphs of ~100-200 words,
breaking only at segment ends (ASR segments end at sentence/pause
boundaries). Paragraph ids P01.. are stable for a given transcript.
"""

from __future__ import annotations

MIN_WORDS, MAX_WORDS = 100, 200


def words(text: str) -> int:
    return len(text.split())


def make_chunks(segments: list[dict]) -> list[dict]:
    chunks, cur = [], []

    def flush():
        if cur:
            chunks.append({"chunk_id": f"P{len(chunks) + 1:02d}",
                           "start_ms": cur[0]["interval"]["start_ms"], "end_ms": cur[-1]["interval"]["end_ms"],
                           "segment_ids": [s["segment_id"] for s in cur],
                           "text": " ".join(s["text"].strip() for s in cur),
                           "precision": "word" if all(s["precision"] == "word" for s in cur) else "segment"})

    n = 0
    for s in segments:
        w = words(s["text"])
        if cur and n + w > MAX_WORDS and n >= MIN_WORDS // 2:
            flush()
            cur, n = [], 0
        cur.append(s)
        n += w
        if n >= MIN_WORDS and s["text"].rstrip()[-1:] in ".?!।":
            flush()
            cur, n = [], 0
    flush()
    return chunks
