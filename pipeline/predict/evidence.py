"""Reviewable rule findings. These are candidates, never automatic rewrite verdicts.

Rule families -> cause groups (owner design, 2026-10-03):
  A opening/promise   A1 long preamble after the hook, A2 no hook identified, A3 delayed title payoff,
                      A4 unconfirmed title promise
  B progress          B1 repetition, B2 low novelty, B3 topic drift without a link back
  C comprehension     C1 long sentences, C2 term used before explanation, C3 dense new terms, C4 extended abstraction
  D questions/payoff  D1 question without (timely) callback, D2 new open questions while earlier ones are open
  E interruptions     E1 CTA before the first payoff, E2 sponsor / mid-video interruption, E3 extended outro,
                      E4 redundant recap
  V delivery          V1 slow pace, V2 fast pace, V3 filler cluster, V4 dead air

Every finding quotes the passage, states its measurements, explains the mechanism in plain words, gives a
counter-explanation, a concrete suggestion and what must be preserved. Evidence strength is `supported` only when
the rule's condition is a direct measurement of this transcript/audio (verbatim overlap, word counts, waveform
silence); anything resting on narrative extraction or lexical matching is `provisional`.
"""
from __future__ import annotations

import re

from pipeline.predict.features import (ADVANCE, CONCRETE, PAYOFF_MIN_MS, PAYOFF_MIN_REL, RECAP, SETUP_MIN_MS, _cw)
from pipeline.predict.model import GROUP_LABELS
from pipeline.reasoning.candidates import _content_trigrams

# rule_id -> (rule_code, cause_group, creator-facing title, safe_edit, edit_kind, scenario feature or None)
RULES: dict[str, tuple[str, str, str, bool, str, str | None]] = {
    "long_preamble": ("A1", "opening_promise", "Long setup before the first point", False, "move", "setup_before_substance"),
    "no_hook_identified": ("A2", "opening_promise", "No hook identified in the opening", False, "insert", "no_hook_yet"),
    "delayed_title_payoff": ("A3", "opening_promise", "Title payoff arrives late", False, "move", "payoff_pending"),
    "unconfirmed_title_promise": ("A4", "opening_promise", "Title promise not confirmed", False, "confirm", None),
    "repetition": ("B1", "progress", "Repeats an earlier passage", True, "trim", "repetition"),
    "low_novelty": ("B2", "progress", "Few new ideas in this stretch", False, "rewrite", "low_novelty"),
    "topic_drift": ("B3", "progress", "Possible detour without a link back", False, "insert", None),
    "long_sentences": ("C1", "comprehension", "Very long sentence", True, "rewrite", "long_sentences"),
    "term_used_before_explanation": ("C2", "comprehension", "Term used before it is explained", False, "move", None),
    "dense_new_terms": ("C3", "comprehension", "Many new terms at once", False, "rewrite", None),
    "extended_abstraction": ("C4", "comprehension", "Long stretch without an example", False, "insert", None),
    "question_without_callback": ("D1", "questions_payoff", "Question without a clear answer", False, "confirm", None),
    "delayed_question_callback": ("D1", "questions_payoff", "Answer arrives much later than the question", False, "confirm", None),
    "stacked_open_questions": ("D2", "questions_payoff", "New questions while earlier ones are still open", False, "rewrite", None),
    "cta_before_payoff": ("E1", "interruptions", "Call to action before the first payoff", True, "move", "cta_or_sponsor"),
    "mid_video_interruption": ("E2", "interruptions", "Sponsor or mid-video interruption", True, "move", "cta_or_sponsor"),
    "extended_outro": ("E3", "interruptions", "Long ending after the content", True, "trim", "outro"),
    "redundant_recap": ("E4", "interruptions", "Recap repeats what was already said", True, "trim", "outro"),
    "slow_pace": ("V1", "delivery", "Noticeably slower delivery", False, "review", "slow_pace"),
    "fast_pace": ("V2", "delivery", "Noticeably faster delivery", False, "review", "fast_pace"),
    "filler_density": ("V3", "delivery", "Cluster of filler words", True, "trim", "filler_density"),
    "dead_air": ("V4", "delivery", "Quiet gap with no speech", True, "trim", "dead_air"),
    "flat_low_energy": ("V5", "delivery", "Flatter, quieter delivery than usual", False, "review", "flat_low_energy"),
    "loudness_drop": ("V6", "delivery", "Sudden drop in audio level", True, "audio_fix", "loudness_drop"),
    "dense_text_fast_speech": ("C5", "comprehension", "Dense on-screen text during fast speech", False, "review", "dense_text_fast_speech"),
    "long_static_shot": ("S1", "visual_pacing", "One static shot held for a long time", False, "insert", "long_static_shot"),
}

PRESERVE_DEFAULT = "Keep every new point, example, qualification, question and transition in this passage."
CONNECT_BACK = re.compile(r"\b(back to|brings? (us|it|this) back|which (brings|ties|connects|leads)|the reason i mention|"
                          r"relates? to|connects? (to|back)|how does (this|that) (relate|connect)|anyway|so what does this mean)\b", re.I)


