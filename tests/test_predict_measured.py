"""Measured optional signals: visual pacing (shots), on-screen text (OCR), audio energy (loudness + pitch windows).
Each must contribute when its data is present and be off (and say so in feature_info.sources) when absent."""
import math

import pytest

from pipeline.predict.evidence import build_evidence
from pipeline.predict.features import build_features
from pipeline.predict.model import drop_moments, predict

T = 120_000
SEGS = [{"segment_id": f"s{i}", "interval": {"start_ms": i * 10_000, "end_ms": i * 10_000 + 10_000},
         "text": f"This part explains the {w} stage of the process in plain words."}
        for i, w in enumerate(["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth",
                               "tenth", "eleventh", "last"])]


def _has(F, key):
    return [t for t, f in enumerate(F) if f.get(key)]


def _shots(long_motion=0.001):
    shots, t = [], 0
    for _ in range(10):
        shots.append({"start_ms": t, "end_ms": t + 4000, "metrics": {"motion_mean": 0.1}})
        t += 4000
    shots.append({"start_ms": t, "end_ms": t + 40_000, "metrics": {"motion_mean": long_motion}})
    t += 40_000
    while t < T:
        shots.append({"start_ms": t, "end_ms": min(T, t + 4000), "metrics": {"motion_mean": 0.12}})
        t += 4000
    return shots


def test_long_static_shot_contributes_and_cut_is_weak_protective():
    F, info = build_features(T, SEGS, [], None, shots=_shots())
    static = _has(F, "long_static_shot")
    # the 40 s low-motion shot starts at 40 s; threshold = max(8 s, 3 x 4 s median) = 12 s -> flagged from 52 s
    assert static[0] == 52 and static[-1] == 79 and F[52]["long_static_shot"] == 0.5 and F[64]["long_static_shot"] == 1.0
    assert F[4]["fresh_visual_change"] == 1.0 and "fresh_visual_change" not in F[0]
    assert info["visual_pacing"]["long_static_shots"] == 1 and "40 shots (visual pacing)" not in info["sources"]
    assert any(s.endswith("shots (visual pacing)") for s in info["sources"])
    p = predict(F, duration_ms=T)
    base = predict(build_features(T, SEGS, [], None)[0], duration_ms=T)
    assert p["summary"]["avd_s"]["central"] < base["summary"]["avd_s"]["central"]
    assert any(m["reasons"][0]["feature"] == "long_static_shot" for m in drop_moments(p))
    f = next(x for x in build_evidence(F, SEGS, T, info)["findings"] if x["rule_id"] == "long_static_shot")
    assert f["cause_group"] == "visual_pacing" and f["evidence_strength"] == "supported" and f["start_ms"] == 52_000
    # a long shot with lots of motion is not static
    F2, _ = build_features(T, SEGS, [], None, shots=_shots(long_motion=0.5))
    assert not _has(F2, "long_static_shot")


def test_visual_pacing_off_without_shots():
    F, info = build_features(T, SEGS, [], None)
    assert not _has(F, "long_static_shot") and not _has(F, "fresh_visual_change")
    assert "no shot data: visual pacing features off" in info["sources"]


def _words():
    out, t = [], 0
    while t < T:
        step = 250 if 60_000 <= t < 80_000 else 500  # twice as fast between 60 and 80 s
        out.append({"start_ms": t, "end_ms": t + 200, "text": "w"})
        t += step
    return out


def test_onscreen_text_new_and_dense_with_fast_speech():
    tracks = [{"start_ms": 0, "end_ms": T, "text": "CHANNEL LOGO", "detector_confidence": 0.9},
              {"start_ms": 20_000, "end_ms": 25_000, "text": "Step one: open settings", "detector_confidence": 0.9},
              {"start_ms": 60_000, "end_ms": 80_000, "text": " ".join(["word"] * 15), "detector_confidence": 0.9},
              {"start_ms": 30_000, "end_ms": 31_000, "text": "low confidence text", "detector_confidence": 0.2}]
    F, info = build_features(T, SEGS, _words(), None, ocr_tracks=tracks)
    assert F[20]["new_onscreen_text"] == 1.0 and "new_onscreen_text" not in F[0] and "new_onscreen_text" not in F[30]
    dense = _has(F, "dense_text_fast_speech")
    assert dense and 58 <= dense[0] and dense[-1] <= 80 and F[dense[0]]["dense_text_fast_speech"] == pytest.approx(17 / 24)
    f = next(x for x in build_evidence(F, SEGS, T, info)["findings"] if x["rule_id"] == "dense_text_fast_speech")
    assert f["cause_group"] == "comprehension" and f["evidence_strength"] == "provisional"
    # without word timing the dense rule cannot measure speech rate: off
    F2, info2 = build_features(T, SEGS, [], None, ocr_tracks=tracks)
    assert not _has(F2, "dense_text_fast_speech") and _has(F2, "new_onscreen_text")
    assert "off: no word timing" in info2["onscreen_text"]["dense_rule"]


