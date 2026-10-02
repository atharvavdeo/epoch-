"""Hypothetical edit scenario (RETENTION_MODEL §5, P2 mode 1).

The source timeline is transformed by validated cuts: issue intervals and
coverage spans are mapped onto the retained timeline, issues entirely inside
a cut disappear, and the same risk and scenario code runs on the new duration
with the SAME assumptions. Issues the user explicitly assumes resolved are
listed separately (never inferred from review status). Moves, rewrites and
insertions are not modelled: they need a reanalysed video.

Both sides are computed through this module (coverage spans derived from the
stored per-bin coverage) so the comparison is like-for-like. Output is labelled
hypothetical; APV and AVD are reported together with the duration change and
no winner is declared.
"""

from __future__ import annotations

from pipeline.scoring.risk import ScoredIssue, compute_risk
from pipeline.scoring.scenario import Assumptions, ScenarioUnavailable, compute_scenario


def merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(spans):
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def map_time(t: int, cuts: list[tuple[int, int]]) -> int:
    """Source time -> edited time. A time inside a cut maps to the cut point."""
    shift = 0
    for a, b in cuts:
        if t >= b:
            shift += b - a
        elif t > a:
            return a - shift
        else:
            break
    return t - shift


def map_span(a: int, b: int, cuts: list[tuple[int, int]]) -> tuple[int, int] | None:
    na, nb = map_time(a, cuts), map_time(b, cuts)
    return (na, nb) if nb > na else None


def coverage_spans_from_bins(risk_rows: list[dict]) -> dict[str, list[tuple[int, int]]]:
    """Per-track observed spans from stored bins: a bin with coverage c contributes its first c of length."""
    cov: dict[str, list[tuple[int, int]]] = {}
    for r in risk_rows:
        a, b = r["interval"]["start_ms"], r["interval"]["end_ms"]
        for track, v in r["track_values"].items():
            c = float(v["coverage"])
            if c > 0:
                cov.setdefault(track, []).append((a, a + round((b - a) * min(1.0, c))))
    return {t: merge(s) for t, s in cov.items()}


def _scenario(T: int, issues: list[ScoredIssue], cov: dict, assumptions: Assumptions, exclude: frozenset[str]):
    bins = compute_risk(T, issues, cov, profile="multimodal-v1", exclude_issue_ids=exclude)
    return compute_scenario(bins, T, assumptions, scoring_profile="multimodal-v1")


def hypothetical(duration_ms: int, issues: list[ScoredIssue], risk_rows: list[dict], cuts: list[tuple[int, int]],
                 resolved_ids: set[str], assumptions: Assumptions) -> dict:
    cuts = merge([(max(0, a), min(duration_ms, b)) for a, b in cuts])
    removed_ms = sum(b - a for a, b in cuts)
    T2 = duration_ms - removed_ms
    cov = coverage_spans_from_bins(risk_rows)
    try:
        before = _scenario(duration_ms, issues, cov, assumptions, frozenset())
    except ScenarioUnavailable as exc:
        return {"status": "not_comparable", "reason": str(exc)}
    moved, gone = [], []
    for i in issues:
        span = map_span(i.start_ms, i.end_ms, cuts)
        if span is None:
            gone.append(i.issue_id)
        else:
            moved.append(ScoredIssue(i.issue_id, i.track, i.severity, i.evidence_status, span[0], span[1], i.cause_group_id))
    cov2 = {t: merge([s for s in (map_span(a, b, cuts) for a, b in spans) if s]) for t, spans in cov.items()}
    try:
        after = _scenario(T2, moved, cov2, assumptions, frozenset(resolved_ids))
    except ScenarioUnavailable as exc:
        return {"status": "not_comparable", "reason": f"edited duration: {exc}"}

    def summary(sc: dict) -> dict:
        s = sc["summary"]
        return {"duration_ms": s["duration_ms"], "assumed_avd_seconds": s["assumed_avd_seconds"],
                "assumed_apv_pct": s["assumed_apv_pct"], "assumed_end_pct": s["assumed_end_pct"],
                "coverage_status": sc["coverage_status"]}

    return {"status": "hypothetical", "label": "Hypothetical edit scenario — uncalibrated, assumed audience",
            "cuts": [{"start_ms": a, "end_ms": b} for a, b in cuts], "removed_ms": removed_ms,
            "removed_by_cut_issue_ids": gone, "assumed_resolved_issue_ids": sorted(resolved_ids),
            "before": summary(before), "after": summary(after),
            "not_modelled": "moves, rewrites, inserted visuals and audio fixes need a reanalysed video",
            "note": "Shorter videos can raise % viewed while lowering seconds watched; compare both. No winner is declared."}
