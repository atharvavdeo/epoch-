"""predict stage (media env, in-process, no network): text retention model v3.

Reads the aligned transcript, the narrative structure (optional), audio + VAD (optional), shots (optional),
OCR text tracks (optional) and computes 10 s pitch windows from the stage's own audio WAV (optional; the voice
stage runs later, so predict does not depend on it). Each drop moment gets the transcript quote, the overlapping
findings and a plain headline so the UI can say *why* and link evidence.
"""

from __future__ import annotations

from contracts.common import det_uuid, utc_now
from pipeline.orchestration.io import read_json, write_json
from pipeline.orchestration.stage import StageContext, StageResult, StageSpec
from pipeline.predict.evidence import analyse_transcript
from pipeline.predict.features import build_features
from pipeline.predict.model import MODEL_VERSION, WEIGHTS, Anchors, Baseline, drop_moments, predict
from pipeline.predict.risk import apply_risk_to_seconds, attach_findings
from pipeline.predict.view import pack


def predict_spec(source: dict) -> StageSpec:
    tx = "script" if source.get("kind") == "script" else "align"
    deps = (tx,) if tx == "script" else (tx, "probe")
    b = Baseline()
    return StageSpec(name="predict", version="7", deps=deps,
                     optional_deps=("narrative", "audio", "asr", "video_scan", "ocr"),
                     config={"model": MODEL_VERSION, "weights": {k: v[0] for k, v in WEIGHTS.items()},
                             "anchors": {"retention_at_30s": 0.80, "retention_at_end": 0.45},
                             "baseline": {"shape_k": b.shape_k, "end_drop_multiplier": b.end_drop_multiplier,
                                          "end_drop_fraction": b.end_drop_fraction},
                             "band": "weights x0.5..x1.5", "risk_bins_ms": 5000},
                     extra={"title": source["project"]["title"]})


def duration_ms(ctx: StageContext, source: dict) -> int:
    if "probe" in ctx.deps:
        return read_json(ctx.dep("probe").path("probe.json"))["duration_ms"]
    return int(source["duration_ms"])


def _optional_inputs(ctx: StageContext, tr: dict, T: int, vad) -> dict:
    """Shots, OCR tracks and pitch windows when their stages exist; any failure leaves the feature off."""
    out: dict = {}
    if "video_scan" in ctx.deps:
        p = ctx.deps["video_scan"].path("shots.json")
        out["shots"] = read_json(p) if p.exists() else None
    if "ocr" in ctx.deps:
        p = ctx.deps["ocr"].path("ocr_tracks.json")
        out["ocr_tracks"] = read_json(p) if p.exists() else None
    if "audio" in ctx.deps:
        wav = ctx.deps["audio"].path("audio16k.wav")
        if wav.exists():
            try:
                from pipeline.media.voice import analyse_voice
                v = analyse_voice(wav, tr.get("words", []), T, vad)
                out["voice_windows"] = v.get("windows") if v.get("status") == "complete" else None
            except Exception as exc:  # pitch is optional evidence; never fail the prediction for it
                ctx.log(f"pitch windows unavailable: {exc}")
    return out


def predict_stage(source: dict):
    def fn(ctx: StageContext) -> StageResult:
        tx = "script" if source.get("kind") == "script" else "align"
        tr = read_json(ctx.dep(tx).path("transcript.json"))
        T = duration_ms(ctx, source)
        nar = read_json(ctx.deps["narrative"].path("narrative.json")) if "narrative" in ctx.deps else None
        audio = read_json(ctx.deps["audio"].path("audio.json")) if "audio" in ctx.deps else None
        vad = read_json(ctx.deps["asr"].path("vad.json"))["speech"] if "asr" in ctx.deps else None
        structure = nar["structure"] if nar else None
        extra = _optional_inputs(ctx, tr, T, vad)
        F, info = build_features(T, tr["segments"], tr.get("words", []), structure, audio, vad, **extra)
        pred = predict(F, Anchors(), duration_ms=T, baseline=Baseline())
        evidence = analyse_transcript(F, tr["segments"], T, info, structure)
        pred["notes"].append("Exploratory scenario uses provisional rule candidates, not accepted editorial defects or observed audience departures.")
        pred["summary"]["timing_source"] = info["timing_quality"]
        apply_risk_to_seconds(pred["per_second"], evidence["risk_bins"])
        moments = drop_moments(pred)
        segs = tr["segments"]
        attach_findings(moments, evidence["findings"], segs)
        issues = (nar or {}).get("issues", [])
        for m in moments:
            a, b = m["start_s"] * 1000, m["end_s"] * 1000
            m["issue_ids"] = [i["issue_id"] for i in issues
                              if i["affected_interval"]["start_ms"] < b and i["affected_interval"]["end_ms"] > a]
        rec = {"prediction_id": det_uuid("prediction", source["sha256"], ctx.fingerprint),
               "model_version": pred["model_version"], "label": pred["label"], "calibrated": False,
               "anchors": pred["anchors"], "features": [{k: round(v, 4) for k, v in f.items() if v} for f in F],
               "per_second": pred["per_second"], "summary": pred["summary"], "drop_moments": moments,
               "weights": pred["weights"], "notes": pred["notes"], "analysis": evidence, "feature_info": info,
               "risk_bins": evidence["risk_bins"], "findings": evidence["findings"], "baseline": pred["baseline"],
               "risk_weights": evidence["risk_weights"], "band_label": pred["band_label"], "created_at": utc_now()}
        write_json(ctx.out / "prediction.json", pack(rec))
        s = pred["summary"]
        ctx.log(f"text model: predicted avg watch {s['avd_s']['central']:.0f}s ({s['apv_pct']['central']:.1f}%), "
                f"end {s['end_pct']['central']:.1f}%; {len(moments)} drop moments; {len(evidence['findings'])} findings; "
                f"sources: {', '.join(info['sources'])}")
        return StageResult("complete", {"apv_pct": s["apv_pct"]["central"], "drop_moments": len(moments),
                                        "findings": len(evidence["findings"])})

    return fn
