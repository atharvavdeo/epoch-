"""Deterministic issue candidates with fixed intervals, evidence and edit options.

Every candidate carries: a measured affected interval (the LLM never moves
it), numbered evidence items (E..) that map to Evidence records, and edit
options (O1/O2) whose intervals are computed here. Thresholds are FEATURES
"candidate retrieval defaults" (engineering priors, review triggers only).
"""

from __future__ import annotations

import statistics

from contracts.common import evidence_id

PAUSE_MIN_MS = 2000
INTRO_MIN_MS = 20_000
PAYOFF_MIN_MS = 60_000
STATIC_SHOT_MIN_MS = 15_000
MAX_PER_TYPE = {"dead_air": 6, "technical_audio_fault": 3, "technical_visual_fault": 4, "unnecessary_repetition": 6,
                "rushed_delivery": 3, "visual_stagnation": 6, "tangent": 4, "disruptive_cta": 3}


def mmss(ms: int) -> str:
    s = ms / 1000
    return f"{int(s // 60)}:{s % 60:04.1f}"


class EvidenceBook:
    """Numbered evidence items shown to the LLM and their Evidence records."""

    def __init__(self, asset_id: str):
        self.asset_id = asset_id
        self.records: dict[str, dict] = {}

    def transcript(self, seg: dict) -> str:
        eid = evidence_id("transcript", seg["segment_id"], self.asset_id)
        self.records.setdefault(eid, {"evidence_id": eid, "asset_id": self.asset_id, "kind": "transcript",
                                      "ref_id": seg["segment_id"], "interval": seg["interval"],
                                      "precision": seg["precision"], "provenance_stage_id": "align", "quote": None,
                                      "_text": seg["text"]})
        return eid

    def signal(self, key: str, interval: dict, text: str, stage: str = "measurements") -> str:
        eid = evidence_id("signal", key, self.asset_id)
        interval = {"start_ms": int(interval["start_ms"]), "end_ms": int(interval["end_ms"])}  # contract: start/end only
        self.records.setdefault(eid, {"evidence_id": eid, "asset_id": self.asset_id, "kind": "signal", "ref_id": key,
                                      "interval": interval, "precision": "frame" if stage == "video_scan" else "segment",
                                      "provenance_stage_id": stage, "quote": None, "_text": text})
        return eid

    def existing(self, eid: str) -> str:
        return eid


def _ov(a0, a1, b0, b1) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


