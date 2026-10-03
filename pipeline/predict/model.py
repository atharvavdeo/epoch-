"""Text retention model v3: rule-based proportional hazards over transcript features.

    h(t) = h0(t) * exp( sum_c  beta_c * g_c(t) )        per 1-second bin
    S(t) = prod over bins of exp(-h * dt)

g_c(t) is the *deduplicated* signal of cause group c: the strongest feature of that group at time t, scaled by
its relative intensity (feature weight / group beta). Related symptoms of one cause never add up.

h0 is an explicit, documented baseline shape (not data):
  * opening segment 0..30 s:  H0(t) = -ln(a) * (t/30)^k             (Weibull-type, decreasing hazard)
  * after 30 s:              H0(t) = H0(30) + lambda * W(t),  W(t) = int_30^t m(s) * d(s^k)
    where m(s) = end_drop_multiplier in the last end_drop_fraction of the duration and 1 elsewhere.
  lambda is solved in closed form so a *neutral* video (every feature 0) hits S(30) = a and S(T) = z exactly.
  With k < 1 the hazard falls over time (viewers who stayed are less likely to leave), so the neutral curve
  bends instead of being a straight line. k = 1 and m = 1 reproduce the v2 piecewise-constant baseline.
  Videos of 30 s or less use one Weibull segment from 0 that hits S(T) = z.
Per bin the baseline hazard is the exact average dH0/dt, so survival at every bin edge is exact.

The weights are documented PRIORS chosen by reasoning about how viewers behave, not fitted to data: no audience
data exists for this project (owner decision 2026-10-03). Every output is labelled uncalibrated.

The band is an assumption-sensitivity band: every weight scaled by 0.5x and 1.5x. It is not a statistical
confidence interval.

Pure Python (no numpy) so the API process can recompute with new assumptions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MODEL_VERSION = "text-retention-v3"
LABEL = "Retention scenario — explicit assumptions, uncalibrated"
BAND_LABEL = "Assumption sensitivity: every weight x0.5 and x1.5 (not a confidence interval)"

# feature -> (weight = log hazard ratio at x=1, plain-language reason shown to the creator, rationale for reviewers)
WEIGHTS: dict[str, tuple[float, str, str]] = {
    "micro_variation": (0.25, "moment-to-moment slowdown: slower, quieter or longer without a cut than this video's norm",
                        "small signed adjustment from measured pace, loudness and cut timing; it gives the curve "
                        "its texture and can also lower leaving when delivery picks up"),
    "setup_before_substance": (0.6, "still in setup before the first real point",
                               "early viewers are checking whether the video delivers what the title promised"),
    "no_hook_yet": (0.5, "no opening hook identified by these rules yet",
                    "a question, promise or teaser in the opening gives viewers a reason to stay"),
    "payoff_pending": (0.5, "no title payoff identified yet",
                       "the longer the promised answer is delayed, the more viewers give up on it"),
    "low_novelty": (0.5, "low lexical novelty: mostly previously used content terms",
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
    "outro": (0.6, "closing cue or recap detected",
              "once viewers sense the end, many leave before the final seconds"),
    "long_sentences": (0.2, "punctuated sentence longer than 30 words",
                       "sentences over ~30 words are harder to follow by ear"),
    # --- measured visual / on-screen text / audio-energy signals (all optional; absent data -> feature off)
    "long_static_shot": (0.4, "one static shot held much longer than this video's usual shot",
                         "a long unchanging picture gives the eye nothing new; measured from shot cuts and motion"),
    "dense_text_fast_speech": (0.3, "dense on-screen text while the speaker talks fast",
                               "viewers cannot read a lot of text and follow fast speech at the same time"),
    "flat_low_energy": (0.2, "flatter, quieter delivery than this speaker's norm",
                        "sustained low pitch variation and loudness relative to the same speaker; not an emotion judgement"),
    "loudness_drop": (0.4, "sudden loudness drop while speech continues",
                      "a sharp level drop is hard to hear and often signals a recording problem"),
    "open_loop": (-0.4, "question or tease candidate (weak protective assumption)",
                  "an unanswered question gives viewers a reason to wait for the answer"),
    "concrete": (-0.2, "concrete numbers or examples",
                 "specifics hold attention better than abstract claims"),
    "fresh_visual_change": (-0.15, "fresh cut or visual change (weak protective assumption)",
                            "a new picture renews visual interest; capped so it cannot cancel a detected risk"),
    "new_onscreen_text": (-0.15, "new on-screen text appears (weak protective assumption)",
                          "a new caption or label adds information; capped so it cannot cancel a detected risk"),
    "energy_lift": (-0.1, "louder, livelier delivery than this speaker's norm (weak protective assumption)",
                    "a lift in loudness relative to the same speaker can renew attention; not an emotion judgement"),
}
PROTECTIVE = ("open_loop", "concrete", "fresh_visual_change", "new_onscreen_text", "energy_lift")

# Plain sentences for drop-moment headlines (what happens there), keyed by feature.
HEADLINES: dict[str, str] = {
    "setup_before_substance": "The video is still setting up before its first real point",
    "no_hook_yet": "No opening hook has been identified by these rules yet",
    "payoff_pending": "The answer promised by the title has not arrived yet",
    "low_novelty": "Few new ideas are added in this stretch",
    "repetition": "This passage repeats earlier wording",
    "slow_pace": "The speaker slows down noticeably compared with the rest of the video",
    "fast_pace": "The speaker speeds up noticeably compared with the rest of the video",
    "filler_density": "Several filler words cluster here",
    "dead_air": "There is a quiet gap with no speech",
    "cta_or_sponsor": "A call to action or sponsor segment interrupts the content",
    "outro": "Closing cues signal that the video is ending",
    "long_sentences": "A very long sentence makes this part harder to follow by ear",
    "long_static_shot": "One static shot is held much longer than usual for this video",
    "dense_text_fast_speech": "Dense on-screen text competes with fast speech",
    "flat_low_energy": "Delivery is flatter and quieter than this speaker's norm",
    "loudness_drop": "The audio level drops sharply while speech continues",
    "micro_variation": "Delivery slows here: slower, quieter or longer without a cut than this video's norm",
}

GROUP_ORDER = ("opening_promise", "progress", "comprehension", "questions_payoff", "interruptions", "delivery",
               "visual_pacing")
GROUPS: dict[str, tuple[str, ...]] = {
    "opening_promise": ("setup_before_substance", "no_hook_yet", "payoff_pending"),
    "progress": ("low_novelty", "repetition"),
    "comprehension": ("long_sentences", "dense_text_fast_speech"),
    "questions_payoff": (),  # review-only: lexical callbacks cannot establish an unanswered question
    "interruptions": ("cta_or_sponsor", "outro"),
    "delivery": ("slow_pace", "fast_pace", "filler_density", "dead_air", "flat_low_energy", "loudness_drop"),
    "visual_pacing": ("long_static_shot",),
}
GROUP_LABELS = {
    "opening_promise": "Opening and title promise",
    "progress": "Progress and new information",
    "comprehension": "Ease of following",
    "questions_payoff": "Questions and payoffs",
    "interruptions": "Interruptions and ending",
    "delivery": "Delivery (pace, fillers, silence, energy)",
    "visual_pacing": "Visual pacing",
}
FEATURE_GROUP = {k: g for g, keys in GROUPS.items() for k in keys}

# beta_c: log hazard ratio of a cause group at full strength (= the strongest feature weight in the group).
GROUP_BETA: dict[str, tuple[float, str]] = {
    g: (max((WEIGHTS[k][0] for k in keys), default=0.0), why) for g, why in (
        ("opening_promise", "a delayed or missing promise is the main early reason to leave"),
        ("progress", "verbatim repetition is the clearest padding signal; low novelty is weaker"),
        ("comprehension", "long sentences / text-speech overload are only mildly harder; kept small"),
        ("questions_payoff", "not scored: question callbacks are lexical candidates and need review"),
        ("interruptions", "mid-content asks and ads interrupt the reason viewers came"),
        ("delivery", "measured waveform silence is the strongest delivery signal"),
        ("visual_pacing", "a long static shot is a moderate risk; its effect depends on what is shown"),
    ) for keys in [GROUPS[g]]}

# alpha_c: share of each group in the 0-100 heuristic transcript risk (sums to 1). Engineering policy.
GROUP_ALPHA: dict[str, tuple[float, str]] = {
    "opening_promise": (0.22, "the opening decides whether viewers stay at all"),
    "progress": (0.18, "padding and repetition are the most common mid-video problem"),
    "comprehension": (0.18, "if viewers cannot follow, later payoffs are lost"),
    "questions_payoff": (0.08, "lexical question/answer matching is weak evidence, so it carries less"),
    "interruptions": (0.09, "interruptions are short and often intentional (sponsors, CTAs)"),
    "delivery": (0.13, "delivery is measured, but its effect depends on what is on screen"),
    "visual_pacing": (0.12, "measured from cuts and motion, but a static shot can be intentional (demo, talking head)"),
}
assert abs(sum(a for a, _ in GROUP_ALPHA.values()) - 1) < 1e-9


def _groups(features: dict) -> dict:
    """Deduplicated group signal g_c in 0..1: strongest relative intensity among the group's features."""
    out = {}
    for group, keys in GROUPS.items():
        beta = GROUP_BETA[group][0]
        out[group] = round(max((WEIGHTS[k][0] / beta * max(0, min(1, features.get(k, 0))) for k in keys), default=0.0), 6) if beta else 0.0
    return out


