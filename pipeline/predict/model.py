"""Text retention model v1: rule-based proportional hazards over transcript features.

    h(t) = h0(t) * exp( sum_k  w_k * x_k(t) )        per 1-second bin
    S(t) = prod over bins of exp(-h * dt)

h0 is the assumed category baseline: piecewise-constant hazards chosen so a
*neutral* video (every feature 0) hits the assumption anchors S(30 s) and S(T)
exactly. Features then raise (w > 0) or lower (w < 0) the hazard relative to
that neutral video. The weights are documented PRIORS chosen by reasoning about
how viewers behave, not fitted to data: no audience data exists for this
project (owner decision 2026-10-03). Every output is labelled uncalibrated.

The band is a sensitivity band: every weight scaled by 0.5x and 1.5x. It is
not a statistical confidence interval.

Pure Python (no numpy) so the API process can recompute with new assumptions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MODEL_VERSION = "text-retention-v1"
LABEL = "Predicted retention — rule-based text model, uncalibrated"

# feature -> (weight = log hazard ratio at x=1, plain-language reason shown to the creator, rationale for reviewers)
WEIGHTS: dict[str, tuple[float, str, str]] = {
    "setup_before_substance": (0.6, "still in setup before the first real point",
                               "early viewers are checking whether the video delivers what the title promised"),
    "no_hook_yet": (0.5, "no concrete reason to keep watching has been given yet",
                    "a question, promise or teaser in the opening gives viewers a reason to stay"),
    "payoff_pending": (0.5, "the title's promise has not started to be delivered",
                       "the longer the promised answer is delayed, the more viewers give up on it"),
    "low_novelty": (0.5, "little new information here (mostly words already used)",
                    "passages that add few new ideas feel slow even at a normal speaking pace"),
    "repetition": (0.7, "repeats earlier wording",
                   "hearing the same sentences again is the clearest sign of padding"),
    "slow_pace": (0.4, "speaking noticeably slower than the rest of the video",
                  "measured against this speaker's own median, not a universal ideal"),
    "fast_pace": (0.3, "speaking noticeably faster than the rest of the video",
                  "bursts much faster than the speaker's norm can lose viewers who are following closely"),
    "filler_density": (0.3, "a cluster of filler words",
                       "um/uh/you know clusters signal unprepared delivery; meaningful discourse words are not counted"),
    "dead_air": (1.0, "quiet with no speech",
                 "silence gives no reason to stay; measured on the waveform, not just the absence of speech"),
    "cta_or_sponsor": (0.8, "call to action or sponsor segment before the content is finished",
                       "asks and ads in the middle interrupt the reason viewers came"),
    "outro": (0.6, "wrap-up / outro",
              "once viewers sense the end, many leave before the final seconds"),
    "long_sentences": (0.2, "long, complex sentences",
                       "sentences over ~30 words are harder to follow by ear"),
    "open_loop": (-0.4, "an open question or tease is keeping curiosity up",
                  "an unanswered question gives viewers a reason to wait for the answer"),
    "concrete": (-0.2, "concrete numbers or examples",
                 "specifics hold attention better than abstract claims"),
}


@dataclass
class Anchors:
    retention_at_30s: float = 0.80
    retention_at_end: float = 0.45


def _baseline(T_s: int, a: Anchors) -> list[float]:
    """Per-second neutral hazard hitting S(30)=a30 and S(T)=aend (piecewise constant, split at 30 s)."""
    if T_s <= 30:
        return [-math.log(max(1e-6, a.retention_at_end)) / max(1, T_s)] * T_s
    h1 = -math.log(a.retention_at_30s) / 30.0
    h2 = -math.log(a.retention_at_end / a.retention_at_30s) / (T_s - 30)
    return [h1] * 30 + [h2] * (T_s - 30)


def _curve(features: list[dict[str, float]], a: Anchors, scale: float) -> tuple[list[float], list[float], list[float]]:
    T_s = len(features)
    h0 = _baseline(T_s, a)
    hz, surv = [], [1.0]
    for t in range(T_s):
        lp = sum(WEIGHTS[k][0] * scale * v for k, v in features[t].items() if k in WEIGHTS and v)
        h = h0[t] * math.exp(lp)
        hz.append(h)
        surv.append(surv[-1] * math.exp(-h))
    return h0, hz, surv


def _avd(surv: list[float], hz: list[float]) -> float:
    """Exact integral of S(t) over piecewise-constant hazards (seconds)."""
    tot = 0.0
    for t, h in enumerate(hz):
        tot += surv[t] * (1 - math.exp(-h)) / h if h > 1e-12 else surv[t]
    return tot


def predict(features: list[dict[str, float]], anchors: Anchors | None = None) -> dict:
    """features: one dict per second (feature -> 0..1). Returns curve, band, attribution and summary."""
    a = anchors or Anchors()
    if not (0 < a.retention_at_end <= a.retention_at_30s <= 1):
        raise ValueError("require 0 < retention_at_end <= retention_at_30s <= 1")
    T_s = len(features)
    if T_s < 10:
        raise ValueError("too short to model (< 10 s)")
    h0, hz, s = _curve(features, a, 1.0)
    _, hz_lo, s_lo = _curve(features, a, 0.5)
    _, hz_hi, s_hi = _curve(features, a, 1.5)
    _, hz_n, s_n = _curve([{} for _ in features], a, 1.0)  # neutral video, same anchors

    per_second = []
    for t in range(T_s):
        lp_parts = {k: WEIGHTS[k][0] * v for k, v in features[t].items() if k in WEIGHTS and v}
        loss = s[t] - s[t + 1]  # absolute share of starting viewers lost in this second
        excess = max(0.0, hz[t] - h0[t])
        pos = {k: c for k, c in lp_parts.items() if c > 0}
        ptot = sum(pos.values())
        # attribute the excess loss over the neutral baseline to positive features by share of log-hazard
        excess_loss = s[t] * (1 - math.exp(-excess)) if excess > 0 else 0.0
        per_second.append({"t": t, "retention": round(s[t + 1], 6), "lower": round(min(s_lo[t + 1], s_hi[t + 1]), 6),
                           "upper": round(max(s_lo[t + 1], s_hi[t + 1]), 6), "neutral": round(s_n[t + 1], 6),
                           "loss": round(loss, 6), "excess_loss": round(excess_loss, 6),
                           "contributions": {k: round(excess_loss * c / ptot, 6) for k, c in pos.items()} if ptot else {},
                           "protective": [k for k, c in lp_parts.items() if c < 0]})
    avd, avd_lo, avd_hi, avd_n = _avd(s, hz), _avd(s_lo, hz_lo), _avd(s_hi, hz_hi), _avd(s_n, hz_n)
    totals: dict[str, float] = {}
    for p in per_second:
        for k, v in p["contributions"].items():
            totals[k] = totals.get(k, 0.0) + v
    return {
        "model_version": MODEL_VERSION, "label": LABEL, "calibrated": False,
        "anchors": {"retention_at_30s": a.retention_at_30s, "retention_at_end": a.retention_at_end},
        "per_second": per_second,
        "summary": {
            "duration_s": T_s,
            "avd_s": {"central": round(avd, 2), "lower": round(min(avd_lo, avd_hi), 2), "upper": round(max(avd_lo, avd_hi), 2)},
            "apv_pct": {"central": round(100 * avd / T_s, 2), "lower": round(100 * min(avd_lo, avd_hi) / T_s, 2),
                        "upper": round(100 * max(avd_lo, avd_hi) / T_s, 2)},
            "end_pct": {"central": round(100 * s[-1], 2), "lower": round(100 * min(s_lo[-1], s_hi[-1]), 2),
                        "upper": round(100 * max(s_lo[-1], s_hi[-1]), 2)},
            "neutral_avd_s": round(avd_n, 2), "neutral_end_pct": round(100 * s_n[-1], 2),
            "excess_loss_by_feature": {k: round(v, 5) for k, v in sorted(totals.items(), key=lambda kv: -kv[1])},
        },
        "weights": {k: {"weight": w, "reason": r, "rationale": why} for k, (w, r, why) in WEIGHTS.items()},
        "notes": ["Weights are documented priors, not fitted to audience data.",
                  "Band = every weight scaled 0.5x..1.5x (sensitivity), not a confidence interval.",
                  "Anchors describe an assumed neutral video in this category; change them to explore."],
    }


def drop_moments(pred: dict, k: int = 8, min_gap_s: int = 15) -> list[dict]:
    """Top windows by excess loss (10 s windows), non-overlapping, with dominant reasons."""
    ps = pred["per_second"]
    win = 10
    scored = []
    for t0 in range(0, max(1, len(ps) - win + 1)):
        seg = ps[t0:t0 + win]
        ex = sum(p["excess_loss"] for p in seg)
        if ex > 0:
            scored.append((ex, t0))
    scored.sort(reverse=True)
    out: list[dict] = []
    for ex, t0 in scored:
        if any(abs(t0 - o["start_s"]) < min_gap_s for o in out):
            continue
        seg = ps[t0:t0 + win]
        contrib: dict[str, float] = {}
        for p in seg:
            for f, v in p["contributions"].items():
                contrib[f] = contrib.get(f, 0.0) + v
        reasons = sorted(contrib.items(), key=lambda kv: -kv[1])[:3]
        out.append({"start_s": t0, "end_s": min(len(ps), t0 + win), "excess_loss": round(ex, 6),
                    "retention_before": seg[0]["retention"] + seg[0]["loss"], "retention_after": seg[-1]["retention"],
                    "reasons": [{"feature": f, "share": round(v / ex, 3), "text": WEIGHTS[f][1]} for f, v in reasons]})
        if len(out) >= k:
            break
    return sorted(out, key=lambda o: o["start_s"])
