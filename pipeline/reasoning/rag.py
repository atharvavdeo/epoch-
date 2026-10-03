"""Hybrid transcript retrieval with a dependency-free lexical fallback.

Dense scores come from the pinned local E5 encoder in an isolated subprocess;
rank fusion avoids treating cosine as a relevance probability or rewrite verdict.
"""

from __future__ import annotations

import math
import unicodedata
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
    t = "".join(c if c.isalnum() or unicodedata.category(c).startswith("M") or c == "'" else " " for c in t)
    return [_stem(NUM.get(w, w)) for w in t.split() if NUM.get(w, w) not in _STOP and len(NUM.get(w, w)) > 0
            and (len(w) > 1 or w.isdigit())]


class TranscriptIndex:
    def __init__(self, segments: list[dict], window: int = WINDOW, semantic_scorer=None):
        self.semantic_scorer = semantic_scorer
        self.last_method = "lexical_bm25"
        self.last_fallback = None
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
        self.last_method, self.last_fallback = "lexical_bm25", None
        if k <= 0:
            return []
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
        if self.semantic_scorer and query.strip() and self.passages:
            try:
                dense = self.semantic_scorer(query, self.passages)
                if len(dense) != len(self.passages) or any(not math.isfinite(v) for v in dense):
                    raise ValueError("invalid embedding scores")
                ranks = sorted(range(len(dense)), key=lambda i: -dense[i])
                fused = {i: 1 / (60 + rank) for rank, i in enumerate(ranks, 1)}
                hits_by_id = {i: hits for _, i, hits in scored}
                for rank, (_, i, _) in enumerate(scored, 1):
                    fused[i] += 1 / (60 + rank)
                # Selection adds a bounded location prior without excluding semantic results elsewhere.
                if near_ms is not None:
                    for i, p in enumerate(self.passages):
                        if p["start_ms"] <= near_ms <= p["end_ms"]:
                            fused[i] += 1 / 120
                scored = sorted([(v, i, hits_by_id.get(i, [])) for i, v in fused.items()], reverse=True)
                self.last_method = "hybrid_e5_bm25"
            except Exception:
                # No raw exception text: model/path/process errors can contain sensitive environment details.
                self.last_fallback = "semantic encoder unavailable; used lexical retrieval"
        out, taken = [], []
        for s, i, hits in scored:
            p = self.passages[i]
            if any(p["start_ms"] < b and p["end_ms"] > a for a, b in taken):  # no overlapping duplicates
                continue
            taken.append((p["start_ms"], p["end_ms"]))
            out.append({**p, "score": round(s, 5), "matched": sorted(set(hits)), "retrieval_method": self.last_method,
                        "retrieval_warning": self.last_fallback})
            if len(out) >= k:
                break
        return sorted(out, key=lambda x: x["start_ms"])
