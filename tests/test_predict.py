import math

import pytest

from pipeline.predict.features import build_features
from pipeline.predict.model import Anchors, drop_moments, predict


def test_neutral_video_hits_the_anchors_exactly():
    p = predict([{} for _ in range(300)], Anchors(0.8, 0.45))
    curve = [1.0] + [s["retention"] for s in p["per_second"]]
    assert math.isclose(curve[30], 0.8, abs_tol=1e-4) and math.isclose(curve[300], 0.45, abs_tol=1e-4)
    assert p["summary"]["excess_loss_by_feature"] == {} and p["calibrated"] is False


def test_survival_is_monotone_and_band_contains_central():
    F = [{"setup_before_substance": 1.0} if t < 40 else {"open_loop": 0.5} if t < 100 else {} for t in range(300)]
    ps = predict(F)["per_second"]
    assert all(b["retention"] <= a["retention"] + 1e-12 for a, b in zip(ps, ps[1:]))
    assert all(s["lower"] - 1e-9 <= s["retention"] <= s["upper"] + 1e-9 for s in ps)


def test_feature_directions_and_attribution():
    base = predict([{} for _ in range(200)])["summary"]["avd_s"]["central"]
    worse = predict([{"repetition": 1.0} if 50 <= t < 80 else {} for t in range(200)])
    better = predict([{"open_loop": 1.0} if 50 <= t < 80 else {} for t in range(200)])
    assert worse["summary"]["avd_s"]["central"] < base < better["summary"]["avd_s"]["central"]
    # all excess loss in the repeated window is attributed to repetition
    s = worse["per_second"][60]
    assert s["contributions"] == {"repetition": s["excess_loss"]} and s["excess_loss"] > 0
    m = drop_moments(worse)
    assert m and m[0]["reasons"][0]["feature"] == "repetition" and 45 <= m[0]["start_s"] <= 80


def test_invalid_anchors_rejected():
    with pytest.raises(ValueError):
        predict([{} for _ in range(100)], Anchors(0.4, 0.6))


def test_features_from_transcript_and_structure():
    segs = [{"interval": {"start_ms": i * 5000, "end_ms": i * 5000 + 5000}, "text": t} for i, t in enumerate(
        ["Hi everyone welcome back to the channel today", "So in this video we will look at something",
         "The battery lasted 9 hours and 12 minutes in our test", "For example the screen used 40 percent"] * 5)]
    st = {"first_substance_ms": 10_000, "hook_ms": 6_000, "promises": [],
          "spans": [{"kind": "cta", "interval": {"start_ms": 30_000, "end_ms": 35_000}}]}
    F, info = build_features(100_000, segs, [], st)
    assert F[3].get("setup_before_substance") == 1.0 and "setup_before_substance" not in F[12]
    assert F[11].get("concrete") == 1.0 and F[32].get("cta_or_sponsor") == 1.0
    assert "no word timing: pace features off" in info["sources"]
