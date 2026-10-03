"""Text retention v3: curved baseline, exact watch-time integral, 5 s risk bins, findings shape, ranking, packaging."""
import math

import pytest

from pipeline.predict.model import (GROUP_ALPHA, Anchors, Baseline, baseline_cumulative, drop_moments, predict)


@pytest.mark.parametrize("T,a,z,b", [
    (300, .8, .45, Baseline()), (600, .7, .3, Baseline()), (95.4, .9, .5, Baseline(0.4, 2.5, 0.2)),
    (1200, .8, .45, Baseline(1.0, 1.0, 0.0)), (25, .8, .6, Baseline()), (60, .8, .8, Baseline()),
])
def test_neutral_video_hits_anchors_exactly_with_curved_baseline(T, a, z, b):
    n = math.ceil(T)
    p = predict([{} for _ in range(n)], Anchors(a, z), duration_ms=int(T * 1000), baseline=b)
    ps = p["per_second"]
    assert ps[-1]["retention"] == pytest.approx(z, abs=1e-6)
    if T > 30:
        assert ps[29]["retention"] == pytest.approx(a, abs=1e-6)
    H, _ = baseline_cumulative(T, Anchors(a, z), b)
    assert math.exp(-H(T)) == pytest.approx(z, rel=1e-12)
    assert p["summary"]["excess_loss_by_feature"] == {} and p["calibrated"] is False


def test_neutral_curve_is_not_linear_hazard_falls_after_30s():
    p = predict([{} for _ in range(300)], Anchors(.8, .45))
    ps = p["per_second"]
    h = [x["baseline_hazard_per_s"] for x in ps]
    main = range(31, int(300 * 0.95) - 1)  # after the opening, before the end-drop stretch
    assert all(h[t + 1] < h[t] for t in main)
    S = [1.0] + [x["retention"] for x in ps]
    second_diff = [S[t + 1] - 2 * S[t] + S[t - 1] for t in range(32, 280)]
    assert all(d > 0 for d in second_diff)  # convex: the line bends, it is not straight
    assert h[0] > h[29] > h[40]  # steep opening that keeps falling
    # the final stretch has the documented end-drop multiplier
    assert h[290] / h[280] == pytest.approx(1.5, rel=0.02)
    assert p["baseline"]["kind"] == "weibull_two_segment" and p["baseline"]["shape_k"] == 0.6


def test_avd_matches_numeric_integration_and_cumulative_series():
    F = [{"repetition": 1.0} if 40 <= t < 70 else {"dead_air": 0.5} if 150 <= t < 160 else {} for t in range(200)]
    p = predict(F, duration_ms=199_400)
    ps = p["per_second"]
    # numeric integration of the model's piecewise-exponential survival, 400 steps per bin
    total, s = 0.0, 1.0
    for x in ps:
        h, dt, n = x["hazard_per_s"], x["duration_s"], 400
        total += sum(s * math.exp(-h * dt * (k + 0.5) / n) for k in range(n)) * dt / n
        s *= math.exp(-h * dt)
    assert p["summary"]["avd_s"]["central"] == pytest.approx(total, abs=0.02)
    assert ps[-1]["cumulative_watch_s"] == pytest.approx(p["summary"]["avd_s"]["central"], abs=0.01)
    assert ps[-1]["neutral_cumulative_watch_s"] == pytest.approx(p["summary"]["neutral_avd_s"], abs=0.01)
    assert all(b["cumulative_watch_s"] >= a["cumulative_watch_s"] for a, b in zip(ps, ps[1:]))
    wt = p["summary"]["watch_time"]
    assert wt["delta_vs_neutral_s"] < 0 and wt["duration_s"] == 199.4
    # the bin-averaged hazard stays close to the continuous Weibull curve
    H, _ = baseline_cumulative(300, Anchors(), Baseline())
    cont = sum(math.exp(-H((k + 0.5) / 20)) / 20 for k in range(300 * 20))
    neutral = predict([{} for _ in range(300)])["summary"]["avd_s"]["central"]
    assert neutral == pytest.approx(cont, abs=0.5)


