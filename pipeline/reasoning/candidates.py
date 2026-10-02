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
            self.add("slow_intro", 0, sub, self.ev_span(0, sub), [
                {"id": "O1", "operation": "cut", "interval": {"start_ms": st.get("intro_cut_start_ms", 0), "end_ms": sub},
                 "desc": f"cut the opening up to {mmss(sub)} where the topic starts"},
                {"id": "O2", "operation": "rewrite", "interval": {"start_ms": 0, "end_ms": min(sub, 15_000)},
                 "desc": "rewrite the first line into a concrete hook drawn from the video's own content"}],
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
        for i, sp in enumerate([s for s in st.get("spans", []) if s["kind"] == "tangent_candidate"][:MAX_PER_TYPE["tangent"]]):
            iv = sp["interval"]
            self.add("tangent", iv["start_ms"], iv["end_ms"], self.ev_span(iv["start_ms"], iv["end_ms"]), [
                {"id": "O1", "operation": "cut", "interval": iv, "desc": f"cut {mmss(iv['start_ms'])}-{mmss(iv['end_ms'])}"},
                {"id": "O2", "operation": "rewrite", "interval": iv, "desc": "condense into one sentence that links back to the topic"}],
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
        for pair in self.c["pairs"][:MAX_PER_TYPE["unnecessary_repetition"]]:
            e, l = self.chunk(pair["earlier"]), self.chunk(pair["later"])
            in_recap = any(_ov(l["start_ms"], l["end_ms"], r["start_ms"], r["end_ms"]) for r in recap_spans)
            self.add("unnecessary_repetition", l["start_ms"], l["end_ms"], self.ev_chunk(pair["later"])[:4] + self.ev_chunk(pair["earlier"])[:3], [
                {"id": "O1", "operation": "cut", "interval": {"start_ms": l["start_ms"], "end_ms": l["end_ms"]},
                 "desc": f"cut the later passage {mmss(l['start_ms'])}-{mmss(l['end_ms'])}"},
                {"id": "O2", "operation": "rewrite", "interval": {"start_ms": l["start_ms"], "end_ms": l["end_ms"]},
                 "desc": "replace the repeated passage with one new example or a one-line callback"}],
                f"semantic similarity {pair['cosine']} with {mmss(e['start_ms'])}-{mmss(e['end_ms'])}"
                + ("; the later passage sits in a recap/outro (may be intentional)" if in_recap else ""),
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
                {"id": "O1", "operation": "cut", "interval": bl, "desc": "cut the black frames"},
                {"id": "O2", "operation": "insert_visual", "interval": bl, "desc": "cover with the relevant visual"}],
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
