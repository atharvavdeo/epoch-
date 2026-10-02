from pipeline.scoring.hypothetical import coverage_spans_from_bins, hypothetical, map_span, map_time
from pipeline.scoring.risk import ScoredIssue
from pipeline.scoring.scenario import Assumptions

CUTS = [(10_000, 20_000), (40_000, 45_000)]


def test_time_mapping_removes_cut_spans():
    assert map_time(5_000, CUTS) == 5_000
    assert map_time(15_000, CUTS) == 10_000          # inside a cut -> cut point
    assert map_time(30_000, CUTS) == 20_000
    assert map_time(50_000, CUTS) == 35_000
    assert map_span(12_000, 18_000, CUTS) is None    # entirely cut
    assert map_span(5_000, 25_000, CUTS) == (5_000, 15_000)


def _rows(T, cov=1.0):
    return [{"interval": {"start_ms": a, "end_ms": min(T, a + 5000)},
             "track_values": {t: {"coverage": cov} for t in ("narrative", "visual", "pacing", "text", "technical")}}
            for a in range(0, T, 5000)]


def test_hypothetical_reports_both_apv_and_avd_and_drops_cut_issues():
    T = 120_000
    issues = [ScoredIssue("i1", "narrative", "high", "supported", 10_000, 20_000, "g1"),
              ScoredIssue("i2", "pacing", "medium", "supported", 60_000, 70_000, "g2")]
    out = hypothetical(T, issues, _rows(T), [(10_000, 20_000)], set(), Assumptions(0.8, 0.45, 1.0))
    assert out["status"] == "hypothetical" and out["removed_ms"] == 10_000
    assert out["removed_by_cut_issue_ids"] == ["i1"]
    assert out["after"]["duration_ms"] == 110_000 and out["before"]["duration_ms"] == T
    for side in ("before", "after"):
        assert out[side]["assumed_apv_pct"] and out[side]["assumed_avd_seconds"]


def test_partial_coverage_spans_are_derived_per_bin():
    cov = coverage_spans_from_bins(_rows(10_000, cov=0.5))
    assert cov["visual"] == [(0, 2500), (5000, 7500)]
