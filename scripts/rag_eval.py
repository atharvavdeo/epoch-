"""Retrieval check for pipeline/reasoning/rag.py on the test video's transcript.

Gold = the time range where each answer is spoken, picked by reading the transcript (not by the retriever).
  .venvs/media/Scripts/python.exe scripts/rag_eval.py ../epoch-data/validation/mrbeast_transcript.json  (not in git: third-party transcript)
"""
import json
import sys

from pipeline.reasoning.rag import TranscriptIndex

GOLD = [("what is input bias", (240, 300)), ("how to use input bias without a big budget", (305, 320)),
        ("antarctic trek side story", (540, 575)), ("energy cycling pacing", (620, 700)),
        ("what colors are used in the thumbnail", (60, 70)), ("how long should a hook be", (371, 404)),
        ("what happens at the end of the video", (732, 809)), ("subscribe", (840, 850)),
        ("why does the first five seconds matter", (23, 60)), ("visual variety frequent cuts", (438, 502))]

ix = TranscriptIndex(json.load(open(sys.argv[1], encoding="utf-8"))["segments"])
h1 = h3 = 0
for q, (a, b) in GOLD:
    r = ix.search(q, k=3)
    inside = lambda p: p["start_ms"] // 1000 < b and p["end_ms"] // 1000 > a  # noqa: E731
    top = max(r, key=lambda p: p["score"]) if r else None
    h1 += bool(top and inside(top))
    h3 += any(inside(p) for p in r)
    print(f"{'hit' if any(inside(p) for p in r) else 'MISS'}  {q}")
print(f"hit@1 {h1}/{len(GOLD)}  hit@3 {h3}/{len(GOLD)}")
