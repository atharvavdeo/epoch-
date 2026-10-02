"""Per-second features for the text retention model (deterministic, explainable).

Sources: aligned transcript (segments + word times), the narrative stage's validated structure
(hook, first substance, title-payoff timing, CTA/recap/outro/question/open-loop spans), and audio
measurements (waveform-quiet pauses). No LLM call happens here.
"""

from __future__ import annotations

import math
import re
import statistics

from pipeline.reasoning.candidates import _STOP, _content_trigrams, find_pauses
from pipeline.reasoning.transcript_signals import EN_FILLERS

CONCRETE = re.compile(r"\d|\b(for example|for instance|such as|let's say|imagine|like when)\b", re.I)


def _cw(text: str) -> set[str]:
    return {w for w in re.findall(r"[^\W_]+", text.lower()) if w not in _STOP and len(w) > 2}


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def build_features(T_ms: int, segments: list[dict], words: list[dict], structure: dict | None,
                   audio: dict | None = None, vad: list[dict] | None = None) -> tuple[list[dict[str, float]], dict]:
    T_s = max(1, math.ceil(T_ms / 1000))
    F: list[dict[str, float]] = [{} for _ in range(T_s)]
    info: dict = {"sources": []}

    def put(a_ms: int, b_ms: int, key: str, v: float) -> None:
        for t in range(max(0, a_ms // 1000), min(T_s, math.ceil(b_ms / 1000))):
            F[t][key] = max(F[t].get(key, 0.0), v)

    segs = sorted(segments, key=lambda s: s["interval"]["start_ms"])
    info["sources"].append(f"{len(segs)} transcript segments")

    # --- novelty and lexical repetition (per segment, against everything said before it)
    seen: set[str] = set()
    tri_seen: set[tuple] = set()
    nov, rep = [], []
    for s in segs:
        cw = _cw(s["text"])
        n = len(cw - seen) / len(cw) if cw else 1.0
        nov.append(n)
        tri = _content_trigrams(s["text"])
        rep.append(bool(tri) and len(tri & tri_seen) / len(tri) >= 0.5 and len(s["text"].split()) >= 6)
        seen |= cw
        tri_seen |= tri
    # repetition = a run of >= 2 consecutive sentences repeating earlier wording (same rule as the repetition
    # finding, E-01). One re-quoted line or a shared signpost phrase ("let's take a look at…") is not padding.
    i = 0
    while i < len(segs):
        j = i
        while j < len(segs) and rep[j]:
            j += 1
        if j - i >= 2:
            put(segs[i]["interval"]["start_ms"], segs[j - 1]["interval"]["end_ms"], "repetition", 1.0)
        i = max(j, i + 1)
    # windowed novelty: share of content words in a 20 s window never heard before that window. Per-sentence
    # novelty misfires on fragments ("The title of the video is,"), so it is smoothed and must stay low >= 10 s.
    seg_cw = [_cw(x["text"]) for x in segs]
    win_nov: list[float | None] = []
    for t in range(T_s):
        a, b = t * 1000 - 10_000, t * 1000 + 10_000
        inside = [k for k, x in enumerate(segs) if x["interval"]["end_ms"] > a and x["interval"]["start_ms"] < b]
        if not inside:
            win_nov.append(None)
            continue
        before = set().union(*(seg_cw[k] for k in range(inside[0]))) if inside[0] else set()
        cw = set().union(*(seg_cw[k] for k in inside))
        win_nov.append(len(cw - before) / len(cw) if len(cw) >= 8 else None)
    later = [x for t, x in enumerate(win_nov) if x is not None and t >= 60]
    med_nov = statistics.median(later) if later else 0.5
    info["median_window_novelty_after_1min"] = round(med_nov, 3)
    low = [t >= 30 and x is not None and x < 0.6 * med_nov for t, x in enumerate(win_nov)]
    t = 0
    while t < T_s:
        u = t
        while u < T_s and low[u]:
            u += 1
        if u - t >= 10:
            for k in range(t, u):
                F[k]["low_novelty"] = _clip((0.6 * med_nov - win_nov[k]) / (0.6 * med_nov))
        t = max(u, t + 1)

    # --- concreteness and sentence length
    for s in segs:
        if CONCRETE.search(s["text"]):
            put(s["interval"]["start_ms"], s["interval"]["end_ms"], "concrete", 1.0)
        longest = max((len(x.split()) for x in re.split(r"[.!?]+", s["text"]) if x.strip()), default=0)
        if longest > 30:
            put(s["interval"]["start_ms"], s["interval"]["end_ms"], "long_sentences", _clip((longest - 30) / 20))

    # --- pace from aligned words: local words/min over speaking time in a 20 s window vs this speaker's median
    timed = sorted((w for w in words if w.get("start_ms") is not None), key=lambda w: w["start_ms"])
    if len(timed) >= 50:
        starts = [w["start_ms"] for w in timed]
        local = []
        for t in range(T_s):
            a, b = t * 1000 - 10_000, t * 1000 + 10_000
            ws = [w for w in timed[_bisect(starts, a):_bisect(starts, b)]]
            speak = sum(w["end_ms"] - w["start_ms"] for w in ws) + sum(
                max(0, min(500, ws[i + 1]["start_ms"] - ws[i]["end_ms"])) for i in range(len(ws) - 1))
            local.append(60_000 * len(ws) / speak if speak > 4000 and len(ws) >= 8 else None)
        vals = [x for x in local if x]
        med = statistics.median(vals) if vals else None
        info["median_wpm"] = round(med) if med else None
        if med:
            for t, x in enumerate(local):
                if x is None:
                    continue
                if x < 0.8 * med:
                    F[t]["slow_pace"] = _clip((0.8 * med - x) / (0.3 * med))
                elif x > 1.2 * med:
                    F[t]["fast_pace"] = _clip((x - 1.2 * med) / (0.3 * med))
        info["sources"].append(f"{len(timed)} aligned words (pace)")
    else:
        info["sources"].append("no word timing: pace features off")

    # --- filler clusters: lexicon fillers per minute in a 20 s window (Hindi discourse words never counted)
    fill_t = []
    for s in segs:
        text = " " + re.sub(r"[^\w\s']", " ", s["text"].lower()) + " "
        n = sum(len(re.findall(rf"(?<=\s){re.escape(f)}(?=\s)", text)) for f in EN_FILLERS)
        if n:
            fill_t += [(s["interval"]["start_ms"] + s["interval"]["end_ms"]) // 2] * n
    for t in range(T_s):
        n = sum(1 for x in fill_t if abs(x - t * 1000) <= 10_000)
        if n >= 2:
            F[t]["filler_density"] = _clip(n * 3 / 6)  # fillers per minute / 6

    # --- quiet dead air (waveform-quiet gaps only, see N-03)
    if audio is not None and vad is not None:
        for g in find_pauses(vad, audio.get("silence", []), T_ms, audio.get("rms")):
            put(g["start_ms"], g["end_ms"], "dead_air", 1.0)
        info["sources"].append("audio waveform + VAD (dead air)")

    # --- structure from the validated narrative pass
    st = structure or {}
    sub = st.get("first_substance_ms")
    if sub:
        put(0, sub, "setup_before_substance", 1.0)
    hook = st.get("hook_ms")
    put(0, min(30_000, hook if hook is not None else 30_000), "no_hook_yet", 1.0)
    for p in st.get("promises", []):
        first = p.get("first_fulfil_ms")
        if p.get("status") in ("fulfilled", "partial") and first and first > 15_000:
            for t in range(15, min(T_s, first // 1000)):
                F[t]["payoff_pending"] = max(F[t].get("payoff_pending", 0.0), _clip((t - 15) / 60))
        elif p.get("status") in ("unaddressed", "uncertain"):
            for t in range(60, T_s):
                F[t]["payoff_pending"] = max(F[t].get("payoff_pending", 0.0), 0.5)
    for sp in st.get("spans", []):
        a, b = sp["interval"]["start_ms"], sp["interval"]["end_ms"]
        near_end = a >= T_ms - 45_000 or a >= 0.85 * T_ms
        if sp["kind"] in ("cta", "sponsor"):
            put(a, b, "outro" if near_end else "cta_or_sponsor", 1.0)
        elif sp["kind"] == "outro" or (sp["kind"] == "recap" and near_end):
            put(a, T_ms, "outro", 1.0)
        elif sp["kind"] in ("viewer_question", "open_loop"):
            for t in range(a // 1000, min(T_s, a // 1000 + 60)):
                F[t]["open_loop"] = max(F[t].get("open_loop", 0.0), 1.0 - (t - a // 1000) / 60)
    if structure is not None:
        info["sources"].append("narrative structure (hook, substance, payoff, spans)")
    else:
        info["sources"].append("no narrative structure: hook/payoff/CTA features off")
    return F, info


def _bisect(xs: list[int], v: int) -> int:
    lo, hi = 0, len(xs)
    while lo < hi:
        mid = (lo + hi) // 2
        if xs[mid] < v:
            lo = mid + 1
        else:
            hi = mid
    return lo
