"""Diagnostic risk per 5 s bin (RETENTION_MODEL §2).

contribution(j,b) = severity_j * evidence_weight_j * overlap(j,b)/len(b)
cause-group value = max over its issues; track risk r[k,b] = max over groups.
Coverage c[k,b] widens the bound: l = c*r, u = c*r + (1-c). Combined bounds
are weighted sums. A point value exists only when combined coverage is 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BIN_MS = 5000
SEVERITY = {"low": 1.0 / 3.0, "medium": 2.0 / 3.0, "high": 1.0}
EVIDENCE_WEIGHT = {"supported": 1.0, "provisional": 0.5}
PROFILES: dict[str, dict[str, float]] = {
    "multimodal-v1": {"narrative": 0.30, "visual": 0.25, "pacing": 0.20, "text": 0.15, "technical": 0.10},
    "script-only-v1": {"narrative": 0.75, "pacing": 0.25},
}
_EPS = 1e-9


@dataclass(frozen=True)
class ScoredIssue:
    issue_id: str
    track: str
    severity: str
    evidence_status: str
    start_ms: int
    end_ms: int
    cause_group_id: str


@dataclass
class TrackBin:
    risk: float | None
    coverage: float
    lower: float
    upper: float


@dataclass
class BinRisk:
    start_ms: int
    end_ms: int
    tracks: dict[str, TrackBin]
    lower: float
    upper: float
    coverage: float
    point: float | None
    contributing_issue_ids: list[str]
    dominant_cause_group_id: str | None
    dominant_issue_ids: list[str] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return (self.end_ms - self.start_ms) / 1000.0


def make_bins(duration_ms: int, bin_ms: int = BIN_MS) -> list[tuple[int, int]]:
    if duration_ms <= 0:
        raise ValueError("duration must be positive")
    return [(s, min(s + bin_ms, duration_ms)) for s in range(0, duration_ms, bin_ms)]


def _overlap(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def coverage_fraction(spans: list[tuple[int, int]], b0: int, b1: int) -> float:
    """Fraction of [b0,b1) covered by the union of observed spans."""
    pieces = sorted((max(s, b0), min(e, b1)) for s, e in spans if _overlap(s, e, b0, b1) > 0)
    covered, cur_s, cur_e = 0, None, None
    for s, e in pieces:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                covered += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        covered += cur_e - cur_s
    return _clamp01(covered / (b1 - b0))


def compute_risk(
    duration_ms: int,
    issues: list[ScoredIssue],
    track_coverage: dict[str, list[tuple[int, int]]],
    profile: str = "multimodal-v1",
    exclude_issue_ids: frozenset[str] = frozenset(),
) -> list[BinRisk]:
    """Risk bins for one run.

    track_coverage maps each profile track to its observed spans. A track with
    no spans is wholly unknown ([0,1]), never zero risk (R06).
    exclude_issue_ids is only for explicit scenario configurations; review
    status alone never removes an issue (RETENTION_MODEL §7 last fixture).
    """
    weights = PROFILES[profile]
    for t in track_coverage:
        if t not in weights:
            raise ValueError(f"track {t!r} is not part of profile {profile}")
    for iss in issues:
        if iss.track not in weights:
            raise ValueError(f"issue {iss.issue_id} uses track {iss.track} outside profile {profile}")
        if iss.evidence_status not in EVIDENCE_WEIGHT:
            raise ValueError(f"issue {iss.issue_id}: evidence_status {iss.evidence_status} cannot be scored")

    out: list[BinRisk] = []
    for b0, b1 in make_bins(duration_ms):
        blen = b1 - b0
        # group -> (best contribution, issue ids in group overlapping this bin)
        per_track: dict[str, dict[str, tuple[float, list[str]]]] = {t: {} for t in weights}
        for iss in issues:
            if iss.issue_id in exclude_issue_ids:
                continue
            ov = _overlap(iss.start_ms, iss.end_ms, b0, b1)
            if ov <= 0:
                continue
            contrib = SEVERITY[iss.severity] * EVIDENCE_WEIGHT[iss.evidence_status] * (ov / blen)
            groups = per_track[iss.track]
            best, ids = groups.get(iss.cause_group_id, (0.0, []))
            groups[iss.cause_group_id] = (max(best, contrib), ids + [iss.issue_id])

        tracks: dict[str, TrackBin] = {}
        lower = upper = cov_total = 0.0
        contributing: list[str] = []
        dominant: tuple[float, str | None, list[str]] = (0.0, None, [])
        for t, w in weights.items():
            c = coverage_fraction(track_coverage.get(t, []), b0, b1)
            groups = per_track[t]
            r = max((v for v, _ in groups.values()), default=0.0)
            r = _clamp01(r)
            if c <= _EPS:
                tb = TrackBin(risk=None, coverage=0.0, lower=0.0, upper=1.0)
            else:
                tb = TrackBin(risk=r, coverage=c, lower=c * r, upper=_clamp01(c * r + (1.0 - c)))
            tracks[t] = tb
            lower += w * tb.lower
            upper += w * tb.upper
            cov_total += w * tb.coverage
            for gid, (v, ids) in groups.items():
                contributing.extend(ids)
                if w * v > dominant[0] + _EPS:
                    dominant = (w * v, gid, ids)
        complete = cov_total >= 1.0 - 1e-9
        out.append(
            BinRisk(
                start_ms=b0,
                end_ms=b1,
                tracks=tracks,
                lower=_clamp01(lower),
                upper=_clamp01(upper),
                coverage=_clamp01(cov_total),
                point=_clamp01(lower) if complete else None,
                contributing_issue_ids=sorted(set(contributing)),
                dominant_cause_group_id=dominant[1],
                dominant_issue_ids=sorted(set(dominant[2])),
            )
        )
    return out


def top_regions(bins: list[BinRisk], limit: int = 5) -> list[dict]:
    """Top non-overlapping editable-risk regions (RETENTION_MODEL §4).

    Adjacent flagged bins sharing a dominant cause merge into one region.
    Score = max evidence-backed risk (lower bound) x duration in seconds, so
    unknown coverage alone can never rank a region highly.
    """
    regions: list[dict] = []
    cur: dict | None = None
    for b in bins:
        flagged = b.dominant_cause_group_id is not None
        if flagged and cur is not None and cur["cause"] == b.dominant_cause_group_id and cur["end_ms"] == b.start_ms:
            cur["end_ms"] = b.end_ms
            cur["max_risk"] = max(cur["max_risk"], b.lower)
            cur["issue_ids"] |= set(b.contributing_issue_ids)
            continue
        if cur is not None:
            regions.append(cur)
            cur = None
        if flagged:
            cur = {"start_ms": b.start_ms, "end_ms": b.end_ms, "max_risk": b.lower,
                   "cause": b.dominant_cause_group_id, "issue_ids": set(b.contributing_issue_ids)}
    if cur is not None:
        regions.append(cur)
    for r in regions:
        r["score"] = r["max_risk"] * (r["end_ms"] - r["start_ms"]) / 1000.0
    regions.sort(key=lambda r: (-r["score"], r["start_ms"]))
    return [
        {"interval": {"start_ms": r["start_ms"], "end_ms": r["end_ms"]}, "max_risk": r["max_risk"],
         "score": r["score"], "dominant_cause_group_id": r["cause"], "issue_ids": sorted(r["issue_ids"])}
        for r in regions[:limit]
    ]
