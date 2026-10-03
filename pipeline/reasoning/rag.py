"""Small retrieval layer over the transcript (stdlib only): BM25 over overlapping ~25 s passages.

Why BM25 and not embeddings: the API env has no embedding model, transcripts are short (one video), and the
questions creators ask mostly name the thing they mean ("input bias", "the Antarctic trek", "subscribe").
Lexical retrieval is exact, explainable (we can show the matched words) and has no model to drift.
A passage is 3 consecutive segments, stride 1, so every sentence appears in up to 3 passages with context.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from pipeline.reasoning.relations import _STOP

WINDOW = 3
K1, B = 1.4, 0.75
SYNONYMS = {  # a few creator-vocabulary expansions; kept tiny on purpose
    "intro": ["hook", "opening", "beginning"], "hook": ["intro", "opening"], "ending": ["end", "outro", "final"],
    "cta": ["subscribe", "like"], "retention": ["watching", "viewers"], "pacing": ["pace", "energy", "cycle"],
    "thumbnail": ["thumbnails", "title"], "example": ["instance"],
}


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


NUM = {w: str(i) for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())}
NUM.update({"twenty": "20", "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70", "hundred": "100"})


def _terms(text: str) -> list[str]:
    t = text.lower().replace("mr. beast", "mrbeast").replace("mr beast", "mrbeast").replace("mr b ", "mrbeast ")
    return [_stem(NUM.get(w, w)) for w in re.findall(r"[a-z0-9']+", t) if NUM.get(w, w) not in _STOP and len(NUM.get(w, w)) > 0
            and (len(w) > 1 or w.isdigit())]


class TranscriptIndex:
    def __init__(self, segments: list[dict], window: int = WINDOW):
        segs = sorted(segments, key=lambda s: s["interval"]["start_ms"])
        self.passages = []
        for i in range(len(segs)):
            grp = segs[i: i + window]
            if not grp:
                continue
            self.passages.append({"start_ms": grp[0]["interval"]["start_ms"], "end_ms": grp[-1]["interval"]["end_ms"],
                                  "text": " ".join(g["text"] for g in grp)})
            if i + window >= len(segs):
                break
        self.tf = [Counter(_terms(p["text"])) for p in self.passages]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.len) / max(1, len(self.len))
        df = Counter(w for t in self.tf for w in t)
        n = len(self.passages)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    def search(self, query: str, k: int = 6, near_ms: int | None = None) -> list[dict]:
        q = _terms(query)
        q += [_stem(s) for w in list(q) for s in SYNONYMS.get(w, [])]
        qc = Counter(q)
        scored = []
        for i, tf in enumerate(self.tf):
            s, hits = 0.0, []
            for w, qn in qc.items():
                f = tf.get(w, 0)
                if not f:
                    continue
                s += qn * self.idf.get(w, 0) * f * (K1 + 1) / (f + K1 * (1 - B + B * self.len[i] / self.avg))
                hits.append(w)
            if near_ms is not None:  # the reviewer is looking at a moment: favour passages around it
                p = self.passages[i]
                if p["start_ms"] - 20_000 <= near_ms <= p["end_ms"] + 20_000:
                    s += 1.5
            if s > 0:
                scored.append((s, i, hits))
        scored.sort(key=lambda x: -x[0])
        out, taken = [], []
        for s, i, hits in scored:
            p = self.passages[i]
            if any(p["start_ms"] < b and p["end_ms"] > a for a, b in taken):  # no overlapping duplicates
                continue
            taken.append((p["start_ms"], p["end_ms"]))
            out.append({**p, "score": round(s, 2), "matched": sorted(set(hits))})
            if len(out) >= k:
                break
        return sorted(out, key=lambda x: x["start_ms"])