def test_baseline_parameters_are_validated():
    for bad in (Baseline(shape_k=0.2), Baseline(shape_k=1.2), Baseline(end_drop_multiplier=0.9),
                Baseline(end_drop_multiplier=3.5), Baseline(end_drop_fraction=-0.1), Baseline(end_drop_fraction=0.3)):
        with pytest.raises(ValueError):
            predict([{} for _ in range(100)], baseline=bad)


def test_related_symptoms_do_not_double_in_scenario_or_risk_bins():
    from pipeline.predict.risk import transcript_risk_bins
    a = predict([{"dead_air": 1} for _ in range(60)])
    b = predict([{"dead_air": 1, "filler_density": 1, "slow_pace": 1} for _ in range(60)])
    assert a["summary"]["avd_s"] == b["summary"]["avd_s"]
    one = [{"finding_id": "x", "cause_group": "delivery", "severity": "high", "evidence_strength": "supported", "start_ms": 0, "end_ms": 5000}]
    two = one + [{"finding_id": "y", "cause_group": "delivery", "severity": "medium", "evidence_strength": "supported", "start_ms": 0, "end_ms": 5000}]
    r1, r2 = transcript_risk_bins(one, 10_000), transcript_risk_bins(two, 10_000)
    assert r1[0]["risk"] == r2[0]["risk"] == pytest.approx(100 * GROUP_ALPHA["delivery"][0])
    assert r2[0]["finding_ids"] == ["x", "y"] and r2[0]["top_finding_id"] == "x"
    # different groups add, weighted by alpha; a half-covered bin counts half; provisional counts half
    mixed = one + [{"finding_id": "z", "cause_group": "progress", "severity": "high", "evidence_strength": "provisional", "start_ms": 2500, "end_ms": 5000}]
    r3 = transcript_risk_bins(mixed, 10_000)
    assert r3[0]["risk"] == pytest.approx(100 * (GROUP_ALPHA["delivery"][0] + GROUP_ALPHA["progress"][0] * 0.25))
    assert r3[0]["groups"]["progress"] == 0.25 and r3[1]["risk"] == 0
    assert sum(a for a, _ in GROUP_ALPHA.values()) == pytest.approx(1)


def test_priority_prefers_supported_high_over_provisional_and_suppresses_duplicates():
    from pipeline.predict.risk import rank_findings
    base = {"cause_group": "progress", "severity": "high", "start_ms": 100_000, "end_ms": 110_000, "safe_edit": False}
    fs = [{**base, "finding_id": "prov", "evidence_strength": "provisional"},
          {**base, "finding_id": "sup", "evidence_strength": "supported", "start_ms": 200_000, "end_ms": 210_000},
          {**base, "finding_id": "dup", "evidence_strength": "supported", "severity": "medium", "start_ms": 201_000, "end_ms": 209_000}]
    ranked = rank_findings(fs, 300_000)
    order = [f["finding_id"] for f in ranked]
    assert order.index("sup") < order.index("prov")
    dup = next(f for f in ranked if f["finding_id"] == "dup")
    assert dup["duplicate_of"] == "sup" and order[-1] == "dup"
    assert [f["priority_rank"] for f in ranked] == [1, 2, 3]
    assert all(0 <= f["priority_score"] <= 100 and f["priority_components"] for f in ranked)


def _seg(i, a, b, t):
    return {"segment_id": f"s{i}", "interval": {"start_ms": a, "end_ms": b}, "text": t}


def _video():
    lines = ["Hi everyone and welcome back to the channel, great to see you.",
             "Before we start, a few words about how this channel works and what we do here.",
             "We talk about many things and we have done many videos in the past years.",
             "So let us get into it slowly, there is a lot to say about the topic today.",
             "Battery cells lose capacity in winter when cold slows the chemistry inside.",
             "For example, at minus ten degrees a phone battery holds 20 percent less charge.",
             "Battery cells lose capacity in winter when cold slows the chemistry inside them.",
             "Battery cells lose capacity in winter when cold slows the chemistry inside them all.",
             "Lithium plating is a problem that appears when charging is too fast in the cold.",
             "Thanks for watching, please like and subscribe and see you next time everyone."]
    return [_seg(i, i * 12_000, i * 12_000 + 12_000, t) for i, t in enumerate(lines)]


