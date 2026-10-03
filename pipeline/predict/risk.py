"""Transcript attention risk (5-second bins) and editorial ranking of findings.

Risk per bin b:
    a_{j,b} = s_j * e_j * o_{j,b}        severity weight x evidence weight x fraction of the bin the finding covers
    g_{c,b} = max_j in group c  a_{j,b}  (related findings never add up)
    R_b     = sum_c alpha_c * g_{c,b}    (sum alpha = 1);   displayed as 100 * R_b, "heuristic transcript risk"
It is an ordinal engineering score traceable to quoted findings, never a probability of leaving.

Priority (editorial value, not absolute curve drop) is a weighted sum of evidence strength, severity, affected
duration, relevance to the title promise, whether a safe edit exists and the viewer-misunderstanding risk, with
duplicate suppression inside a cause group. All weights below are engineering policies, not fitted values.
"""
from __future__ import annotations

from pipeline.predict.model import GROUP_ALPHA, GROUP_BETA, GROUP_LABELS, GROUP_ORDER, WEIGHTS, GROUPS

BIN_MS = 5000
SEVERITY_WEIGHT = {"low": 1 / 3, "medium": 2 / 3, "high": 1.0}
EVIDENCE_WEIGHT = {"supported": 1.0, "provisional": 0.5}
PRIORITY_WEIGHTS = {
    "evidence": (0.30, "supported findings are measured directly; provisional ones need confirmation"),
    "severity": (0.25, "how strongly the rule's condition holds"),
    "safe_edit": (0.15, "a low-risk edit (trim, split, move a CTA) is more valuable to act on now"),
    "duration": (0.10, "longer affected stretches matter more (saturates at 30 s)"),
    "title_relevance": (0.10, "problems on the way to the title payoff affect the reason viewers came"),
    "misunderstanding": (0.10, "comprehension and question problems can make viewers lose the thread"),
}
DUPLICATE_FACTOR = 0.5  # a finding mostly overlapping a higher-priority finding of the same group is down-weighted


def _overlap(a0, a1, b0, b1) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def rank_findings(findings: list[dict], duration_ms: int, structure: dict | None = None) -> list[dict]:
    from pipeline.predict.evidence import first_payoff_ms
    pay = first_payoff_ms(structure or {})
    scored = []
    for f in findings:
        dur_s = max(0, f["end_ms"] - f["start_ms"]) / 1000
        comp = {
            "evidence": EVIDENCE_WEIGHT.get(f.get("evidence_strength"), 0.5),
            "severity": SEVERITY_WEIGHT.get(f.get("severity"), 1 / 3),
            "safe_edit": 1.0 if f.get("safe_edit") else 0.0,
            "duration": min(1.0, dur_s / 30),
            "title_relevance": 1.0 if f.get("cause_group") == "opening_promise" or (pay is not None and f["start_ms"] < pay) else 0.0,
            "misunderstanding": 1.0 if f.get("cause_group") in ("comprehension", "questions_payoff") else 0.0,
        }
        raw = sum(PRIORITY_WEIGHTS[k][0] * v for k, v in comp.items())
        scored.append((raw, f, comp))
    scored.sort(key=lambda x: (-x[0], x[1]["start_ms"]))
    kept: list[dict] = []
    out = []
    for raw, f, comp in scored:
        dup = None
        for k in kept:
            if k["cause_group"] != f.get("cause_group"):
                continue
            ov = _overlap(f["start_ms"], f["end_ms"], k["start_ms"], k["end_ms"])
            shorter = max(1, min(f["end_ms"] - f["start_ms"], k["end_ms"] - k["start_ms"]))
            if ov / shorter >= 0.5:
                dup = k["finding_id"]
                break
        score = raw * (DUPLICATE_FACTOR if dup else 1.0)
        g = {**f, "priority_score": round(100 * score, 2), "priority_components": {k: round(v, 3) for k, v in comp.items()},
             "duplicate_of": dup}
        g.setdefault("group_label", GROUP_LABELS.get(g.get("cause_group"), g.get("cause_group")))
        if not dup:
            kept.append(g)
        out.append(g)
    out.sort(key=lambda x: (-x["priority_score"], x["start_ms"]))
    for i, g in enumerate(out, 1):
        g["priority_rank"] = i
    return out


