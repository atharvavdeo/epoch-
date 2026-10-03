"""Script package integration with real parser/predict/export and a mocked narrative service."""
from pathlib import Path

from test_pipeline_e2e import mock_llm_transport


def test_script_export_preserves_text_and_marks_unmeasured_modalities(tmp_path, monkeypatch):
    monkeypatch.setenv("EPOCH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CEREBRAS_API_KEY", "test-key")
    from contracts.common import new_uuid, utc_now
    from contracts.package import validate_package
    from pipeline.orchestration.io import read_json, write_json
    from pipeline.orchestration.stage import StageResult, StageSpec, run_stage
    from pipeline.script.stage import register_script, script_spec, script_stage
    from pipeline.reasoning.chunks import make_chunks
    from pipeline.reasoning.narrative import narrative_spec, narrative_stage
    from pipeline.reasoning.llm import CerebrasClient
    from pipeline.predict.stage import predict_spec, predict_stage
    from pipeline.scoring.stage import score_spec, score_stage
    from pipeline.package_export import export_spec, export_stage
    now = utc_now()
    project = dict(project_id=new_uuid(), title="Retention test script", category="education", declared_language="en",
                   created_at=now, updated_at=now, description=None)
    path = tmp_path / "script.txt"
    text = " ".join(f"Sentence number {i} explains the retention test in plain words." for i in range(24))
    path.write_text(text)
    ws, source = register_script(path, project)
    assert run_stage(ws, script_spec(source), script_stage(source)).status == "complete"
    tr = read_json(ws.current("script").path("transcript.json"))
    assert not tr["words"] and all(s["precision"] == "estimated" and s["source"] == "user" for s in tr["segments"])
    def embed(ctx):
        write_json(ctx.out / "chunks.json", {"chunks": make_chunks(tr["segments"]), "pairs": []})
        return StageResult("complete")
    run_stage(ws, StageSpec(name="embed", version="test", deps=("script",)), embed)
    specs = [(narrative_spec(source), narrative_stage(source, llm_factory=lambda: CerebrasClient.from_env(transport=mock_llm_transport()))),
             (predict_spec(source), predict_stage(source)), (score_spec(source), score_stage(source)),
             (export_spec(source), export_stage(source, ws))]
    for spec, fn in specs:
        rec = run_stage(ws, spec, fn)
        assert rec.status == "complete", rec.data.get("error")
    exp = ws.current("export")
    package = validate_package(exp.path(exp.data["summary"]["zip"]))
    assert package.asset.kind == "script" and package.asset.time_origin == "estimated_script"
    assert " ".join(s.text for s in package.records["transcript"]) == text
    assert not package.records["words"] and not package.records["shots"]
    assert not any(f.kind == "proxy" for f in package.manifest.files)
    assert all(c.status == ("observed" if c.modality == "text" else "unknown") for c in package.records["coverage"])
    pred = package.records["predictions"][0]
    assert pred.summary["timing_source"] == "estimated_150wpm" and not pred.calibrated
    assert not any(k in f for f in pred.features for k in ("slow_pace", "fast_pace", "dead_air", "micro_slowdown"))
    assert not any(s.feature_id in ("F40", "F52") for s in package.records["signals"])
    assert all(s.modality == "text" for s in package.records["signals"])
    assert package.run.provenance.detector_config["text_inspection"] == "user-script"


def test_script_subtitle_cues_and_project_scoping(tmp_path, monkeypatch):
    monkeypatch.setenv("EPOCH_DATA_DIR", str(tmp_path / "data"))
    from contracts.common import new_uuid, utc_now
    from pipeline.script.stage import register_script, script_spec, script_stage
    from pipeline.orchestration.stage import run_stage
    from pipeline.orchestration.io import read_json
    path = tmp_path / "script.srt"
    path.write_text("1\n00:00:01,000 --> 00:00:20,000\n" + " ".join(["word"] * 25))
    now = utc_now()
    p = dict(project_id=new_uuid(), title="Script test", category="other", declared_language="en", created_at=now, updated_at=now, description=None)
    ws, source = register_script(path, p)
    run_stage(ws, script_spec(source), script_stage(source))
    s = read_json(ws.current("script").path("transcript.json"))["segments"][0]
    assert s["interval"] == {"start_ms": 1000, "end_ms": 20000} and s["precision"] == "segment"
    ws2, source2 = register_script(path, {**p, "project_id": new_uuid()})
    assert ws2.root != ws.root and source2["asset_id"] != source["asset_id"]
