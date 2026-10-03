"""prediction.json <-> API response.

The package schema (contracts/entities.py RetentionPrediction) forbids unknown top-level, per-second and
drop-moment keys, so `pack` stores the v3 additions inside the free-form `analysis` and `summary` blocks.
`unpack` returns the flat v3 contract (docs/PREDICTION_CONTRACT.md) for the API, and also upgrades v2 packages
as far as their stored data allows (cumulative watch time and risk bins are derived; baseline is reported as v2).
"""
from __future__ import annotations

import math

SECOND_EXTRAS = ("cumulative_watch_s", "neutral_cumulative_watch_s")
MOMENT_EXTRAS = ("headline", "headline_finding_id")
TOP_EXTRAS = ("risk_bins", "findings", "baseline", "risk_weights", "band_label")

V2_BASELINE = {"kind": "piecewise_constant_v2", "shape_k": 1.0, "end_drop_multiplier": 1.0, "end_drop_fraction": 0.0,
               "description": "Built by text-retention-v2: constant hazard before and after 30 s (straight-line shape). "
                              "Recompute to apply the v3 baseline shape."}


def pack(rec: dict) -> dict:
    rec = dict(rec)
    analysis = dict(rec.get("analysis") or {})
    ps = [dict(p) for p in rec["per_second"]]
    analysis["scenario_series"] = {k: [p.pop(k, None) for p in ps] for k in SECOND_EXTRAS}
    moments = [dict(m) for m in rec.get("drop_moments", [])]
    analysis["drop_moment_headlines"] = [{"start_s": m["start_s"], **{k: m.pop(k, None) for k in MOMENT_EXTRAS}} for m in moments]
    for k in TOP_EXTRAS:
        if k in rec:
            analysis[k] = rec.pop(k)
    rec.update(per_second=ps, drop_moments=moments, analysis=analysis)
    return rec


def _derive_cumulative(ps: list[dict], key: str) -> list[float]:
    """Exact integral of a piecewise-exponential curve from stored survival values (v2 packages)."""
    out, tot, prev = [], 0.0, 1.0
    for p in ps:
        cur, dt = p[key], p.get("duration_s") or 1.0
        if cur > 0 and prev > cur:
            tot += (prev - cur) * dt / math.log(prev / cur)
        else:
            tot += prev * dt
        out.append(round(tot, 4))
        prev = cur
    return out


def unpack(stored: dict, scenario: dict | None = None, moments: list[dict] | None = None) -> dict:
    """Flat v3 response. `scenario` (a fresh predict() result) and `moments` override the stored scenario."""
    from pipeline.predict.model import headline_for
    from pipeline.predict.risk import apply_risk_to_seconds, attach_findings, rank_findings, risk_weights, transcript_risk_bins

    r = {k: v for k, v in stored.items() if k != "features"}
    analysis = dict(r.get("analysis") or {})
    if scenario is not None:
        for k in ("model_version", "label", "calibrated", "anchors", "per_second", "summary", "weights", "notes",
                  "baseline", "band_label"):
            if k in scenario:
                r[k] = scenario[k]
        r["summary"] = {**r["summary"], "timing_source": stored.get("summary", {}).get("timing_source")}
    duration_ms = int(round(r["summary"]["duration_s"] * 1000))

    ps = [dict(p) for p in r["per_second"]]
    series = analysis.get("scenario_series") or {}
    for key, surv in (("cumulative_watch_s", "retention"), ("neutral_cumulative_watch_s", "neutral")):
        if ps and key in ps[0]:
            continue
        vals = series.get(key) if scenario is None else None
        if not vals or len(vals) != len(ps) or vals[0] is None:
            vals = _derive_cumulative(ps, surv)
        for p, v in zip(ps, vals):
            p[key] = v

    findings = analysis.get("findings") or []
    if findings and "priority_rank" not in findings[0]:
        findings = rank_findings(findings, duration_ms, analysis.get("structure_ledger"))
    for f in findings:
        f.setdefault("title", f.get("rule_id", "finding").replace("_", " ").capitalize())
        f.setdefault("needs_reanalysis", f.get("requires_reanalysis", True))
    bins = analysis.get("risk_bins") or []
    if not bins or "risk" not in bins[0]:
        bins = transcript_risk_bins(findings, duration_ms)
    apply_risk_to_seconds(ps, bins)

    if moments is None:
        moments = [dict(m) for m in r.get("drop_moments", [])]
        saved = {h["start_s"]: h for h in analysis.get("drop_moment_headlines") or []}
        for m in moments:
            h = saved.get(m["start_s"]) or {}
            if h.get("headline"):
                m["headline"] = h["headline"]
                if h.get("headline_finding_id"):
                    m["headline_finding_id"] = h["headline_finding_id"]
            else:
                m["headline"] = headline_for(m["start_s"], m["end_s"], m["reasons"][0]["feature"] if m.get("reasons") else None)
                attach_findings([m], findings)
    s = dict(r["summary"])
    if "watch_time" not in s:
        avd = s["avd_s"]["central"]
        s["watch_time"] = {"avd_s": avd, "neutral_avd_s": s.get("neutral_avd_s"), "duration_s": s["duration_s"],
                           "apv_pct": s["apv_pct"]["central"],
                           "delta_vs_neutral_s": round(avd - s["neutral_avd_s"], 2) if s.get("neutral_avd_s") is not None else None}
    baseline = r.get("baseline") if scenario is not None else analysis.get("baseline")
    if not baseline:
        baseline = {**V2_BASELINE, "anchors": r.get("anchors")}
    r.update(per_second=ps, summary=s, drop_moments=moments, risk_bins=bins, findings=findings, baseline=baseline,
             risk_weights=analysis.get("risk_weights") or risk_weights(),
             band_label=r.get("band_label") or analysis.get("band_label") or
             "Assumption sensitivity: every weight x0.5 and x1.5 (not a confidence interval)")
    analysis.update(findings=findings, risk_bins=bins)
    r["analysis"] = analysis
    return r