def transcript_risk_bins(findings: list[dict], duration_ms: int) -> list[dict]:
    """Five-second bins (final bin may be shorter). Keeps legacy keys (start_ms, end_ms, score, groups)."""
    bins = []
    for a in range(0, duration_ms, BIN_MS):
        b = min(duration_ms, a + BIN_MS)
        width = b - a
        groups = {g: 0.0 for g in GROUP_ORDER}
        best: dict[str, tuple[float, str]] = {}
        ids, top = [], (0.0, None)
        for f in findings:
            ov = _overlap(a, b, f["start_ms"], f["end_ms"])
            if not ov or f.get("cause_group") not in groups:
                continue
            c = f["cause_group"]
            contrib = SEVERITY_WEIGHT.get(f.get("severity"), 1 / 3) * EVIDENCE_WEIGHT.get(f.get("evidence_strength"), 0.5) * ov / width
            ids.append(f["finding_id"])
            if contrib > groups[c]:
                groups[c] = contrib
                best[c] = (contrib, f["finding_id"])
            weighted = GROUP_ALPHA[c][0] * contrib
            if weighted > top[0] or (weighted == top[0] and top[1] is None):
                top = (weighted, f["finding_id"])
        R = sum(GROUP_ALPHA[c][0] * v for c, v in groups.items())
        groups = {c: round(v, 4) for c, v in groups.items()}
        bins.append({"start_s": a / 1000, "end_s": b / 1000, "risk": round(100 * R, 3), "groups": groups,
                     "top_finding_id": top[1], "finding_ids": ids,
                     # legacy keys (v2 UI)
                     "start_ms": a, "end_ms": b, "duration_s": width / 1000, "score": round(100 * R, 3),
                     "label": "Heuristic transcript risk (not probability of leaving); max per cause group"})
    return bins


def risk_weights() -> dict:
    return {
        "severity": {k: {"weight": round(v, 4), "rationale": r} for (k, v), r in zip(SEVERITY_WEIGHT.items(), (
            "weak condition", "clear condition", "strong condition"))},
        "evidence": {"supported": {"weight": 1.0, "rationale": "the rule's condition is a direct measurement of this video"},
                     "provisional": {"weight": 0.5, "rationale": "rests on narrative extraction or lexical matching; needs review"}},
        "group_alpha": {c: {"weight": a, "rationale": r, "label": GROUP_LABELS[c]} for c, (a, r) in GROUP_ALPHA.items()},
        "group_beta": {c: {"weight": b, "rationale": r, "label": GROUP_LABELS[c], "features": list(GROUPS[c]),
                           "relative_intensity": {k: round(WEIGHTS[k][0] / b, 4) for k in GROUPS[c]} if b else {}}
                       for c, (b, r) in GROUP_BETA.items()},
        "priority": {k: {"weight": w, "rationale": r} for k, (w, r) in PRIORITY_WEIGHTS.items()},
        "duplicate_factor": {"weight": DUPLICATE_FACTOR, "rationale": "same cause group and >=50% overlap with a higher-priority finding"},
        "formula": "risk_b = 100 * sum_c alpha_c * max_{j in c} severity_j * evidence_j * overlap_{j,b}",
        "policy": "Engineering policies chosen by reasoning, not fitted to audience data.",
    }


def apply_risk_to_seconds(per_second: list[dict], bins: list[dict]) -> None:
    """Per-second transcript_risk / risk_groups = the 5-second bin the second falls in (one consistent number)."""
    for p in per_second:
        i = int(p["t"] * 1000 // BIN_MS)
        if 0 <= i < len(bins):
            p["transcript_risk"] = bins[i].get("risk", bins[i].get("score", 0.0))
            p["risk_groups"] = dict(bins[i].get("groups", {}))


def attach_findings(moments: list[dict], findings: list[dict], segments: list[dict] | None = None) -> None:
    """Link each drop moment to overlapping findings and rewrite its headline from the best matching finding."""
    from pipeline.predict.evidence import mmss
    from pipeline.predict.model import FEATURE_GROUP
    for m in moments:
        a, b = m["start_s"] * 1000, m["end_s"] * 1000
        over = [f for f in findings if f["start_ms"] < b and f["end_ms"] > a]
        m["finding_ids"] = [f["finding_id"] for f in sorted(over, key=lambda f: f.get("priority_rank", 10 ** 6))]
        if segments is not None:
            q = " ".join(s["text"] for s in segments if s["interval"]["end_ms"] > a and s["interval"]["start_ms"] < b)
            m["quote"] = q or None
        top = m["reasons"][0]["feature"] if m.get("reasons") else None
        match = [f for f in over if f.get("scenario_feature") == top] or \
                [f for f in over if top and f.get("cause_group") == FEATURE_GROUP.get(top)]
        if match:
            f = min(match, key=lambda f: f.get("priority_rank", 10 ** 6))
            m["headline"] = f"{mmss(a)}–{mmss(b)}: {f['title']}. {f['mechanism']}"
            m["headline_finding_id"] = f["finding_id"]
