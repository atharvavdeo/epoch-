"""score stage: per-track coverage -> risk bins -> baseline scenario.

Coverage per track (RETENTION_MODEL §2):
  narrative  whole video when the narrative stage ran (minus unadjudicated candidate spans)
  visual     union of VLM-observed clip cores
  pacing     whole video when VAD + transcript + audio + shots exist
  text       OCR-inspected span; without OCR (D18) the VLM-observed windows, labelled
  technical  1.0 when decode/visual checks and waveform checks both ran; 0.5 if audio missing
Missing evidence is unknown (bounds widen), never zero risk (R06).
"""

from __future__ import annotations

from contracts.common import det_uuid, utc_now
from pipeline.orchestration.io import read_json, write_json
from pipeline.orchestration.stage import StageContext, StageResult, StageSpec
from pipeline.scoring import FORMULA_VERSION, RISK_VERSION
from pipeline.scoring.risk import ScoredIssue, compute_risk
from pipeline.scoring.scenario import DEFAULT_ASSUMPTIONS, Assumptions, ScenarioUnavailable, compute_scenario


def _minus(span: tuple[int, int], holes: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out = [span]
    for h0, h1 in holes:
        nxt = []
        for a, b in out:
            if h1 <= a or h0 >= b:
                nxt.append((a, b))
            else:
                if a < h0:
                    nxt.append((a, h0))
                if h1 < b:
                    nxt.append((h1, b))
        out = nxt
    return out


def track_coverage(T: int, deps: dict) -> tuple[dict, dict, list[dict]]:
    """Return (track -> observed spans, notes, Coverage-shaped modality records)."""
    notes, cov = {}, {}
    nar = read_json(deps["narrative"].path("narrative.json")) if "narrative" in deps else None
    if nar:
        holes = [(c["interval"]["start_ms"], c["interval"]["end_ms"]) for c in nar["candidates"]
                 if c["kid"] in {u["candidate"] for u in nar["unadjudicated"]}]
        cov["narrative"] = _minus((0, T), holes)
        notes["narrative"] = "transcript + narrative pass" + (f"; {len(holes)} candidate spans unadjudicated" if holes else "")
    else:
        cov["narrative"] = []
        notes["narrative"] = "narrative stage missing"
    vis = read_json(deps["visual"].path("visual.json")) if "visual" in deps else None
    vis_spans = [(c["interval"]["start_ms"], c["interval"]["end_ms"]) for c in (vis or {}).get("coverage", [])
                 if c["status"] == "observed"]
    cov["visual"] = vis_spans
    notes["visual"] = f"VLM {vis['profile']} sampled clips" if vis else "visual analysis not attached (awaiting Colab)"
    audio = read_json(deps["audio"].path("audio.json")) if "audio" in deps else {"status": "missing"}
    audio_ok = audio.get("status") in ("valid", "valid_silence")
    pacing_ok = audio_ok and "asr" in deps and "align" in deps and "video_scan" in deps
    cov["pacing"] = [(0, T)] if pacing_ok else []
    notes["pacing"] = "VAD + transcript + audio + shots" if pacing_ok else "needs audio, VAD and transcript"
    if "ocr" in deps:
        cov["text"] = [(0, T)]
        notes["text"] = "OCR 1 fps + cut frames"
    else:
        cov["text"] = vis_spans
        notes["text"] = "text inspection: vlm-sampled (no OCR, D18)" if vis_spans else "no OCR and no visual analysis"
    tech_full = "video_scan" in deps and audio_ok
    cov["technical"] = [(0, T)] if tech_full else ([(0, T // 2)] if "video_scan" in deps else [])
    notes["technical"] = ("decode/black/freeze + waveform checks" if tech_full
                          else "video checks only; audio checks missing (counted as half coverage)")
    return cov, notes, (vis or {}).get("coverage", [])


def score_spec() -> StageSpec:
    return StageSpec(name="score", version="1", deps=("probe",), optional_deps=("narrative", "visual", "audio", "asr", "align",
                                                                                 "video_scan", "ocr"),
                     config={"formula": FORMULA_VERSION, "risk": RISK_VERSION, "profile": "multimodal-v1",
                             "assumptions": DEFAULT_ASSUMPTIONS})


def score_stage(source: dict):
    def fn(ctx: StageContext) -> StageResult:
        T = read_json(ctx.dep("probe").path("probe.json"))["duration_ms"]
        cov, notes, _ = track_coverage(T, ctx.deps)
        issues = read_json(ctx.deps["narrative"].path("narrative.json"))["issues"] if "narrative" in ctx.deps else []
        scored = [ScoredIssue(i["issue_id"], i["risk_track"], i["severity"], i["evidence_status"],
                              i["affected_interval"]["start_ms"], i["affected_interval"]["end_ms"], i["cause_group_id"])
                  for i in issues]
        bins = compute_risk(T, scored, cov, profile="multimodal-v1")
        risk_rows = [{"interval": {"start_ms": b.start_ms, "end_ms": b.end_ms},
                      "track_values": {k: {"risk": v.risk, "coverage": round(v.coverage, 6), "lower": round(v.lower, 6),
                                           "upper": round(v.upper, 6)} for k, v in b.tracks.items()},
                      "combined_lower": round(b.lower, 6), "combined_upper": round(b.upper, 6),
                      "display_value": round(100 * b.point) if b.point is not None else None,
                      "evidence_coverage": round(b.coverage, 6), "contributing_issue_ids": b.contributing_issue_ids}
                     for b in bins]
        labels = [f"Coverage — {k}: {v}" for k, v in notes.items()]
        try:
            sc = compute_scenario(bins, T, Assumptions(), scoring_profile="multimodal-v1", extra_labels=labels)
            sc.update(scenario_id=det_uuid("scenario", ctx.fingerprint, "baseline"), edit_plan_id=None,
                      assumptions=dict(DEFAULT_ASSUMPTIONS), created_at=utc_now())
            scenarios = [sc]
        except ScenarioUnavailable as exc:
            scenarios = []
            labels.append(f"scenario unavailable: {exc}")
        write_json(ctx.out / "score.json", {"risk": risk_rows, "scenarios": scenarios, "coverage_spans": cov,
                                            "coverage_notes": notes})
        complete = all(b.point is not None for b in bins)
        ctx.log(f"{len(bins)} bins; central curve {'available' if complete else 'NOT available (partial coverage)'}; "
                + "; ".join(f"{k}: {notes[k]}" for k in notes))
        return StageResult("complete", {"bins": len(bins), "central_curve": complete})

    return fn