def _parts(features: dict) -> dict:
    """beta_c * g_c per group, keyed by the feature that dominates the group (for attribution)."""
    parts = {}
    for keys in GROUPS.values():
        if not keys:
            continue
        candidates = [(k, WEIGHTS[k][0] * max(0, min(1, features.get(k, 0)))) for k in keys]
        k, value = max(candidates, key=lambda x: x[1])
        if value:
            parts[k] = value
    # Weak phrase-based protective candidates cannot cancel measured editorial risks.
    if not parts:
        # at most one protective signal counts (the strongest), capped at -0.1
        prot = {k: max(-0.1, WEIGHTS[k][0] * max(0, min(1, features.get(k, 0)))) for k in PROTECTIVE if features.get(k, 0)}
        if prot:
            k = min(prot, key=prot.get)
            parts = {k: prot[k]}
    mv = features.get("micro_slowdown", 0.0) - features.get("micro_pickup", 0.0)
    if mv:  # signed, measured texture (features.micro_variation); outside the cause groups by design
        parts["micro_variation"] = WEIGHTS["micro_variation"][0] * max(-1.0, min(1.0, mv))
    return parts


@dataclass
class Anchors:
    retention_at_30s: float = 0.80
    retention_at_end: float = 0.45


@dataclass
class Baseline:
    shape_k: float = 0.6               # Weibull shape; < 1 = hazard falls over time; 1 = constant (v2)
    end_drop_multiplier: float = 1.5   # hazard multiplier in the final stretch (viewers leave as the end nears)
    end_drop_fraction: float = 0.05    # share of the duration treated as the final stretch (0 disables)

    RANGES = {"shape_k": (0.3, 1.0), "end_drop_multiplier": (1.0, 3.0), "end_drop_fraction": (0.0, 0.2)}

    def validate(self) -> None:
        for name, (lo, hi) in self.RANGES.items():
            v = getattr(self, name)
            if not (isinstance(v, (int, float)) and lo <= v <= hi):
                raise ValueError(f"{name} must be between {lo} and {hi}")