def test_onscreen_text_off_without_ocr():
    F, info = build_features(T, SEGS, _words(), None)
    assert not _has(F, "new_onscreen_text") and not _has(F, "dense_text_fast_speech")
    assert "no OCR tracks: on-screen text features off" in info["sources"]


def _audio():
    lufs = []
    for t in range(120):
        lufs.append(-30.0 if 50 <= t < 55 else -10.0 if 80 <= t < 84 else -20.0 if 90 <= t < 110 else -16.0)
    return {"loudness": {"short_term_t_ms": [t * 1000 for t in range(120)], "short_term_lufs": lufs}, "silence": [], "rms": None}


VAD = [{"start_ms": 0, "end_ms": T}]
WINDOWS = [{"start_ms": s, "end_ms": s + 10_000, "pitch_std_hz": 10.0 if s in (90_000, 100_000) else 30.0,
            "voiced_fraction": 0.6} for s in range(0, T, 10_000)]


def test_audio_energy_drop_lift_and_flat_delivery():
    audio = _audio()
    F, info = build_features(T, SEGS, [], None, audio, VAD, voice_windows=WINDOWS)
    assert _has(F, "loudness_drop") == [50, 51, 52, 53, 54]
    assert _has(F, "energy_lift") == [80, 81, 82, 83]
    assert _has(F, "flat_low_energy") == list(range(90, 110))
    assert info["audio_energy"]["speaker_median_lufs"] == -16.0
    rules = {f["rule_id"]: f for f in build_evidence(F, SEGS, T, info)["findings"]}
    assert rules["loudness_drop"]["evidence_strength"] == "supported" and rules["loudness_drop"]["cause_group"] == "delivery"
    assert "not an emotion judgement" in rules["flat_low_energy"]["counter_explanation"]
    assert "emotion" not in rules["flat_low_energy"]["mechanism"].lower()
    p = predict(F, duration_ms=T)
    c52 = p["per_second"][52]["contributions"]
    assert max(c52, key=c52.get) == "loudness_drop" and set(c52) <= {"loudness_drop", "micro_variation"}
    assert p["per_second"][81]["protective"][0] == "energy_lift" and set(p["per_second"][81]["protective"]) <= {"energy_lift", "micro_variation"}
    # flat delivery needs pitch windows; drop needs VAD ("speech continues" must be measured)
    F2, info2 = build_features(T, SEGS, [], None, audio, None)
    assert not _has(F2, "loudness_drop") and not _has(F2, "flat_low_energy") and _has(F2, "energy_lift")
    assert "no pitch windows: flat-delivery feature off" in info2["sources"]


def test_audio_energy_off_without_audio():
    F, info = build_features(T, SEGS, [], None)
    assert not any(_has(F, k) for k in ("loudness_drop", "energy_lift", "flat_low_energy"))
    assert "no short-term loudness: audio-energy features off" in info["sources"]


def test_protective_signals_are_capped_and_never_cancel_a_risk():
    risk = predict([{"repetition": 1} for _ in range(60)])
    both = predict([{"repetition": 1, "fresh_visual_change": 1, "new_onscreen_text": 1, "energy_lift": 1} for _ in range(60)])
    assert risk["summary"]["avd_s"] == both["summary"]["avd_s"]
    neutral = predict([{} for _ in range(60)])
    prot = predict([{"fresh_visual_change": 1, "new_onscreen_text": 1, "energy_lift": 1, "concrete": 1} for _ in range(60)])
    s = prot["per_second"][40]
    # only one protective signal counts, capped at -0.1 log-hazard
    assert len(s["protective"]) == 1
    assert s["hazard_per_s"] == pytest.approx(s["baseline_hazard_per_s"] * math.exp(-0.1), rel=1e-4)
    assert prot["summary"]["avd_s"]["central"] > neutral["summary"]["avd_s"]["central"]


def test_micro_variation_is_measured_signed_and_keeps_neutral_anchors():
    from pipeline.predict.features import micro_variation
    from pipeline.predict.model import Anchors, predict
    F = [{} for _ in range(120)]
    local = [150.0] * 60 + [90.0] * 60          # speaker slows down in the second minute
    info = {"sources": []}
    micro_variation(F, local, 150.0, None, None, info)
    assert all("micro_slowdown" not in f for f in F[:55]) and F[100]["micro_slowdown"] > 0
    assert any("speech rate" in s for s in info["sources"])
    p = predict(F, Anchors(0.8, 0.45))
    hz = [s["hazard_per_s"] / s["baseline_hazard_per_s"] for s in p["per_second"][30:]]
    assert max(hz) > 1.05 and min(hz) <= 1.0     # texture raises leaving only where it was measured
    neutral = predict([{} for _ in range(120)], Anchors(0.8, 0.45))
    assert abs(neutral["per_second"][-1]["retention"] - 0.45) < 1e-4
