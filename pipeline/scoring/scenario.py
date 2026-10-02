"""Uncalibrated first-pass survival scenario (RETENTION_MODEL §3–§4).

h(t) = h0(t) + (kappa/T) * r(t), piecewise constant per bin, split at 30 s.
S(end) = S(start) * exp(-h dt). AVD = integral S dt (exact per piece).
Lower survival uses the risk upper bound U[b]; upper survival uses L[b].
A central curve exists only when every bin has complete coverage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pipeline.scoring import FORMULA_VERSION
from pipeline.scoring.risk import BinRisk, top_regions

MIN_DURATION_S = 60.0
ANCHOR_S = 30.0
DEFAULT_ASSUMPTIONS = {"retention_at_30s": 0.80, "retention_at_end": 0.45, "kappa": 1.0, "acknowledged": False}

HEADER_LABEL = "Estimated retention — uncalibrated scenario"
SUBTEXT_LABEL = "Uses assumed audience behaviour. Percentages and edit differences are not measured predictions."


class ScenarioUnavailable(ValueError):
    """Raised when the formula's preconditions are not met (e.g. T < 60 s)."""


@dataclass(frozen=True)
class Assumptions:
    retention_at_30s: float = 0.80
    retention_at_end: float = 0.45
    kappa: float = 1.0

    def validate(self) -> None:
        a30, end = self.retention_at_30s, self.retention_at_end
        if not (0.0 < end <= a30 <= 1.0):
            raise ScenarioUnavailable("assumptions must satisfy 0 < end <= at30 <= 1")
        if not (0.0 <= self.kappa <= 10.0) or not math.isfinite(self.kappa):
            raise ScenarioUnavailable("kappa must be finite in [0,10]")


def baseline_hazard(t_s: float, T_s: float, a: Assumptions) -> float:
    if t_s < ANCHOR_S:
        return -math.log(a.retention_at_30s) / ANCHOR_S
    return -math.log(a.retention_at_end / a.retention_at_30s) / (T_s - ANCHOR_S)


def _pieces(b0_s: float, b1_s: float) -> list[tuple[float, float]]:
    if b0_s < ANCHOR_S < b1_s:
        return [(b0_s, ANCHOR_S), (ANCHOR_S, b1_s)]
    return [(b0_s, b1_s)]


def _integrate(S0: float, h: float, dt: float) -> tuple[float, float]:
    """Return (S_end, area) for constant hazard h over dt seconds."""
    if h <= 0.0:
        return S0, S0 * dt
    decay = math.exp(-h * dt)
    return S0 * decay, S0 * (1.0 - decay) / h


@dataclass
class Curve:
    starts: list[float]
    ends: list[float]
    avd_s: float


def survival_curve(bin_edges_ms: list[tuple[int, int]], risks: list[float], T_s: float, a: Assumptions) -> Curve:
    if len(bin_edges_ms) != len(risks):
        raise ValueError("one risk value per bin required")
    extra = a.kappa / T_s
    S, area = 1.0, 0.0
    starts, ends = [], []
    for (b0, b1), r in zip(bin_edges_ms, risks):
        if not (0.0 <= r <= 1.0) or not math.isfinite(r):
            raise ValueError(f"risk must be finite in [0,1], got {r}")
        starts.append(S)
        for p0, p1 in _pieces(b0 / 1000.0, b1 / 1000.0):
            h = baseline_hazard(p0, T_s, a) + extra * r
            S, piece_area = _integrate(S, h, p1 - p0)
            area += piece_area
        ends.append(S)
    return Curve(starts=starts, ends=ends, avd_s=area)


def _bound(lo: float, hi: float, central: float | None) -> dict:
    lo, hi = min(lo, hi), max(lo, hi)
    return {"lower": lo, "upper": hi, "central": central}


def compute_scenario(
    bins: list[BinRisk],
    duration_ms: int,
    assumptions: Assumptions,
    *,
    scoring_profile: str,
    extra_labels: list[str] | None = None,
) -> dict:
    """Return a dict shaped like contracts.RetentionScenario minus identity fields."""
    T_s = duration_ms / 1000.0
    if T_s < MIN_DURATION_S:
        raise ScenarioUnavailable(f"scenario requires duration >= {MIN_DURATION_S:.0f}s (got {T_s:.1f}s)")
    assumptions.validate()
    edges = [(b.start_ms, b.end_ms) for b in bins]
    if not edges or edges[0][0] != 0 or edges[-1][1] != duration_ms:
        raise ValueError("bins must span [0, duration)")

    complete = all(b.point is not None for b in bins)
    lower_surv = survival_curve(edges, [b.upper for b in bins], T_s, assumptions)  # pessimistic
    upper_surv = survival_curve(edges, [b.lower for b in bins], T_s, assumptions)  # optimistic
    central = upper_surv if complete else None  # complete => lower == upper risk
    base = survival_curve(edges, [0.0] * len(bins), T_s, Assumptions(
        assumptions.retention_at_30s, assumptions.retention_at_end, 0.0))

    out_bins = []
    for i, b in enumerate(bins):
        rs = _bound(lower_surv.starts[i], upper_surv.starts[i], central.starts[i] if central else None)
        re_ = _bound(lower_surv.ends[i], upper_surv.ends[i], central.ends[i] if central else None)

        def cond(c: Curve) -> float:
            return 1.0 - (c.ends[i] / c.starts[i]) if c.starts[i] > 0 else 0.0

        def absd(c: Curve) -> float:
            return c.starts[i] - c.ends[i]

        out_bins.append({
            "start_ms": b.start_ms,
            "end_ms": b.end_ms,
            "baseline_start": base.starts[i],
            "baseline_end": base.ends[i],
            "retention_start": rs,
            "retention_end": re_,
            "risk": _bound(b.lower, b.upper, b.point),
            "conditional_drop": _bound(cond(upper_surv), cond(lower_surv), cond(central) if central else None),
            "absolute_drop": _bound(absd(upper_surv), absd(lower_surv), absd(central) if central else None),
        })

    def pct(x: float) -> float:
        return 100.0 * x

    summary = {
        "duration_ms": duration_ms,
        "assumed_avd_seconds": _bound(lower_surv.avd_s, upper_surv.avd_s, central.avd_s if central else None),
        "assumed_apv_pct": _bound(pct(lower_surv.avd_s / T_s), pct(upper_surv.avd_s / T_s),
                                  pct(central.avd_s / T_s) if central else None),
        "assumed_end_pct": _bound(pct(lower_surv.ends[-1]), pct(upper_surv.ends[-1]),
                                  pct(central.ends[-1]) if central else None),
        "top_regions": top_regions(bins),
    }
    labels = [HEADER_LABEL, SUBTEXT_LABEL]
    if not complete:
        labels.append("Partial evidence coverage: ranges only, no central curve.")
    labels.extend(extra_labels or [])
    return {
        "mode": "baseline",
        "formula_version": FORMULA_VERSION,
        "scoring_profile": scoring_profile,
        "bins": out_bins,
        "summary": summary,
        "coverage_status": "complete" if complete else "partial",
        "labels": labels,
    }