class CandidateBuilder:
    def __init__(self, ctx: dict):
        self.c = ctx
        self.book: EvidenceBook = ctx["book"]
        self.items: list[dict] = []

    # helpers -------------------------------------------------------------
    def snap_to_sentences(self, iv: dict) -> dict:
        """Move edit boundaries to sentence boundaries using aligned word times (ASR segments break mid-sentence).
        Start moves back to the first word after the previous . ? !; end moves forward to the next word ending in
        . ? !. Unaligned words leave that boundary unchanged."""
        words = [w for w in self.c.get("words", []) if w.get("start_ms") is not None]
        if not words:
            return dict(iv)
        a, b = iv["start_ms"], iv["end_ms"]
        ends = lambda w: w["text"].rstrip("\"')”").endswith((".", "?", "!"))  # noqa: E731
        before = [w for w in words if w["start_ms"] < a]
        first_in = next((w for w in words if w["start_ms"] >= a), None)
        if before and not ends(before[-1]):
            k = len(before) - 1
            while k > 0 and not ends(before[k - 1]):
                k -= 1
            a = before[k]["start_ms"]
        elif first_in:
            a = first_in["start_ms"]
        inside = [w for w in words if a <= w["start_ms"] < b]
        if inside and not ends(inside[-1]):
            nxt = next((w for w in words if w["start_ms"] >= b and ends(w)), None)
            if nxt and nxt["end_ms"] - b <= 15_000:
                b = nxt["end_ms"]
        elif inside:
            b = inside[-1]["end_ms"]
        return {"start_ms": a, "end_ms": b}

    def _first_seg_iv(self, iv: dict) -> dict:
        segs = self.segs_in(iv["start_ms"], iv["end_ms"])
        return dict(segs[0]["interval"]) if segs else dict(iv)

    def segs_in(self, a: int, b: int) -> list[dict]:
        return [s for s in self.c["segments"] if _ov(s["interval"]["start_ms"], s["interval"]["end_ms"], a, b)]

    def chunk(self, cid: str) -> dict:
        return self.c["chunk_by_id"][cid]

    def ev_chunk(self, cid: str) -> list[tuple[str, str]]:
        ch = self.chunk(cid)
        segs = [self.c["seg_by_id"][s] for s in ch["segment_ids"]]
        return [(self.book.transcript(s), f"[{mmss(s['interval']['start_ms'])}-{mmss(s['interval']['end_ms'])}] \"{s['text']}\"")
                for s in segs]

    def ev_span(self, a: int, b: int, limit: int = 6) -> list[tuple[str, str]]:
        return [(self.book.transcript(s), f"[{mmss(s['interval']['start_ms'])}-{mmss(s['interval']['end_ms'])}] \"{s['text']}\"")
                for s in self.segs_in(a, b)[:limit]]

    def ev_visual(self, a: int, b: int, kinds: tuple[str, ...] | None = None, limit: int = 3) -> list[tuple[str, str]]:
        out = []
        for o in self.c.get("observations", []):
            if kinds and o["_kind"] not in kinds:
                continue
            if _ov(o["interval"]["start_ms"], o["interval"]["end_ms"], a, b) and o["status"] != "unknown":
                out.append((self.c["obs_ev"][o["observation_id"]], f"[visual {mmss(o['interval']['start_ms'])}] {o['statement']}"))
        return out[:limit]

    def add(self, type_: str, a: int, b: int, evidence: list[tuple[str, str]], options: list[dict], note: str,
            comparison: dict | None = None, absence: bool = False):
        T = self.c["duration_ms"]
        a, b = max(0, a), min(T, b)
        if b <= a or not evidence:
            return
        for it in self.items:  # one defect span = one candidate (issue ids derive from type + interval)
            if it["type"] == type_ and it["interval"] == {"start_ms": a, "end_ms": b}:
                it["evidence"] += [e for e in evidence if e[0] not in {x[0] for x in it["evidence"]}]
                it["note"] = f"{it['note']}; {note}"
                return
        self.items.append({"type": type_, "interval": {"start_ms": a, "end_ms": b}, "evidence": evidence,
                           "options": options, "note": note, "comparison": comparison, "absence": absence})

    # generators ----------------------------------------------------------
    def build(self) -> list[dict]:
        st = self.c["structure"]
        T = self.c["duration_ms"]
        sub = st.get("first_substance_ms")
        if sub is not None and sub >= INTRO_MIN_MS:
            hook = st.get("hook_ms")
            # edits keep the hook: only the setup between the end of the hook and the first point is touched
            h_end = st.get("hook_end_ms")
            setup = {"start_ms": h_end if h_end is not None and h_end < sub else 0, "end_ms": sub}
            setup = self.snap_to_sentences(setup)
            self.add("slow_intro", 0, sub, self.ev_span(0, sub), [
                {"id": "O1", "operation": "rewrite", "interval": setup,
                 "desc": f"tighten the setup {mmss(setup['start_ms'])}-{mmss(setup['end_ms'])} after the hook; keep the hook "
                         "and every point, only remove words"},
                {"id": "O2", "operation": "cut", "interval": setup,
                 "desc": f"cut the setup {mmss(setup['start_ms'])}-{mmss(setup['end_ms'])} so the first point follows the hook"}],
                f"substantive content starts at {mmss(sub)}" + (f"; hook at {mmss(hook)}" if hook is not None else "; no hook found"))
        for p in st.get("promises", []):
            first = p.get("first_fulfil_ms")
            if p["status"] in ("fulfilled", "partial") and first is not None and first >= PAYOFF_MIN_MS:
                f_iv = p.get("first_delivery_interval") or p["fulfil_interval"]
                ev = self.ev_span(f_iv["start_ms"], f_iv["end_ms"], 3) + self.ev_span(0, min(T, 20_000), 2)
                self.add("delayed_payoff", 0, first, ev, [
                    {"id": "O1", "operation": "move", "interval": f_iv, "destination_ms": st.get("hook_ms") or 0,
                     "desc": f"move the first payoff ({mmss(f_iv['start_ms'])}-{mmss(f_iv['end_ms'])}) to the opening"},
                    {"id": "O2", "operation": "rewrite", "interval": {"start_ms": 0, "end_ms": min(15_000, T)},
                     "desc": "add an opening line that previews the payoff using the speaker's own words"}],
                    f"title promise \"{p['obligation']}\" first addressed at {mmss(first)}")
            elif p["status"] in ("unaddressed", "uncertain"):
                s0 = p.get("setup_ms") or 0
                ev = self.ev_span(s0, s0 + 20_000, 2) + self.ev_span(max(0, T - 60_000), T, 3)
                self.add("unresolved_promise", s0, T, ev, [
                    {"id": "O1", "operation": "rewrite", "interval": self.c["last_chunk_iv"],
                     "desc": "close the loop in the ending with a line that answers the promise from material already in the video"}],
                    f"title promise \"{p['obligation']}\" judged {p['status']} by the structure pass", absence=True)
        # A tangent label from the structure pass must be backed by measurement: the span's paragraphs must be
        # title-relevance outliers (> 2.5 robust deviations below the video's median e5 title similarity).
        # A "lowest quarter" rule always flags something; on the test video it flagged the core lesson.
        tc = sorted(c["title_cos"] for c in self.c["chunk_by_id"].values() if "title_cos" in c)
        q1 = None
        if len(tc) >= 6:
            med = tc[len(tc) // 2]
            mad = sorted(abs(x - med) for x in tc)[len(tc) // 2]
            q1 = med - 2.5 * max(mad, 0.005)
        tangents = []
        for sp in [s for s in st.get("spans", []) if s["kind"] == "tangent_candidate"]:
            cs = [c["title_cos"] for c in self.c["chunk_by_id"].values() if "title_cos" in c
                  and _ov(c["start_ms"], c["end_ms"], sp["interval"]["start_ms"], sp["interval"]["end_ms"])]
            if q1 is not None and cs and max(cs) < q1:
                tangents.append({**sp, "note": f"{sp.get('note', '')}; title relevance {max(cs):.3f} is an outlier "
                                               f"for this video (threshold {q1:.3f})"})
        for i, sp in enumerate(tangents[:MAX_PER_TYPE["tangent"]]):
            iv = sp["interval"]
            self.add("tangent", iv["start_ms"], iv["end_ms"], self.ev_span(iv["start_ms"], iv["end_ms"]), [
                {"id": "O1", "operation": "cut", "interval": iv, "desc": f"cut {mmss(iv['start_ms'])}-{mmss(iv['end_ms'])}"},
                {"id": "O2", "operation": "rewrite", "interval": self._first_seg_iv(iv),
                 "desc": "rewrite only the first sentence to add a bridge back to the title topic; keep the rest"}],
                sp.get("note", "possible drift from the title topic"))
        ctas = [s for s in st.get("spans", []) if s["kind"] in ("cta", "sponsor")]
        for sp in ctas[:MAX_PER_TYPE["disruptive_cta"]]:
            iv = sp["interval"]
            if iv["start_ms"] > T - 45_000:
                continue  # end-of-video CTA is conventional placement
            dest = max(sub or 0, min(T - 1, (sub or 0) + 60_000))
            self.add("disruptive_cta", iv["start_ms"], iv["end_ms"], self.ev_span(iv["start_ms"], iv["end_ms"]), [
                {"id": "O1", "operation": "move", "interval": iv, "destination_ms": T - 1 if iv["start_ms"] < (sub or 0) else dest,
                 "desc": "move the call-to-action later, after the first payoff or to the end"},
                {"id": "O2", "operation": "cut", "interval": iv, "desc": "cut it"}],
                f"{sp['kind']} at {mmss(iv['start_ms'])}")
        recap_spans = [s["interval"] for s in st.get("spans", []) if s["kind"] in ("recap", "outro")]
        n_rep = 0
        for pair in self.c["pairs"]:
            if n_rep >= MAX_PER_TYPE["unnecessary_repetition"]:
                break
            e, l = self.chunk(pair["earlier"]), self.chunk(pair["later"])
            run = repeated_run(e, l, self.c["seg_by_id"])
            if run is None:  # same topic, new wording: not a repetition (embedding similarity is retrieval only)
                continue
            n_rep += 1
            segs = [self.c["seg_by_id"][x] for x in run]
            iv = self.snap_to_sentences({"start_ms": segs[0]["interval"]["start_ms"], "end_ms": segs[-1]["interval"]["end_ms"]})
            a, b = iv["start_ms"], iv["end_ms"]
            in_recap = any(_ov(a, b, r["start_ms"], r["end_ms"]) for r in recap_spans)
            ev = self.ev_span(max(0, a - 6000), a, 1) + [(self.book.transcript(s), f"[{mmss(s['interval']['start_ms'])}-"
                                                         f"{mmss(s['interval']['end_ms'])}] \"{s['text']}\"") for s in segs[:5]]
            self.add("unnecessary_repetition", a, b, ev + self.ev_chunk(pair["earlier"])[:3], [
                {"id": "O1", "operation": "cut", "interval": iv,
                 "desc": f"cut only the repeated sentences {mmss(a)}-{mmss(b)}; everything around them stays"},
                {"id": "O2", "operation": "rewrite", "interval": iv,
                 "desc": "replace only the repeated sentences with a one-line callback"}],
                f"{len(run)} consecutive sentences repeat the wording of {mmss(e['start_ms'])}-{mmss(e['end_ms'])}; "
                "the first evidence line is the sentence just before (it may announce an intentional replay)"
                + ("; inside a recap/outro (may be intentional)" if in_recap else ""),
                comparison={"start_ms": e["start_ms"], "end_ms": e["end_ms"]})
        for p in sorted(self.c["pauses"], key=lambda x: -(x["end_ms"] - x["start_ms"]))[:MAX_PER_TYPE["dead_air"]]:
            a, b = p["start_ms"], p["end_ms"]
            ev = [(self.book.signal(f"pause:{a}:{b}", {"start_ms": a, "end_ms": b},
                                    f"no speech {mmss(a)}-{mmss(b)} ({(b - a) / 1000:.1f} s; {p['source']})", "audio"),
                   f"[measured] no speech from {mmss(a)} to {mmss(b)} ({(b - a) / 1000:.1f} s), source: {p['source']}")]
            ev += self.ev_visual(a, b) + self.ev_span(max(0, a - 4000), a, 1)
            self.add("dead_air", a, b, ev, [
                {"id": "O1", "operation": "cut", "interval": {"start_ms": a + 300, "end_ms": max(a + 301, b - 300)},
                 "desc": f"trim the pause, keeping 0.3 s each side (removes {(b - a - 600) / 1000:.1f} s)"},
                {"id": "O2", "operation": "insert_visual", "interval": {"start_ms": a, "end_ms": b},
                 "desc": "keep the pause but cover it with a relevant visual"}],
                "pause may be intentional emphasis or a demonstration")
        for r in self.c["rushed"][:MAX_PER_TYPE["rushed_delivery"]]:
            ch = self.chunk(r["chunk_id"])
            self.add("rushed_delivery", ch["start_ms"], ch["end_ms"], self.ev_chunk(r["chunk_id"])[:4] + [
                (self.book.signal(f"wpm:{r['chunk_id']}", {"start_ms": ch["start_ms"], "end_ms": ch["end_ms"]},
                                  f"{r['wpm']} words/min", "align"), f"[measured] speech rate {r['wpm']} words/min "
                 f"(video median {r['median']})")], [
                {"id": "O1", "operation": "rewrite", "interval": {"start_ms": ch["start_ms"], "end_ms": ch["end_ms"]},
                 "desc": "split the dense passage into shorter sentences or remove a non-essential detail"}],
                f"speech rate {r['wpm']} wpm vs median {r['median']}")
        for w in self.c["clip_windows"][:MAX_PER_TYPE["technical_audio_fault"]]:
            ev = [(self.book.signal(f"clip:{w['start_ms']}:{w['end_ms']}", w, f"clipped samples {w['fraction']:.2%}", "audio"),
                   f"[measured] {w['fraction']:.2%} of samples at full scale in {mmss(w['start_ms'])}-{mmss(w['end_ms'])}"
                   + (f"; whole-video true peak {self.c['true_peak']} dBFS" if self.c.get("true_peak") is not None else ""))]
            self.add("technical_audio_fault", w["start_ms"], w["end_ms"], ev, [  # w also carries "fraction"
                {"id": "O1", "operation": "adjust_audio", "interval": {"start_ms": w["start_ms"], "end_ms": w["end_ms"]},
                 "desc": "reduce gain / apply a limiter so peaks stay below 0 dBFS"}], "clipping can be audible distortion")
        for bl in self.c["black"][:MAX_PER_TYPE["technical_visual_fault"]]:
            a, b = bl["start_ms"], bl["end_ms"]
            if a < 1000 or b > T - 1000:
                continue  # fades at the very start/end are conventional
            ev = [(self.book.signal(f"black:{a}:{b}", bl, "black frames", "video_scan"),
                   f"[measured] black picture {mmss(a)}-{mmss(b)} ({(b - a) / 1000:.1f} s)")] + self.ev_span(a, b, 2)
            self.add("technical_visual_fault", a, b, ev, [
                {"id": "O1", "operation": "insert_visual", "interval": bl,
                 "desc": "replace the black frames with the neighbouring shot; audio untouched"}]
                + ([] if self.segs_in(a, b) else [{"id": "O2", "operation": "cut", "interval": bl,
                                                    "desc": "cut the black frames (no speech over them)"}]),
                "black frames mid-video (could be an intentional transition)")
        for o in [o for o in self.c.get("observations", []) if o["_kind"] == "technical_visual"][:2]:
            iv = o["interval"]
            self.add("technical_visual_fault", iv["start_ms"], iv["end_ms"], self.ev_visual(iv["start_ms"], iv["end_ms"], ("technical_visual",)), [
                {"id": "O1", "operation": "insert_visual", "interval": iv, "desc": "replace the affected shot"}],
                "visual technical issue reported on sampled frames (provisional)")
        for sh in self.c["long_static_shots"][:MAX_PER_TYPE["visual_stagnation"]]:
            a, b = sh["start_ms"], sh["end_ms"]
            vis = self.ev_visual(a, b, ("static_visual", "speech_visual_relation", "observation"), 3)
            if not vis:
                continue  # without visual inspection a long shot is only a measurement (X04)
            ev = [(self.book.signal(f"shot:{a}:{b}", {"start_ms": a, "end_ms": b}, "long low-motion shot", "video_scan"),
                   f"[measured] single shot {mmss(a)}-{mmss(b)} ({(b - a) / 1000:.1f} s), low frame change")] + vis + self.ev_span(a, b, 3)
            self.add("visual_stagnation", a, b, ev, [
                {"id": "O1", "operation": "insert_visual", "interval": {"start_ms": a, "end_ms": b},
                 "desc": "add a visual that shows what is being explained (diagram, b-roll, on-screen text)"},
                {"id": "O2", "operation": "cut", "interval": {"start_ms": a, "end_ms": b}, "desc": "tighten the shot"}],
                "a still picture can be useful when it carries the explanation")
        return self.items


_STOP = set("the a an and or but to of in on for is it that this with as at be are was so you i he his we they my your "
             "our its by from".split())
REPEAT = {"trigram_overlap": 0.5, "min_run": 2}


def _content_trigrams(text: str) -> set[tuple[str, ...]]:
    import re

    w = [x for x in re.findall(r"[^\W_]+(?:'[^\W_]+)?", text.lower()) if x not in _STOP]
    return {tuple(w[i:i + 3]) for i in range(len(w) - 2)}


def repeated_run(earlier: dict, later: dict, seg_by_id: dict, cfg: dict = REPEAT) -> list[str] | None:
    """Longest run of consecutive later segments whose content-word trigrams mostly occur in the earlier
    paragraph. Measured on this project's test video: same-topic paragraphs score 0 and true repeats 0.6-1.0,
    while sentence embeddings scored both ~0.85 (no usable threshold)."""
    E = set().union(*(_content_trigrams(seg_by_id[x]["text"]) for x in earlier["segment_ids"])) if earlier["segment_ids"] else set()
    best, cur = [], []
    for sid in later["segment_ids"]:
        T = _content_trigrams(seg_by_id[sid]["text"])
        if T and len(T & E) / len(T) >= cfg["trigram_overlap"]:
            cur.append(sid)
            best = max(best, cur, key=len)
        else:
            cur = []
    return list(best) if len(best) >= cfg["min_run"] else None


QUIET = {"floor_dbfs": -45.0, "below_speech_db": 20.0, "min_quiet_frac": 0.6}


def _quiet_frac(rms: dict | None, a: int, b: int, threshold: float) -> float | None:
    if not rms:
        return None
    vals = [d if d is not None else -120.0 for t, d in zip(rms["t_ms"], rms["dbfs"]) if a <= t < b]
    return sum(v < threshold for v in vals) / len(vals) if vals else None


def find_pauses(vad: list[dict] | None, silence: list[dict], T: int, rms: dict | None = None) -> list[dict]:
    """Quiet gaps >= 2 s: waveform silence, plus VAD no-speech gaps that are actually quiet.

    A VAD gap only means nobody is talking. When the waveform there is as loud as
    speech (a played clip, music, sound effects) it is not dead air, so it is
    kept only if >= 60% of its RMS windows fall below max(-45 dBFS, speech
    median - 20 dB). Without an RMS envelope the VAD gap is kept (unknown != loud).
    """
    speech_vals = [d for s in (vad or []) for t, d in zip((rms or {}).get("t_ms", []), (rms or {}).get("dbfs", []))
                   if d is not None and s["start_ms"] <= t < s["end_ms"]]
    threshold = QUIET["floor_dbfs"]
    if speech_vals:
        threshold = max(threshold, sorted(speech_vals)[len(speech_vals) // 2] - QUIET["below_speech_db"])
    gaps = []
    if vad:
        prev = 0
        for v in vad + [{"start_ms": T, "end_ms": T}]:
            if v["start_ms"] - prev >= PAUSE_MIN_MS:
                qf = _quiet_frac(rms, prev, v["start_ms"], threshold)
                if qf is None or qf >= QUIET["min_quiet_frac"]:
                    gaps.append({"start_ms": prev, "end_ms": v["start_ms"], "source": "no speech detected (VAD), quiet waveform"
                                 if qf is not None else "no speech detected (VAD)"})
            prev = v["end_ms"]
    for s in silence:
        if s["end_ms"] - s["start_ms"] >= PAUSE_MIN_MS:
            gaps.append({**s, "source": "waveform silence below -50 dB"})
    gaps.sort(key=lambda g: g["start_ms"])
    merged: list[dict] = []
    for g in gaps:
        if merged and g["start_ms"] <= merged[-1]["end_ms"]:
            merged[-1]["end_ms"] = max(merged[-1]["end_ms"], g["end_ms"])
            if g["source"] not in merged[-1]["source"]:
                merged[-1]["source"] += " + " + g["source"]
        else:
            merged.append(dict(g))
    # ignore the first/last second (natural lead-in/out)
    return [g for g in merged if g["start_ms"] >= 1000 and g["end_ms"] <= T - 1000]


def speech_rates(chunks: list[dict], words_by_seg: dict, seg_by_id: dict) -> list[dict]:
    rates = []
    for ch in chunks:
        segs = [seg_by_id[s] for s in ch["segment_ids"]]
        n = sum(len(s["text"].split()) for s in segs)
        dur = sum(s["interval"]["end_ms"] - s["interval"]["start_ms"] for s in segs) / 60000
        if dur > 0.15:
            rates.append({"chunk_id": ch["chunk_id"], "wpm": round(n / dur), "precision": ch["precision"]})
    if not rates:
        return []
    med = statistics.median(r["wpm"] for r in rates)
    for r in rates:
        r["median"] = round(med)
    return rates


def merge_clip_windows(windows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for w in sorted(windows, key=lambda x: x["start_ms"]):
        if out and w["start_ms"] - out[-1]["end_ms"] <= 2000:
            out[-1]["end_ms"] = w["end_ms"]
            out[-1]["fraction"] = max(out[-1]["fraction"], w["fraction"])
        else:
            out.append(dict(w))
    return sorted(out, key=lambda x: -x["fraction"])