def test_findings_have_reviewable_shape_and_drop_moments_get_headlines():
    from pipeline.predict.evidence import analyse_transcript
    from pipeline.predict.features import build_features
    from pipeline.predict.risk import attach_findings
    segs = _video()
    T = 120_000
    st = {"hook_ms": None, "hook_end_ms": None, "first_substance_ms": 48_000,
          "promises": [{"obligation": "why batteries die in winter", "title_quote": "winter", "status": "fulfilled", "first_fulfil_ms": 48_000}],
          "spans": [{"kind": "outro", "interval": {"start_ms": 108_000, "end_ms": 120_000}},
                    {"kind": "cta", "interval": {"start_ms": 12_000, "end_ms": 20_000}}]}
    F, info = build_features(T, segs, [], st)
    ev = analyse_transcript(F, segs, T, info, st)
    by = {f["rule_id"]: f for f in ev["findings"]}
    assert {"long_preamble", "no_hook_identified", "delayed_title_payoff", "repetition", "cta_before_payoff"} <= by.keys()
    rep = by["repetition"]
    assert rep["rule_code"] == "B1" and rep["evidence_strength"] == "supported" and rep["earlier_start_ms"] == 48_000
    assert rep["mechanism"].startswith("Reuses wording from 0:48")
    assert "No hook was identified by these rules" in by["no_hook_identified"]["mechanism"]
    assert "there is no hook" not in by["no_hook_identified"]["mechanism"].lower()
    a1 = by["long_preamble"]
    assert a1["severity"] == "medium" and a1["needs_reanalysis"] is True and a1["group_label"]
    keys = {"finding_id", "rule_id", "rule_code", "cause_group", "group_label", "title", "start_ms", "end_ms", "status", "severity",
            "evidence_strength", "quote", "earlier_quote", "measurements", "mechanism", "counter_explanation", "suggestion",
            "preserve", "needs_reanalysis", "requires_reanalysis", "priority_score", "priority_rank"}
    assert all(keys <= f.keys() and f["status"] == "candidate" for f in ev["findings"])
    assert [f["priority_rank"] for f in ev["findings"]] == list(range(1, len(ev["findings"]) + 1))
    assert len(ev["risk_bins"]) == 24 and max(b["risk"] for b in ev["risk_bins"]) > 0
    assert set(ev["risk_weights"]) >= {"severity", "evidence", "group_alpha", "group_beta"}
    p = predict(F, duration_ms=T)
    m = drop_moments(p)
    attach_findings(m, ev["findings"], segs)
    assert m and all(x["headline"] and isinstance(x["finding_ids"], list) for x in m)
    rep_moment = next(x for x in m if x["reasons"][0]["feature"] == "repetition")
    assert "Repeats an earlier passage" in rep_moment["headline"] and rep["finding_id"] in rep_moment["finding_ids"]


def test_low_novelty_severity_drops_with_progress_markers_and_recap_excuses_repetition():
    from pipeline.predict.evidence import build_evidence
    from pipeline.predict.features import build_features
    F = [{"low_novelty": 0.9} if 40 <= t < 70 else {} for t in range(100)]
    plain = [_seg(0, 40_000, 70_000, "The thing we said is the thing we said about the thing.")]
    marked = [_seg(0, 40_000, 70_000, "For example the thing we said is the thing, because the thing.")]
    info = {"sources": []}
    f1 = build_evidence(F, plain, 100_000, info)["findings"][0]
    f2 = build_evidence(F, marked, 100_000, info)["findings"][0]
    assert f1["severity"] == "medium" and f2["severity"] == "low" and f2["measurements"]["progress_markers"]
    line = "Battery cells lose capacity in winter when cold slows the chemistry inside them."
    recap = [_seg(0, 0, 10_000, line), _seg(1, 10_000, 20_000, "To recap: " + line), _seg(2, 20_000, 30_000, "In summary, " + line)]
    Fr, _ = build_features(40_000, recap, [], None)
    assert all("repetition" not in f for f in Fr)
    plain_repeat = [_seg(0, 0, 10_000, line), _seg(1, 10_000, 20_000, "So, " + line), _seg(2, 20_000, 30_000, "Yes, " + line)]
    Fp, _ = build_features(40_000, plain_repeat, [], None)
    assert any("repetition" in f for f in Fp)