def baseline_cumulative(T_s: float, a: Anchors, b: Baseline):
    """Return H0(t), the cumulative neutral hazard, solved so S(30) = a and S(T) = z exactly."""
    k, m = b.shape_k, b.end_drop_multiplier
    t0, H_t0 = (30.0, -math.log(a.retention_at_30s)) if T_s > 30 else (0.0, 0.0)
    H_T = -math.log(max(1e-9, a.retention_at_end))
    Te = max(t0, T_s * (1 - b.end_drop_fraction))

    def W(t: float) -> float:
        t = min(max(t, t0), T_s)
        return (min(t, Te) ** k - t0 ** k) + (m * (t ** k - Te ** k) if t > Te else 0.0)

    lam = (H_T - H_t0) / W(T_s) if W(T_s) > 0 else 0.0

    def H(t: float) -> float:
        if t <= t0:
            return H_t0 * (t / 30.0) ** k if t0 else 0.0
        return H_t0 + lam * W(t)

    return H, lam


def describe_baseline(a: Anchors, b: Baseline, T_s: float) -> dict:
    _, lam = baseline_cumulative(T_s, a, b)
    return {
        "kind": "weibull_two_segment" if b.shape_k != 1 else "piecewise_constant",
        "shape_k": b.shape_k, "end_drop_multiplier": b.end_drop_multiplier, "end_drop_fraction": b.end_drop_fraction,
        "anchors": {"retention_at_30s": a.retention_at_30s, "retention_at_end": a.retention_at_end},
        "scale_after_30s": round(lam, 8),
        "formula": ("H0(t) = -ln(a)*(t/30)^k for t<=30; H0(t) = H0(30) + lambda*W(t) after, W(t) = integral from 30 "
                    "to t of m(s) d(s^k), m = end_drop_multiplier in the last end_drop_fraction of the video, else 1; "
                    "lambda solved so S(T) = z. S(t) = exp(-H0(t)) for a neutral video."),
        "description": ("Assumed neutral video, not measured audience data. The hazard falls over time (shape k < 1) "
                        "because viewers who stay past the opening are less likely to leave; the final stretch has a "
                        "modest extra drop. Anchors are hit exactly by a feature-free video."),
    }


