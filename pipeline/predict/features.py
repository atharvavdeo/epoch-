"""Per-second features for the text retention model (deterministic, explainable).

Sources: aligned transcript (segments + word times), the narrative stage's validated structure
(hook, first substance, title-payoff timing, CTA/recap/outro/question/open-loop spans), and audio
measurements (waveform-quiet pauses). No LLM call happens here.
"""

from __future__ import annotations

import math
import re
import statistics

ADVANCE = re.compile(r"\b(for example|for instance|however|because|therefore|instead|first|second|next step|to check|to find|in contrast)\b", re.I)

from pipeline.reasoning.candidates import _STOP, _content_trigrams, find_pauses
from pipeline.reasoning.transcript_signals import EN_FILLERS, announced_replay

CONCRETE = re.compile(r"\d|\b(for example|for instance|such as|let's say|imagine|like when)\b", re.I)
# An explicit recap/replay marker makes reused wording intentional reinforcement, not padding (rule B1).
RECAP = re.compile(r"\b(to recap|recap|in summary|to summari[sz]e|to sum (it )?up|as i (said|mentioned)|once again|"
                   r"let me repeat|quick reminder)\b", re.I)

# Rule thresholds shared with the findings (pipeline/predict/evidence.py). Engineering policies, not fitted.
SETUP_MIN_MS = 15_000          # A1: setup after the hook counts only when longer than this
PAYOFF_MIN_MS = 45_000         # A3: a title payoff is "delayed" only if later than this ...
PAYOFF_MIN_REL = 0.20          # ... AND later than this share of the duration