def test_packed_record_is_schema_valid_and_unpack_restores_contract():
    from contracts.entities import RetentionPrediction
    from pipeline.predict.evidence import analyse_transcript
    from pipeline.predict.features import build_features
    from pipeline.predict.risk import attach_findings
    from pipeline.predict.view import pack, unpack
    segs = _video()
    T = 120_000
    F, info = build_features(T, segs, [], {"hook_ms": 0, "hook_end_ms": 5000, "first_substance_ms": 48_000, "promises": [], "spans": []})
    ev = analyse_transcript(F, segs, T, info, None)
    p = predict(F, duration_ms=T)
    m = drop_moments(p)
    attach_findings(m, ev["findings"], segs)
    rec = {"prediction_id": "00000000-0000-4000-8000-000000000001", "run_id": "00000000-0000-4000-8000-000000000002",
           "model_version": p["model_version"], "label": p["label"], "calibrated": False, "anchors": p["anchors"],
           "features": [{k: round(v, 4) for k, v in f.items() if v} for f in F], "per_second": p["per_second"],
           "summary": p["summary"], "drop_moments": m, "weights": p["weights"], "notes": p["notes"], "analysis": ev,
           "feature_info": info, "risk_bins": ev["risk_bins"], "findings": ev["findings"], "baseline": p["baseline"],
           "risk_weights": ev["risk_weights"], "band_label": p["band_label"], "created_at": "2026-10-03T00:00:00Z"}
    packed = pack(rec)
    RetentionPrediction.model_validate(packed)
    out = unpack(packed)
    assert "features" not in out and out["baseline"]["shape_k"] == 0.6
    assert out["per_second"][-1]["cumulative_watch_s"] == p["per_second"][-1]["cumulative_watch_s"]
    assert out["drop_moments"][0]["headline"] == m[0]["headline"]
    assert out["findings"] == ev["findings"] and out["risk_bins"] == ev["risk_bins"]
    assert out["summary"]["watch_time"] == p["summary"]["watch_time"]
    # per-second risk equals the 5 s bin it falls in
    assert out["per_second"][7]["transcript_risk"] == ev["risk_bins"][1]["risk"]


def test_v2_package_is_upgraded_on_read():
    from pipeline.predict.view import unpack
    p = predict([{"repetition": 1} if 20 <= t < 40 else {} for t in range(60)],
                baseline=Baseline(1.0, 1.0, 0.0))
    v2 = {"model_version": "text-retention-v2", "label": p["label"], "calibrated": False, "anchors": p["anchors"],
          "per_second": [{k: v for k, v in x.items() if not k.endswith("cumulative_watch_s")} for x in p["per_second"]],
          "summary": {k: v for k, v in p["summary"].items() if k not in ("watch_time", "assumptions")},
          "drop_moments": [{k: v for k, v in x.items() if k != "headline"} for x in drop_moments(p)],
          "weights": {}, "notes": [], "features": [],
          "analysis": {"findings": [{"finding_id": "repetition:20000:40000", "rule_id": "repetition", "cause_group": "progress",
                                     "start_ms": 20_000, "end_ms": 40_000, "severity": "high", "evidence_strength": "provisional",
                                     "requires_reanalysis": True, "mechanism": "repeats earlier wording"}],
                       "risk_bins": [{"start_ms": 0, "end_ms": 5000, "score": 0}]}}
    out = unpack(v2)
    assert out["baseline"]["kind"] == "piecewise_constant_v2"
    assert out["per_second"][-1]["cumulative_watch_s"] == pytest.approx(p["summary"]["avd_s"]["central"], abs=0.02)
    assert out["findings"][0]["priority_rank"] == 1 and out["risk_bins"][5]["risk"] > 0
    assert out["drop_moments"][0]["headline"] and out["drop_moments"][0]["finding_ids"] == ["repetition:20000:40000"]
    assert out["summary"]["watch_time"]["avd_s"] == p["summary"]["avd_s"]["central"]