def mmss(ms: float) -> str:
    s = int(ms // 1000)
    return f"{s // 60}:{s % 60:02d}"


def _overlapping(segments: list[dict], a: int, b: int) -> list[dict]:
    return [s for s in segments if s["interval"]["start_ms"] < b and s["interval"]["end_ms"] > a]


def make_finding(rule_id: str, a: int, b: int, segments: list[dict], *, severity: str, evidence: str,
                 mechanism: str, suggestion: str, counter: str, measurements: dict, preserve: str = PRESERVE_DEFAULT,
                 quote: str | None = None, earlier: dict | None = None, later: list | None = None,
                 scored: bool | None = None, title: str | None = None) -> dict:
    code, group, default_title, safe, kind, feature = RULES[rule_id]
    source = _overlapping(segments, a, b)
    needs = kind not in ("trim", "audio_fix")  # rewrites, moves, insertions, confirmations change meaning: re-run
    return {
        "finding_id": f"{rule_id}:{a}:{b}", "rule_id": rule_id, "rule_code": code, "rule_family": code[0],
        "cause_group": group, "group_label": GROUP_LABELS[group], "title": title or default_title,
        "start_ms": int(a), "end_ms": int(b), "status": "candidate", "severity": severity, "evidence_strength": evidence,
        "quote": quote if quote is not None else " ".join(s["text"] for s in source),
        "source_segment_ids": [s.get("segment_id", s.get("id")) for s in source if s.get("segment_id", s.get("id"))],
        "earlier_quote": (earlier or {}).get("quote"), "earlier_start_ms": (earlier or {}).get("start_ms"),
        "earlier_end_ms": (earlier or {}).get("end_ms"), "later_answer_candidates": later or [],
        "measurements": {**measurements, "affected_duration_s": round((b - a) / 1000, 3)},
        "mechanism": mechanism, "counter_explanation": counter, "suggestion": suggestion, "preserve": preserve,
        "safe_edit": safe, "edit_kind": kind, "needs_reanalysis": needs, "requires_reanalysis": needs,
        "scenario_feature": feature, "scored_in_scenario": feature is not None if scored is None else scored,
        "acceptance": "Review the quote and the alternative explanation before accepting; this rule does not establish abandonment.",
    }


def _runs(features: list[dict], key: str):
    t = 0
    while t < len(features):
        if not features[t].get(key):
            t += 1
            continue
        end = t + 1
        while end < len(features) and features[end].get(key):
            end += 1
        yield t, end
        t = end


def _best_earlier(text: str, previous: list[dict]) -> tuple[float, dict | None]:
    tri = _content_trigrams(text)
    best = (0.0, None)
    for s in previous:
        if tri:
            o = len(tri & _content_trigrams(s["text"])) / len(tri)
            if o > best[0]:
                best = (o, s)
    return best


def _step_down(severity: str) -> str:
    return {"high": "medium", "medium": "low"}.get(severity, "low")


def build_evidence(features: list[dict], segments: list[dict], duration_ms: int, info: dict,
                   structure: dict | None = None) -> dict:
    """Findings from per-second feature runs (A1, A2, B1, B2, C1, V1-V4) and narrative structure (A3, B3, E1-E4)."""
    segs = sorted(segments, key=lambda s: s["interval"]["start_ms"])
    st = structure or {}
    findings: list[dict] = []
    for key in ("setup_before_substance", "no_hook_yet", "repetition", "low_novelty", "long_sentences",
                "slow_pace", "fast_pace", "filler_density", "dead_air", "flat_low_energy", "loudness_drop",
                "dense_text_fast_speech", "long_static_shot"):
        for t, end in _runs(features, key):
            a, b = t * 1000, min(duration_ms, end * 1000)
            strength = max(features[x].get(key, 0) for x in range(t, end))
            source = _overlapping(segs, a, b)
            quote = " ".join(s["text"] for s in source)
            dur = (b - a) / 1000
            m = {"feature_strength": round(strength, 4)}
            if key == "setup_before_substance":
                sev = "low" if dur <= 30 else "medium" if dur <= 60 else "high"
                findings.append(make_finding(
                    "long_preamble", a, b, segs, severity=sev, evidence="provisional",
                    mechanism=f"After the hook, {dur:.0f} s pass before the first substantive point at {mmss(b)}. "
                              "Viewers who came for the title's promise may not wait that long.",
                    suggestion="Bring the first useful point (or a one-line preview of it) forward, then return to the setup.",
                    counter="The setup may supply prerequisites the main point depends on; narrative extraction can misplace the first substantive point.",
                    preserve="Keep the hook and any prerequisite the first point depends on.",
                    measurements={**m, "setup_s": dur, "threshold_s": SETUP_MIN_MS / 1000, "first_substance_ms": b,
                                  "detector": "Narrative structure: hook end to first substance; requires review"}))
            elif key == "no_hook_yet":
                if b - a < 5000:
                    continue
                hook = st.get("hook_ms")
                late = hook is not None
                findings.append(make_finding(
                    "no_hook_identified", a, b, segs, severity="low" if late else "medium", evidence="provisional",
                    title=f"Hook identified only at {mmss(hook)}" if late else None,
                    mechanism=(f"No hook was identified by these rules before {mmss(b)}." if late else
                               f"No hook was identified by these rules in the first {dur:.0f} s: no opening question, promise or teaser was detected.")
                              + " An early reason to stay helps viewers commit.",
                    suggestion="State the specific problem, question or outcome in the first seconds.",
                    counter="The detector can miss an implicit, paraphrased or visual hook; this is not proof that there is no hook.",
                    preserve="Keep the existing opening content; add or move a hook rather than cutting.",
                    measurements={**m, "hook_ms": hook, "window_s": 30,
                                  "detector": "Narrative structure extraction of the hook; requires review"}))
            elif key == "repetition":
                earlier_best = (0.0, None)
                for s in source:
                    prev = [p for p in segs if p["interval"]["end_ms"] <= a]
                    o = _best_earlier(s["text"], prev)
                    if o[0] > earlier_best[0]:
                        earlier_best = o
                ov, es = earlier_best
                earlier = {"quote": es["text"], "start_ms": es["interval"]["start_ms"], "end_ms": es["interval"]["end_ms"]} if es else None
                findings.append(make_finding(
                    "repetition", a, b, segs, severity="high" if dur >= 15 else "medium", evidence="supported",
                    mechanism=(f"Reuses wording from {mmss(earlier['start_ms'])} without a new example or step." if earlier
                               else "Reuses earlier wording without a new example or step.")
                              + " Hearing the same lines again feels like padding.",
                    suggestion="Cut only the duplicated sentences; keep any new qualification, or replace the repeat with a new example.",
                    counter="The repeat may deliberately reinforce a difficult idea; a recap marker the detector missed would make it intentional.",
                    earlier=earlier,
                    measurements={**m, "best_earlier_trigram_overlap": round(ov, 4), "threshold": 0.5,
                                  "detector": "At least two consecutive segments with >=50% earlier three-word phrases, <25% new words, "
                                              "no progress or recap marker, not an announced replay"}))
            elif key == "low_novelty":
                prev = [s for s in segs if s["interval"]["end_ms"] <= a]
                terms = _cw(quote)
                earlier_terms = set().union(*(_cw(s["text"]) for s in prev)) if prev else set()
                markers = sorted({x.group(0).lower() for x in ADVANCE.finditer(quote)} |
                                 {x.group(0).lower() for x in CONCRETE.finditer(quote) if not x.group(0).isdigit()})
                if any(ch.isdigit() for ch in quote):
                    markers.append("numbers")
                sev = "medium" if strength >= 0.5 and dur >= 20 else "low"
                if markers:
                    sev = _step_down(sev)
                findings.append(make_finding(
                    "low_novelty", a, b, segs, severity=sev, evidence="provisional",
                    mechanism=f"For {dur:.0f} s mostly familiar words are reused, which suggests few new ideas."
                              + (f" Progress markers were found ({', '.join(markers[:4])}), so severity was reduced." if markers else
                                 " No new step, example, comparison or cause marker was found."),
                    suggestion="Check whether this stretch adds a new step, example or comparison; if not, tighten it or add one.",
                    counter="Familiar vocabulary can still carry a new idea; word novelty does not measure meaning.",
                    measurements={**m, "new_content_terms": sorted(terms - earlier_terms)[:20], "content_term_count": len(terms),
                                  "passage_lexical_novelty": round(len(terms - earlier_terms) / len(terms), 4) if terms else None,
                                  "progress_markers": markers,
                                  "detector": "20-second rolling content-term novelty below 60% of speaker baseline for at least 10 seconds"}))
            elif key == "long_sentences":
                longest = max((len(x.split()) for s in source for x in re.split(r"[.!?]+", s["text"])), default=0)
                sev = "low" if longest <= 40 else "medium" if longest <= 50 else "high"
                findings.append(make_finding(
                    "long_sentences", a, b, segs, severity=sev, evidence="supported" if longest > 40 else "provisional",
                    mechanism=f"One sentence runs {longest} words. By ear, viewers must hold several ideas before the point lands.",
                    suggestion="Split it into two or three sentences, keeping the causal links (because, so, unless) and qualifications.",
                    counter="Automatic punctuation can merge sentences; a long but well-structured sentence can still be easy to follow.",
                    preserve="Keep every claim, link word and qualification; only change sentence boundaries.",
                    measurements={**m, "longest_sentence_words": longest, "threshold_words": 30,
                                  "detector": "Word count between punctuation marks; disabled where the transcript has no punctuation"}))
            elif key in ("slow_pace", "fast_pace"):
                slow = key == "slow_pace"
                findings.append(make_finding(
                    key, a, b, segs, severity="medium" if strength >= 0.6 else "low", evidence="provisional",
                    mechanism=(f"For {dur:.0f} s the speaker is noticeably {'slower' if slow else 'faster'} than their own usual pace"
                               + (f" (about {info.get('median_wpm')} words/min)." if info.get("median_wpm") else ".")
                               + (" Slow stretches can feel like waiting." if slow else " Fast bursts can lose viewers who are following closely.")),
                    suggestion=("Check whether the slower delivery helps understanding; if not, tighten pauses." if slow
                                else "Consider a short pause between new ideas in this stretch."),
                    counter=("Slowing down may be helping with a difficult idea." if slow else "Fast delivery may cover familiar material."),
                    preserve="Keep all content; this is a delivery note, not a content cut.",
                    measurements={**m, "speaker_median_wpm": info.get("median_wpm"), "relative_threshold": 0.8 if slow else 1.2,
                                  "detector": "20-second aligned-word window over speaking time"}))
            elif key == "filler_density":
                findings.append(make_finding(
                    key, a, b, segs, severity="medium" if strength >= 0.8 else "low", evidence="provisional",
                    mechanism="Several filler words (um, uh, you know) cluster here, which can sound unprepared.",
                    suggestion="Trim the nonessential hesitations only.",
                    counter="Some fillers are natural conversational style; transcription may add or miss fillers.",
                    preserve="Keep meaningful discourse words and every content word.",
                    measurements={**m, "detector": "At least two lexical filler matches in a 20-second window"}))
            elif key == "dead_air":
                findings.append(make_finding(
                    key, a, b, segs, severity="high" if dur >= 6 else "medium" if dur >= 3 else "low", evidence="supported",
                    mechanism=f"{dur:.1f} s of quiet with no speech. Unless something is happening on screen, silence gives no new reason to keep watching.",
                    suggestion="Check the visuals; if nothing is shown, trim the gap to a natural pause.",
                    counter="The silence may accompany a demonstration, reveal or reading time on screen.",
                    preserve="Keep any on-screen demonstration; trim only empty time.",
                    measurements={**m, "detector": "Waveform-quiet interval with no VAD speech; not transcript absence"}))
            elif key == "flat_low_energy":
                ae = info.get("audio_energy", {})
                findings.append(make_finding(
                    key, a, b, segs, severity="low", evidence="provisional",
                    mechanism=f"For {dur:.0f} s the voice varies less in pitch and is quieter than this speaker usually is "
                              f"(speaker median {ae.get('speaker_median_lufs')} LUFS). A flatter stretch can feel less engaging.",
                    suggestion="Consider re-recording or adding emphasis on the key line in this stretch.",
                    counter="Calm delivery may suit the content; music, room noise or octave errors distort pitch. This is not an emotion judgement.",
                    preserve="Keep all content; this is a delivery note.",
                    measurements={**m, **{k: ae.get(k) for k in ("speaker_median_lufs", "rules")},
                                  "detector": "10 s pitch-variation windows + short-term loudness, relative to the same speaker"}))
            elif key == "loudness_drop":
                ae = info.get("audio_energy", {})
                findings.append(make_finding(
                    key, a, b, segs, severity="medium" if dur >= 5 else "low", evidence="supported",
                    mechanism=f"The audio level drops by 10 LU or more for {dur:.0f} s while speech continues. Viewers may struggle to hear it.",
                    suggestion="Check the recording here and raise or normalise the level.",
                    counter="The drop may be a deliberate quiet moment or a change of speaker or microphone.",
                    preserve="Keep the content; adjust only the audio level.",
                    measurements={**m, **{k: ae.get(k) for k in ("speaker_median_lufs", "rules")},
                                  "detector": "Short-term loudness vs trailing 10 s speech median, with VAD speech"}))
            elif key == "dense_text_fast_speech":
                ot = info.get("onscreen_text", {})
                findings.append(make_finding(
                    key, a, b, segs, severity="medium" if dur >= 5 else "low", evidence="provisional",
                    mechanism=f"For {dur:.0f} s there is a lot of on-screen text while the speaker talks faster than usual. "
                              "Viewers cannot read and listen closely at the same time.",
                    suggestion="Reduce the on-screen text to a few key words, or slow down while it is shown.",
                    counter="The text may be a decorative background or repeat what is said; OCR can misread or over-count text.",
                    preserve="Keep the spoken explanation; trim only redundant on-screen words.",
                    measurements={**m, "rule": ot.get("dense_rule"), "speaker_median_wpm": info.get("median_wpm"),
                                  "detector": "OCR text tracks active in the second + local aligned-word speech rate"}))
            elif key == "long_static_shot":
                vp = info.get("visual_pacing", {})
                shot = next((x for x in vp.get("long_static_list", []) if x["start_ms"] <= a < x["end_ms"]), None)
                length = (shot["end_ms"] - shot["start_ms"]) / 1000 if shot else None
                findings.append(make_finding(
                    key, a, b, segs, severity="medium" if (length or dur) >= 20 else "low", evidence="supported",
                    mechanism=(f"One low-motion shot holds for {length:.0f} s (from {mmss(shot['start_ms'])}); " if shot else
                               f"One low-motion shot continues past {vp.get('long_static_threshold_s')} s; ")
                              + f"shots in this video usually last {vp.get('median_shot_s')} s. A long unchanging picture gives the eye nothing new.",
                    suggestion="Add a cut, zoom, B-roll or on-screen graphic during this stretch.",
                    counter="A static shot can be intentional (talking head, screen demo, slide being read); motion is measured, meaning is not.",
                    preserve="Keep the audio and any on-screen detail viewers need to read.",
                    measurements={**m, **{k: vp.get(k) for k in ("median_shot_s", "long_static_threshold_s", "low_motion_threshold")},
                                  "shot_start_ms": shot["start_ms"] if shot else None, "shot_length_s": length,
                                  "shot_motion_mean": shot["motion_mean"] if shot else None,
                                  "detector": "Shot length > max(8 s, 3x median shot) and motion in the lowest quarter of this video's shots"}))
    findings.extend(structure_findings(segs, duration_ms, st))
    return {"findings": findings,
            "timing_source": info.get("timing_quality") or ("aligned_words" if any("aligned words" in x for x in info["sources"]) else "segment_timestamps"),
            "status": "candidate_review_required", "risk_label": "Heuristic transcript and delivery risk — not probability of leaving",
            "coverage": {"transcript": bool(segments), "word_timing": info.get("median_wpm") is not None,
                         "structure": any(x.startswith("narrative structure") for x in info["sources"]),
                         "visuals": False},
            "scenario_basis": "Exploratory candidate-driven scenario; no editorial findings have been accepted automatically",
            "policy": "Candidates influence an explicitly assumed scenario; acceptance is a separate editorial review step. Related symptoms use their strongest contribution per cause group.",
            "empty_findings_mean": "No rule candidates identified; this is not proof that the script is healthy."}


def first_payoff_ms(st: dict) -> int | None:
    pays = [p["first_fulfil_ms"] for p in st.get("promises", []) if p.get("first_fulfil_ms") is not None
            and p.get("status") in ("fulfilled", "partial")]
    return min(pays) if pays else st.get("first_substance_ms")


def structure_findings(segs: list[dict], T: int, st: dict) -> list[dict]:
    out = []
    # A3: delayed title payoff (absolute AND relative position)
    for i, p in enumerate(st.get("promises", [])):
        first = p.get("first_fulfil_ms")
        if p.get("status") not in ("fulfilled", "partial") or not first:
            continue
        rel = first / T if T else 0
        if first > PAYOFF_MIN_MS and rel > PAYOFF_MIN_REL:
            pay = _overlapping(segs, first, first + 1)
            out.append(make_finding(
                "delayed_title_payoff", min(15_000, first), first, segs, severity="high" if first > 90_000 and rel > 0.35 else "medium",
                evidence="provisional", quote=" ".join(s["text"] for s in pay) or None,
                mechanism=f"The first part of what the title promises (\"{p.get('obligation', 'the title promise')}\") arrives at {mmss(first)}, "
                          f"{rel:.0%} of the way in. Viewers waiting for it may give up first.",
                suggestion="Give a short version of the answer early, then expand on it where it is now.",
                counter="A delayed answer may be a deliberate teaching or story sequence; the payoff time comes from narrative extraction.",
                preserve="Keep the full explanation where it is; add a brief early preview rather than moving everything.",
                measurements={"promise_index": i, "obligation": p.get("obligation"), "title_quote": p.get("title_quote"),
                              "first_payoff_ms": first, "relative_position": round(rel, 4),
                              "thresholds": {"absolute_s": PAYOFF_MIN_MS / 1000, "relative": PAYOFF_MIN_REL},
                              "detector": "Narrative promise ledger; requires confirmation"}))
    pay_ms = first_payoff_ms(st)
    for sp in st.get("spans", []):
        a, b = sp["interval"]["start_ms"], sp["interval"]["end_ms"]
        near_end = a >= T - 45_000 or a >= 0.85 * T
        kind = sp["kind"]
        if kind == "cta" and pay_ms is not None and a < pay_ms:
            out.append(make_finding(
                "cta_before_payoff", a, b, segs, severity="medium", evidence="provisional",
                mechanism=f"A call to action at {mmss(a)} comes before the first payoff ({mmss(pay_ms)}): viewers are asked for something before receiving value.",
                suggestion="Move the request after the first useful point or to a natural section break.",
                counter="A short, relevant request may not interrupt; span detection comes from narrative extraction.",
                preserve="Keep the request itself; change only where it sits.",
                measurements={"first_payoff_ms": pay_ms, "span_kind": kind, "detector": "Narrative CTA span before first payoff"}))
        elif kind in ("cta", "sponsor") and not near_end:
            out.append(make_finding(
                "mid_video_interruption", a, b, segs, severity="medium" if kind == "sponsor" else "low", evidence="provisional",
                title="Sponsor segment interrupts the content" if kind == "sponsor" else "Call to action in the middle",
                mechanism=f"A {'sponsor segment' if kind == 'sponsor' else 'call to action'} at {mmss(a)} pauses the content viewers came for.",
                suggestion="Place it at a section boundary and keep it short; bridge back to the topic afterwards.",
                counter="The interruption may be required or relevant to the viewer's task.",
                preserve="Keep required disclosures intact.",
                measurements={"span_kind": kind, "detector": "Narrative sponsor/CTA span away from the ending"}))
        elif kind == "outro" or (kind in ("cta", "recap") and near_end):
            length = T - a
            if length > max(20_000, 0.08 * T):
                out.append(make_finding(
                    "extended_outro", a, T, segs, severity="high" if length > 60_000 else "medium" if length > 30_000 or length > 0.12 * T else "low",
                    evidence="provisional",
                    mechanism=f"The ending starts at {mmss(a)} and runs {length / 1000:.0f} s. Once viewers sense the end, many leave.",
                    suggestion="Deliver the final takeaway before the closing cue and shorten the sign-off.",
                    counter="A closing synthesis can be valuable; the ending span comes from narrative extraction.",
                    preserve="Keep the final takeaway and any required end-screen time.",
                    measurements={"outro_s": length / 1000, "threshold_s": max(20, round(0.08 * T / 1000, 1)),
                                  "detector": "Narrative outro/closing span"}))
        if kind == "recap":
            prev = [s for s in segs if s["interval"]["end_ms"] <= a]
            text = " ".join(s["text"] for s in _overlapping(segs, a, b))
            ov, es = _best_earlier(text, prev)
            terms = _cw(text)
            seen = set().union(*(_cw(s["text"]) for s in prev)) if prev else set()
            nov = len(terms - seen) / len(terms) if terms else 1.0
            tri = _content_trigrams(text)
            seen_tri = set().union(*(_content_trigrams(s["text"]) for s in prev)) if prev else set()
            reuse = len(tri & seen_tri) / len(tri) if tri else 0.0
            if reuse >= 0.5 and nov < 0.25:  # E4 only when redundancy is measured
                out.append(make_finding(
                    "redundant_recap", a, b, segs, severity="medium" if b - a > 30_000 else "low", evidence="supported",
                    earlier={"quote": es["text"], "start_ms": es["interval"]["start_ms"], "end_ms": es["interval"]["end_ms"]} if es else None,
                    mechanism=f"The recap reuses {reuse:.0%} of its phrases from earlier and adds {nov:.0%} new words: it repeats rather than sums up.",
                    suggestion="Shorten the recap to the one or two takeaways, in fresh words.",
                    counter="Some viewers skip ahead and rely on the recap; repetition can aid memory.",
                    preserve="Keep the single most important takeaway.",
                    measurements={"earlier_trigram_reuse": round(reuse, 4), "lexical_novelty": round(nov, 4),
                                  "thresholds": {"reuse": 0.5, "novelty": 0.25}, "detector": "Recap span text against everything said before it"}))
        if kind == "tangent_candidate":
            after = _overlapping(segs, a, b + 15_000)
            link = next((m.group(0) for s in after for m in [CONNECT_BACK.search(s["text"])] if m), None)
            if not link:
                out.append(make_finding(
                    "topic_drift", a, b, segs, severity="medium", evidence="provisional",
                    mechanism="This passage was marked as a possible detour from the title topic, and no explicit link back "
                              "(for example \"which brings us back to…\") was found here or in the next 15 s.",
                    suggestion="Add one sentence connecting this passage to the title question, or shorten it.",
                    counter="The connection may be implicit or obvious to the audience; the detour label comes from narrative extraction.",
                    preserve="Keep any fact the later content depends on.",
                    measurements={"connection_markers_found": [], "search_after_s": 15,
                                  "detector": "Narrative tangent candidate without explicit connection phrase"}))
    return out


def relation_evidence(segments: list[dict], duration_ms: int, structure: dict | None = None) -> dict:
    """Relation candidates (C2, C3, C4, D1, D2, A4). Review-only: never fed into hazard weights."""
    from pipeline.reasoning.relations import analyse, cognitive_load, concreteness, sentences
    relations = analyse(segments)
    findings = []
    segs = sorted(segments, key=lambda s: s["interval"]["start_ms"])

    def add(rule, a, b, **kw):
        a, b = max(0, int(a)), min(duration_ms, int(b))
        f = make_finding(rule, a, b, segs, scored=False, **kw)
        f["finding_id"] = f"{rule}:{a}:{b}:{len(findings)}"
        f["acceptance"] = "Review candidate manually; lexical rules do not establish semantic defects or abandonment."
        findings.append(f)

    for item in relations["abstract_stretches"]:
        d = (item["end_ms"] - item["start_ms"]) / 1000
        add("extended_abstraction", item["start_ms"], item["end_ms"], severity="medium" if d >= 60 else "low", evidence="provisional",
            mechanism=f"For {d:.0f} s the explanation stays abstract (terms like concept, framework, process) with no example, number or named case.",
            measurements={"duration_s": d, "threshold_s": 40, "abstract_term_matches": item["abstract_terms"],
                          "sentences": item["sentences"], "concrete_marker_matches": 0},
            counter="A visual demonstration or familiar context may make this passage concrete; phrase detection cannot judge example usefulness.",
            suggestion="Add one worked example using the ideas already introduced, if the intended audience needs one.")
    for item in relations["term_dependencies"]:
        used, explained = item["used_at"], item["explained_at"]
        gap = item["gap_ms"] / 1000
        add("term_used_before_explanation", used["start_ms"], used["end_ms"], severity="medium" if gap > 60 else "low", evidence="provisional",
            mechanism=f"'{item['term']}' is used at {mmss(used['start_ms'])} but only explained at {mmss(explained['start_ms'])}. "
                      "Viewers who do not know it may lose the thread until then.",
            measurements={"term": item["term"], "first_use_ms": used["start_ms"], "definition_candidate_ms": explained["start_ms"],
                          "gap_s": gap, "definition_detection": "Named-phrase pattern, not semantic definition verification"},
            counter="The audience may already know the term; a paraphrased definition may occur earlier.",
            suggestion="If this term is unfamiliar to the intended audience, move the existing definition earlier or add a brief definition at first use.",
            preserve="Keep the later full explanation.",
            later=[{"start_ms": explained["start_ms"], "end_ms": explained["end_ms"], "quote": explained["text"], "status": "definition_candidate"}])
    # C3: dense new terms + long sentences + no example in the same minute, grouped as one issue
    sents = sentences(segments)
    load = cognitive_load(sents)
    conc = concreteness(sents)
    dense = []
    for w in load["windows"]:
        if w["load"] != "high":
            continue
        inside = [s for s in conc if w["start_ms"] <= s["start_ms"] < w["end_ms"]]
        long_n = sum(len(s["text"].split()) > 30 for s in inside)
        if inside and (long_n or w["mean_sentence_words"] >= 22) and not any(s["concrete_markers"] for s in inside) \
                and all(s.get("punctuated", True) for s in inside):
            if dense and dense[-1]["end_ms"] >= w["start_ms"]:
                dense[-1] = {**dense[-1], "end_ms": w["end_ms"], "new_terms": dense[-1]["new_terms"] + w["new_terms"],
                             "long": dense[-1]["long"] + long_n}
            else:
                dense.append({"start_ms": w["start_ms"], "end_ms": w["end_ms"], "new_terms": w["new_terms"],
                              "mean": w["mean_sentence_words"], "long": long_n})
    for d in dense:
        add("dense_new_terms", d["start_ms"], d["end_ms"], severity="medium", evidence="provisional",
            mechanism=f"{d['new_terms']} new terms arrive in this stretch, in long sentences and without an example. "
                      "Viewers may fall behind before the ideas settle.",
            measurements={"new_terms": d["new_terms"], "median_new_terms_per_min": load.get("median_new_terms_per_min"),
                          "long_sentences": d["long"], "mean_sentence_words": d["mean"], "concrete_markers": 0,
                          "detector": "60 s window: new terms >1.5x median AND long sentences AND no concrete marker"},
            counter="The terms may be familiar to the intended audience, or shown on screen.",
            suggestion="Introduce fewer terms at once: add one example, or split the sentences so each new term gets its own.")
    for item in relations["questions"]:
        question, answer = item["question"], item["answer"]
        if item["kind"] == "framing" or item["rhetorical_form"]:
            continue
        if answer is not None and (item["gap_ms"] or 0) <= 60_000:
            continue
        add("question_without_callback" if answer is None else "delayed_question_callback", question["start_ms"], question["end_ms"],
            severity="medium" if answer is None else "low", evidence="provisional",
            mechanism=(f"The question at {mmss(question['start_ms'])} gets no detectable answer later. An open question that is never "
                       "closed can feel like a broken promise." if answer is None else
                       f"The question at {mmss(question['start_ms'])} is only picked up at {mmss(answer['start_ms'])}, "
                       f"{item['gap_ms'] / 1000:.0f} s later. Viewers may forget it or stop waiting."),
            measurements={"shared_words": item["shared_words"], "callback_gap_s": item["gap_ms"] / 1000 if item["gap_ms"] is not None else None,
                          "search_horizon_s": 600, "question_kind": item["kind"], "rhetorical_form": item["rhetorical_form"]},
            counter="This may be rhetorical or an opening frame; paraphrased answers can be missed and shared vocabulary does not prove an answer.",
            suggestion="Confirm whether the question is answered. If needed, answer it explicitly or connect the question to its later payoff.",
            preserve="Keep the question; it can be a useful open loop when it is closed later.",
            later=[{"start_ms": answer["start_ms"], "end_ms": answer["end_ms"], "quote": answer["text"], "status": "lexical_callback_candidate"}] if answer else [])
    # D2: several new open questions within 60 s while an earlier substantive question is still unresolved
    subs = [q for q in relations["questions"] if not q["rhetorical_form"] and q["kind"] != "framing"]
    clusters: list[dict] = []
    for i, q in enumerate(subs):
        t = q["question"]["start_ms"]
        open_before = [p for p in subs[:i] if p["question"]["start_ms"] < t - 60_000 or p["kind"] != "immediate"]
        open_before = [p for p in open_before if p["question"]["start_ms"] < t and (p["answer"] is None or p["answer"]["start_ms"] > t)]
        recent = [p for p in subs[:i + 1] if t - 60_000 <= p["question"]["start_ms"] <= t and p["kind"] != "immediate"]
        earlier_open = [p for p in open_before if p not in recent]
        if len(recent) >= 2 and earlier_open:
            a, b = recent[0]["question"]["start_ms"], q["question"]["end_ms"]
            if clusters and clusters[-1]["end_ms"] >= a:
                clusters[-1].update(end_ms=b, n=len({*clusters[-1]["ids"], *(id(p) for p in recent)}),
                                    ids=clusters[-1]["ids"] | {id(p) for p in recent})
            else:
                clusters.append({"start_ms": a, "end_ms": b, "n": len(recent), "ids": {id(p) for p in recent},
                                 "earlier": earlier_open[0]["question"]})
    for c in clusters:
        e = c["earlier"]
        add("stacked_open_questions", c["start_ms"], c["end_ms"], severity="medium" if c["n"] >= 3 else "low", evidence="provisional",
            earlier={"quote": e["text"], "start_ms": e["start_ms"], "end_ms": e["end_ms"]},
            mechanism=f"{c['n']} new questions open here while the question from {mmss(e['start_ms'])} has not been answered yet. "
                      "Too many open threads at once are hard to track.",
            measurements={"new_open_questions": c["n"], "window_s": 60, "earlier_unresolved_ms": e["start_ms"],
                          "detector": "Lexical question/answer matching; answers can be paraphrased"},
            counter="The questions may be a deliberate roadmap answered in order; lexical matching can miss answers.",
            suggestion="Close the earlier question first, or announce the order in which the questions will be answered.")
    ledger = []
    for index, promise in enumerate((structure or {}).get("promises", [])):
        first = promise.get("first_fulfil_ms")
        entry = {**promise, "first_partial_payoff_ms": first,
                 "first_payoff_relative_position": round(first / duration_ms, 4) if first is not None and duration_ms else None,
                 "timing_status": "narrative_candidate_requires_confirmation",
                 "payoff_quote": " ".join(s["text"] for s in segments if first is not None and s["interval"]["start_ms"] <= first < s["interval"]["end_ms"])}
        ledger.append(entry)
        if promise.get("status") in ("unaddressed", "uncertain"):
            add("unconfirmed_title_promise", 0, min(30_000, duration_ms), severity="medium" if promise.get("status") == "unaddressed" else "low",
                evidence="provisional",
                mechanism=f"The narrative pass could not confirm where the title promise (\"{promise.get('obligation', '')}\") is delivered. "
                          "If it is not delivered, viewers who came for it leave disappointed.",
                measurements={"promise_index": index, "promise": promise, "status": promise.get("status")},
                counter="The extraction may miss a paraphrased or implicit fulfilment; uncertainty is not proof of a broken promise.",
                suggestion="Review the title obligation against the full transcript and confirm fulfilment before changing the script.",
                preserve="Keep the title promise; confirm or add its delivery.")
    return {"findings": findings, "promise_ledger": ledger,
            "relation_method": relations["method"],
            "scoring_policy": "Relation candidates (C2-C4, D1, D2, A4) count in the transcript risk timeline with provisional "
                              "evidence weight but do not change the retention scenario."}


def analyse_transcript(features: list[dict], segments: list[dict], duration_ms: int, info: dict,
                       structure: dict | None = None) -> dict:
    """All findings, ranked, plus the 5-second transcript risk timeline (the `analysis` block of prediction.json)."""
    from pipeline.predict.risk import rank_findings, risk_weights, transcript_risk_bins
    evidence = build_evidence(features, segments, duration_ms, info, structure)
    evidence["structure_ledger"] = structure
    extra = relation_evidence(segments, duration_ms, structure)
    evidence["findings"].extend(extra.pop("findings"))
    evidence.update(extra)
    evidence["findings"] = rank_findings(evidence["findings"], duration_ms, structure)
    evidence["risk_bins"] = transcript_risk_bins(evidence["findings"], duration_ms)
    evidence["risk_weights"] = risk_weights()
    return evidence