def _bins(T_s: float, n: int) -> list[tuple[float, float]]:
    return [(t, min(1.0, T_s - t)) for t in range(n)]


def _curve(features: list[dict[str, float]], a: Anchors, scale: float, T_s: float, b: Baseline):
    H, _ = baseline_cumulative(T_s, a, b)
    h0, hz, surv = [], [], [1.0]
    for t, dt in _bins(T_s, len(features)):
        base = (H(t + dt) - H(t)) / dt if dt > 0 else 0.0
        lp = sum(_parts(features[t]).values()) * scale
        h = base * math.exp(lp)
        h0.append(base)
        hz.append(h)
        surv.append(surv[-1] * math.exp(-h * dt))
    return h0, hz, surv


def _cumulative(surv: list[float], hz: list[float], T_s: float) -> list[float]:
    """Exact running integral of S(t) at each bin end: AVD_b = S_b * (1 - exp(-h dt)) / h."""
    out, tot = [], 0.0
    for t, h in enumerate(hz):
        dt = min(1.0, T_s - t)
        tot += surv[t] * -math.expm1(-h * dt) / h if h > 1e-12 else surv[t] * dt
        out.append(tot)
    return out


def _avd(surv: list[float], hz: list[float], duration_s: float | None = None) -> float:
    """Exact integral of S(t) over piecewise-constant hazards (seconds)."""
    c = _cumulative(surv, hz, duration_s or len(hz))
    return c[-1] if c else 0.0


