"""RETENTION_MODEL §7 golden fixtures. These prove implementation correctness
only; they say nothing about real audience behaviour."""

import math

import pytest

from pipeline.scoring.risk import PROFILES, ScoredIssue, compute_risk, make_bins
from pipeline.scoring.scenario import Assumptions, ScenarioUnavailable, compute_scenario, survival_curve

ALL = {t: [(0, 10_000_000)] for t in PROFILES["multimodal-v1"]}


def _full(T_ms):
    return {t: [(0, T_ms)] for t in PROFILES["multimodal-v1"]}


def _iss(i, track="narrative", sev="high", ev="supported", s=0, e=1000, group=None):
    return ScoredIssue(issue_id=f"i{i}", track=track, severity=sev, evidence_status=ev,
                       start_ms=s, end_ms=e, cause_group_id=group or f"g{i}")


def _S_at(curve_edges, curve, t_ms):
    for (b0, b1), s0, s1 in zip(curve_edges, curve.starts, curve.ends):
        if b0 == t_ms:
            return s0
        if b1 == t_ms:
            return s1
    raise AssertionError("t not on a bin edge")


def test_zero_risk_full_coverage_hits_anchors():
    T = 600_000
    bins = compute_risk(T, [], _full(T))
    edges = [(b.start_ms, b.end_ms) for b in bins]
    c = survival_curve(edges, [b.point for b in bins], 600.0, Assumptions())
    assert abs(_S_at(edges, c, 30_000) - 0.80) < 1e-6
    assert abs(c.ends[-1] - 0.45) < 1e-6


def test_uniform_risk_one_gives_045_times_e_minus_one():
    T = 600_000
    edges = make_bins(T)
    c = survival_curve(edges, [1.0] * len(edges), 600.0, Assumptions(kappa=1.0))
    assert abs(c.ends[-1] - 0.45 * math.exp(-1)) < 1e-6
    assert abs(100 * c.ends[-1] - 16.55) < 0.01


def test_unknown_visual_track_widens_bounds_and_blocks_central():
    T = 600_000
    cov = _full(T)
    cov["visual"] = []
    bins = compute_risk(T, [], cov)
    assert all(abs((b.upper - b.lower) - 0.25) < 1e-9 for b in bins)
    assert all(b.point is None for b in bins)
    sc = compute_scenario(bins, T, Assumptions(), scoring_profile="multimodal-v1")
    assert sc["coverage_status"] == "partial"
    assert sc["summary"]["assumed_apv_pct"]["central"] is None
    assert all(b["retention_end"]["central"] is None for b in sc["bins"])


def test_all_zero_hazard_branch_is_safe():
    T = 600_000
    bins = compute_risk(T, [], _full(T))
    sc = compute_scenario(bins, T, Assumptions(1.0, 1.0, 1.0), scoring_profile="multimodal-v1")
    assert abs(sc["summary"]["assumed_avd_seconds"]["central"] - 600.0) < 1e-9
    assert abs(sc["summary"]["assumed_apv_pct"]["central"] - 100.0) < 1e-9


def test_half_bin_overlap_contributes_half_weighted_severity():
    T = 600_000
    bins = compute_risk(T, [_iss(1, s=0, e=2500)], _full(T))
    assert abs(bins[0].tracks["narrative"].risk - 0.5) < 1e-12
    assert abs(bins[0].point - 0.30 * 0.5) < 1e-12


def test_same_cause_duplicates_do_not_stack():
    T = 600_000
    a = compute_risk(T, [_iss(1, sev="high", group="g"), _iss(2, sev="medium", group="g")], _full(T))
    b = compute_risk(T, [_iss(1, sev="high", group="g")], _full(T))
    assert a[0].tracks["narrative"].risk == b[0].tracks["narrative"].risk == 0.2  # 1000/5000 of high
    # distinct causes in one track also take the max, not the sum
    c = compute_risk(T, [_iss(1, group="g1"), _iss(2, group="g2")], _full(T))
    assert c[0].tracks["narrative"].risk == 0.2


def test_601s_video_has_120_full_bins_and_one_short_bin():
    edges = make_bins(601_000)
    assert len(edges) == 121 and edges[-1] == (600_000, 601_000)
    assert all(e - s == 5000 for s, e in edges[:-1])
    bins = compute_risk(601_000, [], _full(601_000))
    sc = compute_scenario(bins, 601_000, Assumptions(1.0, 1.0, 1.0), scoring_profile="multimodal-v1")
    assert abs(sc["summary"]["assumed_avd_seconds"]["central"] - 601.0) < 1e-9


def test_dismissed_issue_still_counts_unless_scenario_excludes_it():
    T = 600_000
    issues = [_iss(1, s=0, e=5000)]
    assert compute_risk(T, issues, _full(T))[0].point > 0  # review status is not an input at all
    assert compute_risk(T, issues, _full(T), exclude_issue_ids=frozenset({"i1"}))[0].point == 0


def test_provisional_half_weight_and_script_profile_rejects_visual():
    T = 600_000
    bins = compute_risk(T, [_iss(1, ev="provisional", s=0, e=5000)], _full(T))
    assert bins[0].tracks["narrative"].risk == 0.5
    with pytest.raises(ValueError):
        compute_risk(T, [_iss(1, track="visual")], {"narrative": [(0, T)], "pacing": [(0, T)]},
                     profile="script-only-v1")


def test_short_duration_and_bad_assumptions_refuse():
    bins = compute_risk(50_000, [], _full(50_000))
    with pytest.raises(ScenarioUnavailable):
        compute_scenario(bins, 50_000, Assumptions(), scoring_profile="multimodal-v1")
    bins = compute_risk(600_000, [], _full(600_000))
    with pytest.raises(ScenarioUnavailable):
        compute_scenario(bins, 600_000, Assumptions(0.5, 0.6), scoring_profile="multimodal-v1")


def test_top_regions_merge_same_cause_and_rank_by_risk_times_duration():
    T = 600_000
    issues = [_iss(1, s=10_000, e=40_000, group="A"), _iss(2, sev="low", s=100_000, e=105_000, group="B")]
    bins = compute_risk(T, issues, _full(T))
    sc = compute_scenario(bins, T, Assumptions(), scoring_profile="multimodal-v1")
    regions = sc["summary"]["top_regions"]
    assert regions[0]["interval"] == {"start_ms": 10_000, "end_ms": 40_000}
    assert regions[0]["issue_ids"] == ["i1"]
    assert len(regions) == 2
