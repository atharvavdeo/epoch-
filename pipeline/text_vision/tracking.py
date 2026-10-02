"""Temporal OCR tracking (TRD §3), pure Python.

Joins detections on chronologically sampled frames when the boxes overlap
(IoU >= 0.5) and normalised text similarity >= 0.8; one missing sampled
frame is tolerated. A track's interval runs from its first observing sample
to the next sample where it was not observed (or video end): an inference
between samples, never exact subtitle timing.
"""

from __future__ import annotations

import difflib
import unicodedata

IOU_MIN = 0.5
TEXT_SIM_MIN = 0.8
MAX_MISSES = 1
MIN_SCORE = 0.5


def norm_text(t: str) -> str:
    return " ".join(unicodedata.normalize("NFC", t).casefold().split())


def bbox(quad: list[list[float]]) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    return min(xs), min(ys), max(xs), max(ys)


def iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    iw, ih = max(0.0, min(ax1, bx1) - max(ax0, bx0)), max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union > 0 else 0.0


def similarity(a: str, b: str) -> float:
    a, b = norm_text(a), norm_text(b)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def build_tracks(frames: list[dict], video_end_ms: int) -> list[dict]:
    """frames: chronological [{frame_id, at_ms, boxes:[{quad,text,score}]}] -> raw tracks."""
    frames = sorted(frames, key=lambda f: f["at_ms"])
    times = [f["at_ms"] for f in frames]
    open_tracks: list[dict] = []
    done: list[dict] = []
    for fi, fr in enumerate(frames):
        dets = [d for d in fr["boxes"] if d["score"] >= MIN_SCORE and norm_text(d["text"])]
        used = set()
        for tr in open_tracks:
            last = tr["samples"][-1]
            best, best_j = 0.0, None
            for j, d in enumerate(dets):
                if j in used:
                    continue
                ov = iou(bbox(last["quad"]), bbox(d["quad"]))
                if ov < IOU_MIN:
                    continue
                sim = similarity(last["observed_text"], d["text"])
                if sim >= TEXT_SIM_MIN and ov + sim > best:
                    best, best_j = ov + sim, j
            if best_j is not None:
                d = dets[best_j]
                used.add(best_j)
                tr["samples"].append({"frame_id": fr["frame_id"], "at_ms": fr["at_ms"], "quad": d["quad"],
                                      "observed_text": d["text"], "confidence": d["score"]})
                tr["misses"] = 0
                tr["last_index"] = fi
            else:
                tr["misses"] += 1
        still = []
        for tr in open_tracks:
            if tr["misses"] > MAX_MISSES:
                done.append(tr)
            else:
                still.append(tr)
        open_tracks = still
        for j, d in enumerate(dets):
            if j not in used:
                open_tracks.append({"samples": [{"frame_id": fr["frame_id"], "at_ms": fr["at_ms"], "quad": d["quad"],
                                                 "observed_text": d["text"], "confidence": d["score"]}],
                                    "misses": 0, "last_index": fi})
    done.extend(open_tracks)

    out = []
    for tr in done:
        s = tr["samples"]
        nxt = tr["last_index"] + 1
        end = times[nxt] if nxt < len(times) else video_end_ms
        start = s[0]["at_ms"]
        if end <= start:
            end = min(video_end_ms, start + 1)
        if end <= start:
            continue
        # representative text: most frequent normalised reading, highest confidence on ties
        counts: dict[str, list] = {}
        for x in s:
            counts.setdefault(norm_text(x["observed_text"]), []).append(x)
        rep = max(counts.values(), key=lambda xs: (len(xs), max(y["confidence"] for y in xs)))
        text = max(rep, key=lambda y: y["confidence"])["observed_text"]
        out.append({"start_ms": start, "end_ms": end, "text": text, "samples": s,
                    "detector_confidence": round(sum(x["confidence"] for x in s) / len(s), 4),
                    "observed_span_ms": s[-1]["at_ms"] - s[0]["at_ms"]})
    out.sort(key=lambda t: (t["start_ms"], t["text"]))
    return out