def predict(features: list[dict[str, float]], anchors: Anchors | None = None, duration_ms: int | None = None,
            baseline: Baseline | None = None) -> dict:
    """features: one dict per second (feature -> 0..1). Returns curve, band, attribution and summary."""
    a = anchors or Anchors()
    b = baseline or Baseline()
    if not (0 < a.retention_at_end <= a.retention_at_30s <= 1):
        raise ValueError("require 0 < retention_at_end <= retention_at_30s <= 1")
    b.validate()
    T_s = duration_ms / 1000 if duration_ms is not None else len(features)
    if duration_ms is not None and (duration_ms <= 0 or math.ceil(T_s) != len(features)):
        raise ValueError("duration must match the number of one-second bins")
    if T_s < 10:
        raise ValueError("too short to model (< 10 s)")
    h0, hz, s = _curve(features, a, 1.0, T_s, b)
    _, hz_lo, s_lo = _curve(features, a, 0.5, T_s, b)
    _, hz_hi, s_hi = _curve(features, a, 1.5, T_s, b)
    _, hz_n, s_n = _curve([{} for _ in features], a, 1.0, T_s, b)  # neutral video, same anchors
    cum, cum_n = _cumulative(s, hz, T_s), _cumulative(s_n, hz_n, T_s)

    per_second = []
    for t in range(len(features)):
        dt = min(1.0, T_s - t)
        lp_parts = _parts(features[t])
        loss = s[t] - s[t + 1]  # absolute share of starting viewers lost in this second
        excess = max(0.0, hz[t] - h0[t])
        pos = {k: c for k, c in lp_parts.items() if c > 0}
        ptot = sum(pos.values())
        # attribute the excess loss over the neutral baseline to positive features by share of log-hazard
        excess_loss = s[t] * (math.exp(-h0[t] * dt) - math.exp(-hz[t] * dt)) if excess > 0 else 0.0
        g = _groups(features[t])
        per_second.append({"t": t, "end_s": t + dt, "duration_s": dt,
                           "hazard_per_s": round(hz[t], 8), "baseline_hazard_per_s": round(h0[t], 8),
                           "conditional_loss": round(-math.expm1(-hz[t] * dt), 6),
                           "risk_groups": g,
                           "transcript_risk": round(100 * sum(GROUP_ALPHA[c][0] * v for c, v in g.items()), 3),
                           "retention": round(s[t + 1], 6), "lower": round(min(s_lo[t + 1], s_hi[t + 1]), 6),
                           "upper": round(max(s_lo[t + 1], s_hi[t + 1]), 6), "neutral": round(s_n[t + 1], 6),
                           "loss": round(loss, 6), "excess_loss": round(excess_loss, 6),
                           "contributions": {k: round(excess_loss * c / ptot, 6) for k, c in pos.items()} if ptot else {},
                           "protective": [k for k, c in lp_parts.items() if c < 0],
                           "cumulative_watch_s": round(cum[t], 4), "neutral_cumulative_watch_s": round(cum_n[t], 4)})
    avd, avd_lo, avd_hi, avd_n = cum[-1], _avd(s_lo, hz_lo, T_s), _avd(s_hi, hz_hi, T_s), cum_n[-1]
    totals: dict[str, float] = {}
    for p in per_second:
        for k, v in p["contributions"].items():
            totals[k] = totals.get(k, 0.0) + v
    base_desc = describe_baseline(a, b, T_s)
    return {
        "model_version": MODEL_VERSION, "label": LABEL, "calibrated": False, "band_label": BAND_LABEL,
        "anchors": {"retention_at_30s": a.retention_at_30s, "retention_at_end": a.retention_at_end},
        "baseline": base_desc,
        "per_second": per_second,
        "summary": {
            "duration_s": T_s,
            "avd_s": {"central": round(avd, 2), "lower": round(min(avd_lo, avd_hi), 2), "upper": round(max(avd_lo, avd_hi), 2)},
            "apv_pct": {"central": round(100 * avd / T_s, 2), "lower": round(100 * min(avd_lo, avd_hi) / T_s, 2),
                        "upper": round(100 * max(avd_lo, avd_hi) / T_s, 2)},
            "end_pct": {"central": round(100 * s[-1], 2), "lower": round(100 * min(s_lo[-1], s_hi[-1]), 2),
                        "upper": round(100 * max(s_lo[-1], s_hi[-1]), 2)},
            "neutral_avd_s": round(avd_n, 2), "neutral_end_pct": round(100 * s_n[-1], 2),
            "watch_time": {"avd_s": round(avd, 2), "neutral_avd_s": round(avd_n, 2), "duration_s": T_s,
                           "apv_pct": round(100 * avd / T_s, 2), "delta_vs_neutral_s": round(avd - avd_n, 2)},
            "assumptions": {"anchors": {"retention_at_30s": a.retention_at_30s, "retention_at_end": a.retention_at_end},
                            "baseline": {k: base_desc[k] for k in ("kind", "shape_k", "end_drop_multiplier", "end_drop_fraction")},
                            "band": BAND_LABEL, "calibrated": False},
            "excess_loss_by_feature": {k: round(v, 5) for k, v in sorted(totals.items(), key=lambda kv: -kv[1])},
        },
        "weights": {k: {"weight": w, "reason": r, "rationale": why, "group": FEATURE_GROUP.get(k, "protective")}
                    for k, (w, r, why) in WEIGHTS.items()},
        "notes": ["Weights are documented priors, not fitted to audience data.",
                  "Band = every weight scaled 0.5x..1.5x (assumption sensitivity), not a confidence interval.",
                  "Anchors and baseline shape describe an assumed neutral video in this category; change them to explore.",
                  "The neutral baseline hazard falls over time (Weibull shape k) with a modest extra drop near the end; "
                  "this is an assumption, not measured audience behaviour.",
                  "Related symptoms use the strongest contribution per cause group; risk is an engineering score, not abandonment probability.",
                  "Excess loss compares scenario and baseline hazards at the same audience remaining; hazard is a rate per second.",
                  "Protective phrase signals are capped and cannot offset a detected risk group."],
    }


def _mmss(s: float) -> str:
    s = int(s)
    return f"{s // 60}:{s % 60:02d}"


def headline_for(start_s: float, end_s: float, feature: str | None) -> str:
    """Plain sentence for a drop moment from its top reason (a finding can replace it with something more specific)."""
    if feature not in WEIGHTS:
        return f"{_mmss(start_s)}–{_mmss(end_s)}: scenario loss above the neutral video."
    return f"{_mmss(start_s)}–{_mmss(end_s)}: {HEADLINES.get(feature, WEIGHTS[feature][1])}; {WEIGHTS[feature][2]}."


def drop_moments(pred: dict, k: int = 8, min_gap_s: int = 15) -> list[dict]:
    """Top windows by excess loss (10 s windows), non-overlapping, with dominant reasons and a plain headline."""
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
        top = reasons[0][0] if reasons else None
        end_s = seg[-1].get("end_s", min(len(ps), t0 + win))
        headline = headline_for(t0, end_s, top)
        out.append({"start_s": t0, "end_s": end_s, "excess_loss": round(ex, 6),
                    "retention_before": seg[0]["retention"] + seg[0]["loss"], "retention_after": seg[-1]["retention"],
                    "reasons": [{"feature": f, "share": round(v / ex, 3), "text": WEIGHTS[f][1]} for f, v in reasons],
                    "headline": headline, "finding_ids": []})
        if len(out) >= k:
            break
    return sorted(out, key=lambda o: o["start_s"])