def _cw(text: str) -> set[str]:
    return {w for w in re.findall(r"[^\W_]+", text.lower()) if w not in _STOP and len(w) > 2}


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def build_features(T_ms: int, segments: list[dict], words: list[dict], structure: dict | None,
                   audio: dict | None = None, vad: list[dict] | None = None, *, shots: list[dict] | None = None,
                   ocr_tracks: list[dict] | None = None, voice_windows: list[dict] | None = None
                   ) -> tuple[list[dict[str, float]], dict]:
    T_s = max(1, math.ceil(T_ms / 1000))
    local: list[float | None] = []
    med = None
    F: list[dict[str, float]] = [{} for _ in range(T_s)]
    info: dict = {"sources": []}

    def put(a_ms: int, b_ms: int, key: str, v: float) -> None:
        for t in range(max(0, a_ms // 1000), min(T_s, math.ceil(b_ms / 1000))):
            overlap = max(0, min(b_ms, (t + 1) * 1000, T_ms) - max(a_ms, t * 1000))
            width = min(1000, T_ms - t * 1000)
            F[t][key] = max(F[t].get(key, 0.0), v * overlap / width if width else 0)

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
        rep.append(bool(tri) and len(tri & tri_seen) / len(tri) >= 0.5 and n < 0.25
                   and not ADVANCE.search(s["text"]) and not RECAP.search(s["text"]) and len(s["text"].split()) >= 6)
        seen |= cw
        tri_seen |= tri
    # repetition = a run of >= 2 consecutive sentences repeating earlier wording (same rule as the repetition
    # finding, E-01). One re-quoted line or a shared signpost phrase ("let's take a look at…") is not padding.
    i = 0
    while i < len(segs):
        j = i
        while j < len(segs) and rep[j]:
            j += 1
        if j - i >= 2 and announced_replay(segs, segs[i]["interval"]["start_ms"]) is None:
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
        if longest > 30 and re.search(r"[.!?]", s["text"]):
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
    if sub:  # the hook itself is not setup: the setup clock starts once the hook has been delivered
        setup_from = min(sub, st.get("hook_end_ms") or 0)
        if sub - setup_from > SETUP_MIN_MS:  # A1: a short setup is normal; only a long preamble is a risk
            put(setup_from, sub, "setup_before_substance", 1.0)
    hook = st.get("hook_ms")
    if structure is not None:
        put(0, min(30_000, hook if hook is not None else 30_000), "no_hook_yet", 1.0)
    for p in st.get("promises", []):
        first = p.get("first_fulfil_ms")
        if p.get("status") in ("fulfilled", "partial") and first and first > PAYOFF_MIN_MS and first > PAYOFF_MIN_REL * T_ms:
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
    measured_features(F, T_ms, info, shots=shots, ocr_tracks=ocr_tracks, audio=audio, vad=vad,
                      voice_windows=voice_windows, local_wpm=local, median_wpm=med)
    micro_variation(F, local, med, audio, shots, info)
    info["timing_quality"] = "aligned_words" if timed else "segment_timestamps"
    info["duration_ms"] = T_ms
    return F, info


def micro_variation(F: list[dict], local_wpm, median_wpm, audio, shots, info: dict, smooth_s: int = 5) -> None:
    """Per-second micro-variation in [-1, 1] (stored as micro_slowdown / micro_pickup) from measured moment-to-moment change (owner request: the
    curve should not look straight). NOT random: each second averages the available components, then a 5 s moving
    average is applied:
      pace      (median_wpm - local_wpm) / median_wpm         slower than this speaker's norm -> +, faster -> -
      loudness  (median_lufs - lufs) / 6 dB                     quieter than this video's norm  -> +, louder -> -
      visuals   -0.6 within 2 s of a cut, +0.3 after 8 s with no cut (only when shots exist)
    The model applies it with a small signed weight, so it shapes the curve without overriding the rule groups."""
    T_s = len(F)
    comps: list[list[float]] = [[] for _ in range(T_s)]
    used = []
    if local_wpm and median_wpm:
        for t in range(min(T_s, len(local_wpm))):
            if local_wpm[t] is not None:
                comps[t].append(max(-1.0, min(1.0, (median_wpm - local_wpm[t]) / median_wpm)))
        used.append("speech rate vs speaker median")
    loud = (audio or {}).get("loudness") or {}
    lt, lv = loud.get("short_term_t_ms") or [], loud.get("short_term_lufs") or []
    vals = [v for v in lv if isinstance(v, (int, float))]
    if vals:
        med_l = statistics.median(vals)
        for t_ms, v in zip(lt, lv):
            t = int(t_ms // 1000) - 1
            if isinstance(v, (int, float)) and 0 <= t < T_s:
                comps[t].append(max(-1.0, min(1.0, (med_l - v) / 6.0)))
        used.append("short-term loudness vs video median")
    if shots:
        starts = sorted(int(s.get("start_ms", s.get("interval", {}).get("start_ms", 0))) // 1000 for s in shots)
        last = -10 ** 9
        k = 0
        for t in range(T_s):
            while k < len(starts) and starts[k] <= t:
                last = starts[k]; k += 1
            nxt = starts[k] if k < len(starts) else 10 ** 9
            comps[t].append(-0.6 if min(t - last, nxt - t) <= 2 else 0.3 if t - last >= 8 else 0.0)
        used.append("cut timing")
    raw = [sum(c) / len(c) if c else 0.0 for c in comps]
    for t in range(T_s):
        w = raw[max(0, t - smooth_s // 2): t + smooth_s // 2 + 1]
        v = sum(w) / len(w) if w else 0.0
        if v >= 0.02:  # stored as two non-negative halves (the package schema requires features >= 0)
            F[t]["micro_slowdown"] = round(min(1.0, v), 4)
        elif v <= -0.02:
            F[t]["micro_pickup"] = round(min(1.0, -v), 4)
    if used:
        info["sources"].append("micro-variation from " + ", ".join(used))


def _quantile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))]


def _decay(F: list[dict], key: str, start_ms: int, length_s: int = 3) -> None:
    """Weak protective pulse: 1.0 in the second something new appears, fading over `length_s` seconds."""
    t0 = start_ms // 1000
    for k in range(length_s):
        if 0 <= t0 + k < len(F):
            F[t0 + k][key] = max(F[t0 + k].get(key, 0.0), 1.0 - k / length_s)


def measured_features(F: list[dict], T_ms: int, info: dict, *, shots=None, ocr_tracks=None, audio=None, vad=None,
                      voice_windows=None, local_wpm=None, median_wpm=None) -> None:
    """Optional measured signals (visual pacing, on-screen text, audio energy). Absent data -> feature off.

    Every threshold is relative to this video's own distribution (its median shot, its speaker's loudness and
    pitch variation), so the signals describe change within the video, never a universal ideal.
    """
    T_s = len(F)
    # --- visual pacing from shot cuts (video_scan shots.json: start_ms, end_ms, metrics.motion_mean)
    if shots:
        durs = [s["end_ms"] - s["start_ms"] for s in shots if s["end_ms"] > s["start_ms"]]
        motions = [s.get("metrics", {}).get("motion_mean") for s in shots]
        known = [m for m in motions if m is not None]
        med_shot = statistics.median(durs) if durs else 0
        low_motion = _quantile(known, 0.25) if len(known) >= 4 else None
        thr = max(8000, 3 * med_shot)
        long_shots = []
        for s, m in zip(shots, motions):
            a, b = s["start_ms"], s["end_ms"]
            if a > 0:
                _decay(F, "fresh_visual_change", a)
            if b - a > thr and m is not None and low_motion is not None and m <= low_motion:
                long_shots.append({"start_ms": a, "end_ms": b, "motion_mean": m})
                for t in range(max(0, math.ceil((a + thr) / 1000)), min(T_s, math.ceil(b / 1000))):
                    F[t]["long_static_shot"] = _clip(0.5 + 0.5 * (t * 1000 - a - thr) / thr)
        info["visual_pacing"] = {"shots": len(shots), "median_shot_s": round(med_shot / 1000, 2),
                                 "long_static_threshold_s": round(thr / 1000, 2),
                                 "low_motion_threshold": low_motion, "long_static_shots": len(long_shots),
                                 "long_static_list": long_shots}
        info["sources"].append(f"{len(shots)} shots (visual pacing)")
    else:
        info["sources"].append("no shot data: visual pacing features off")

    # --- on-screen text from OCR tracks (start_ms, end_ms, text, detector_confidence)
    if ocr_tracks:
        tracks = [t for t in ocr_tracks if (t.get("detector_confidence") or 0) >= 0.5 and len(t.get("text", "").strip()) >= 3]
        last_seen: dict[str, int] = {}
        new_n = 0
        for tr in sorted(tracks, key=lambda x: x["start_ms"]):
            key = " ".join(tr["text"].casefold().split())
            # text present from the first frame (watermark, persistent overlay) or flickering back is not new
            if tr["start_ms"] > 500 and tr["start_ms"] - last_seen.get(key, -10 ** 9) > 5000:
                _decay(F, "new_onscreen_text", tr["start_ms"])
                new_n += 1
            last_seen[key] = max(last_seen.get(key, 0), tr["end_ms"])
        dense_n = 0
        if median_wpm and local_wpm:
            for t in range(T_s):
                ms = t * 1000 + 500
                words_on = sum(len(tr["text"].split()) for tr in tracks if tr["start_ms"] <= ms < tr["end_ms"])
                x = local_wpm[t] if t < len(local_wpm) else None
                if words_on >= 12 and x is not None and x > 1.1 * median_wpm:
                    F[t]["dense_text_fast_speech"] = _clip(words_on / 24)
                    dense_n += 1
        info["onscreen_text"] = {"tracks_used": len(tracks), "new_text_events": new_n, "dense_text_fast_speech_s": dense_n,
                                 "dense_rule": ">=12 on-screen words while local speech > 1.1x speaker median"
                                               + ("" if median_wpm else " (off: no word timing)")}
        info["sources"].append(f"{len(tracks)} OCR text tracks (on-screen text)")
    else:
        info["sources"].append("no OCR tracks: on-screen text features off")

    # --- audio energy: short-term loudness (1/s, 3 s window) relative to this speaker's own median
    loud = (audio or {}).get("loudness") or {}
    L: list[float | None] = [None] * T_s
    for t_ms, v in zip(loud.get("short_term_t_ms") or [], loud.get("short_term_lufs") or []):
        if v is not None and 0 <= t_ms // 1000 < T_s:
            L[t_ms // 1000] = v
    speech = [False] * T_s
    if vad is not None:
        for v in vad:
            for t in range(max(0, v["start_ms"] // 1000), min(T_s, math.ceil(v["end_ms"] / 1000))):
                speech[t] = True
    sp_vals = [L[t] for t in range(T_s) if L[t] is not None and L[t] > -60 and (vad is None or speech[t])]
    if len(sp_vals) >= 20:
        l_med = statistics.median(sp_vals)

        def runs(cond, min_len):
            t = 0
            while t < T_s:
                u = t
                while u < T_s and cond(u):
                    u += 1
                if u - t >= min_len:
                    yield t, u
                t = max(u, t + 1)

        drop_n = lift_n = 0
        if vad is not None:  # "speech continues" must be measured, so a drop needs VAD
            def dropped(t):
                prev = [L[k] for k in range(max(0, t - 10), t) if L[k] is not None and speech[k]]
                return (speech[t] and L[t] is not None and not F[t].get("dead_air") and len(prev) >= 5
                        and L[t] <= statistics.median(prev) - 10)
            for a, b in runs(dropped, 3):
                for t in range(a, b):
                    F[t]["loudness_drop"] = 1.0
                drop_n += 1
        for a, b in runs(lambda t: L[t] is not None and (vad is None or speech[t]) and L[t] >= l_med + 4, 3):
            for t in range(a, b):
                F[t]["energy_lift"] = 1.0
            lift_n += 1
        flat_n = 0
        wins = [w for w in (voice_windows or []) if w.get("pitch_std_hz") is not None and (w.get("voiced_fraction") or 0) >= 0.3]
        if len(wins) >= 4:
            std_med = statistics.median(w["pitch_std_hz"] for w in wins)
            flags = []
            for w in wins:
                ls = [L[t] for t in range(w["start_ms"] // 1000, min(T_s, math.ceil(w["end_ms"] / 1000))) if L[t] is not None]
                flags.append(bool(ls) and w["pitch_std_hz"] < 0.6 * std_med and statistics.fmean(ls) < l_med - 3)
            i = 0
            while i < len(wins):  # sustained: at least two consecutive 10 s windows
                j = i
                while j < len(wins) and flags[j] and (j == i or wins[j]["start_ms"] == wins[j - 1]["end_ms"]):
                    j += 1
                if j - i >= 2:
                    for t in range(wins[i]["start_ms"] // 1000, min(T_s, math.ceil(wins[j - 1]["end_ms"] / 1000))):
                        F[t]["flat_low_energy"] = 1.0
                    flat_n += 1
                i = max(j, i + 1)
            info["sources"].append(f"{len(wins)} pitch windows (delivery variation)")
        else:
            info["sources"].append("no pitch windows: flat-delivery feature off")
        info["audio_energy"] = {"speaker_median_lufs": round(l_med, 2), "loudness_drops": drop_n, "energy_lifts": lift_n,
                                "flat_low_energy_stretches": flat_n,
                                "rules": "drop: >=10 LU below trailing 10 s speech median for >=3 s with VAD speech; "
                                         "lift: >=4 LU above speaker median for >=3 s; flat: pitch std <0.6x median and "
                                         "loudness >3 LU below median for >=2 consecutive 10 s windows"}
        info["sources"].append("short-term loudness (audio energy)")
    else:
        info["sources"].append("no short-term loudness: audio-energy features off")


def _bisect(xs: list[int], v: int) -> int:
    lo, hi = 0, len(xs)
    while lo < hi:
        mid = (lo + hi) // 2
        if xs[mid] < v:
            lo = mid + 1
        else:
            hi = mid
    return lo
