"""Integration: the predict stage on the generated fixture video, with real probe/audio/video_scan outputs and
injected transcript, VAD, narrative structure and OCR tracks. Checks the written prediction.json is valid against
the package contract and unpacks to the v3 API contract. Requires fixtures/generated/long.mp4 and the media venv."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures" / "generated" / "long.mp4"
pytestmark = pytest.mark.skipif(not FIX.exists(), reason="run scripts/make_fixtures.py first")


def test_predict_stage_with_all_optional_inputs(tmp_path, monkeypatch):
    monkeypatch.setenv("EPOCH_DATA_DIR", str(tmp_path / "data"))
    from contracts.common import det_uuid
    from contracts.entities import RetentionPrediction
    from pipeline.media import stages as media
    from pipeline.orchestration.io import read_json, write_json
    from pipeline.orchestration.stage import StageResult, StageSpec, run_stage
    from pipeline.orchestration.workspace import register_video
    from pipeline.predict.stage import predict_spec, predict_stage
    from pipeline.predict.view import unpack

    ws, src = register_video(FIX, title="Retention test fixture", category="education", language="en")
    for spec, fn in [(media.probe_spec(src, True), media.probe_stage(src, True)), (media.audio_spec(), media.audio_stage(src)),
                     (media.video_scan_spec(), media.video_scan_stage(src))]:
        assert run_stage(ws, spec, fn).status == "complete", spec.name
    probe = read_json(ws.current("probe").path("probe.json"))
    T = probe["duration_ms"]
    segs = [{"segment_id": det_uuid("seg", i), "interval": {"start_ms": i * 5000, "end_ms": min(T, i * 5000 + 4500)},
             "text": f"Sentence {i} explains the retention test in plain words."} for i in range(T // 5000)]

    def inject(name, files):
        def fn(ctx):
            for rel, obj in files.items():
                write_json(ctx.out / rel, obj)
            return StageResult("complete")
        return run_stage(ws, StageSpec(name=name, version="test", deps=("probe",)), fn)

    inject("asr", {"vad.json": {"speech": [s["interval"] for s in segs]}})
    inject("align", {"transcript.json": {"segments": segs, "words": []}})
    inject("narrative", {"narrative.json": {"structure": {"hook_ms": None, "hook_end_ms": None, "first_substance_ms": 20_000,
                                                          "promises": [], "spans": []}, "issues": []}})
    inject("ocr", {"ocr_tracks.json": [{"start_ms": 3000, "end_ms": 6000, "text": "Fixture caption", "detector_confidence": 0.9}]})

    rec = run_stage(ws, predict_spec(src), predict_stage(src))
    assert rec.status == "complete", rec.data.get("error")
    stored = read_json(rec.path("prediction.json"))
    RetentionPrediction.model_validate({**stored, "run_id": "00000000-0000-4000-8000-000000000002"})
    sources = " | ".join(stored["feature_info"]["sources"])
    assert "shots (visual pacing)" in sources and "OCR text tracks" in sources and "audio waveform + VAD" in sources
    assert stored["model_version"] == "text-retention-v3"
    out = unpack(stored)
    assert out["baseline"]["kind"] == "weibull_two_segment" and out["findings"] and out["risk_bins"]
    assert out["per_second"][-1]["cumulative_watch_s"] == pytest.approx(out["summary"]["avd_s"]["central"], abs=0.01)
    assert out["summary"]["timing_source"] == "segment_timestamps"
    assert any(f["rule_id"] == "no_hook_identified" for f in out["findings"])
    assert "pitch windows (delivery variation)" in sources and "short-term loudness (audio energy)" in sources
