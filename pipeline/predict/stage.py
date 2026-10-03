"""predict stage (media env, in-process, no network): text retention model v1.

Reads the aligned transcript, the narrative structure (optional), and audio + VAD (optional). Each drop
moment gets the transcript quote and any overlapping finding so the UI can say *why* and link evidence.
"""

from __future__ import annotations

from contracts.common import det_uuid, utc_now
from pipeline.orchestration.io import read_json, write_json
from pipeline.orchestration.stage import StageContext, StageResult, StageSpec
from pipeline.predict.features import build_features
from pipeline.predict.model import MODEL_VERSION, WEIGHTS, Anchors, drop_moments, predict


def predict_spec(source: dict) -> StageSpec:
    tx = "script" if source.get("kind") == "script" else "align"
    deps = (tx,) if tx == "script" else (tx, "probe")
    return StageSpec(name="predict", version="2", deps=deps, optional_deps=("narrative", "audio", "asr"),
                     config={"model": MODEL_VERSION, "weights": {k: v[0] for k, v in WEIGHTS.items()},
                             "anchors": {"retention_at_30s": 0.80, "retention_at_end": 0.45}, "band": "weights x0.5..x1.5"},
                     extra={"title": source["project"]["title"]})


def duration_ms(ctx: StageContext, source: dict) -> int:
    if "probe" in ctx.deps:
        return read_json(ctx.dep("probe").path("probe.json"))["duration_ms"]
    return int(source["duration_ms"])


def predict_stage(source: dict):
    def fn(ctx: StageContext) -> StageResult:
        tx = "script" if source.get("kind") == "script" else "align"
        tr = read_json(ctx.dep(tx).path("transcript.json"))
        T = duration_ms(ctx, source)
        nar = read_json(ctx.deps["narrative"].path("narrative.json")) if "narrative" in ctx.deps else None
        audio = read_json(ctx.deps["audio"].path("audio.json")) if "audio" in ctx.deps else None
        vad = read_json(ctx.deps["asr"].path("vad.json"))["speech"] if "asr" in ctx.deps else None
        F, info = build_features(T, tr["segments"], tr.get("words", []), nar["structure"] if nar else None, audio, vad)
        pred = predict(F, Anchors())
        moments = drop_moments(pred)
        segs = tr["segments"]
        issues = (nar or {}).get("issues", [])
        for m in moments:
            a, b = m["start_s"] * 1000, m["end_s"] * 1000
            q = " ".join(s["text"] for s in segs if s["interval"]["end_ms"] > a and s["interval"]["start_ms"] < b)
            m["quote"] = q[:400] or None
            m["issue_ids"] = [i["issue_id"] for i in issues
                              if i["affected_interval"]["start_ms"] < b and i["affected_interval"]["end_ms"] > a]
        rec = {"prediction_id": det_uuid("prediction", source["sha256"], ctx.fingerprint),
               "model_version": pred["model_version"], "label": pred["label"], "calibrated": False,
               "anchors": pred["anchors"], "features": [{k: round(v, 4) for k, v in f.items() if v} for f in F],
               "per_second": pred["per_second"], "summary": pred["summary"], "drop_moments": moments,
               "weights": pred["weights"], "notes": pred["notes"], "feature_info": info, "created_at": utc_now()}
        write_json(ctx.out / "prediction.json", rec)
        s = pred["summary"]
        ctx.log(f"text model: predicted avg watch {s['avd_s']['central']:.0f}s ({s['apv_pct']['central']:.1f}%), "
                f"end {s['end_pct']['central']:.1f}%; {len(moments)} drop moments; sources: {', '.join(info['sources'])}")
        return StageResult("complete", {"apv_pct": s["apv_pct"]["central"], "drop_moments": len(moments)})

    return fn
