"""Integration: media stages -> visual job -> (fake) Colab runner -> attach ->
narrative (mocked Cerebras) -> score -> export -> package validation.

No heavy models: transcript/embedding stage outputs are injected and the
LLM is an httpx.MockTransport. Requires fixtures/generated/long.mp4
(python scripts/make_fixtures.py) and the media venv.
"""

import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures" / "generated" / "long.mp4"
pytestmark = pytest.mark.skipif(not FIX.exists(), reason="run scripts/make_fixtures.py first")


def mock_llm_transport() -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "gpt-oss-120b"}]})
        body = json.loads(req.content)
        name = body["response_format"]["json_schema"]["name"]
        user = body["messages"][1]["content"]
        if name == "probe":
            out = {"ok": True}
        elif name == "structure":
            ids = re.findall(r"^(P\d\d) \[", user, re.M)
            out = {"title_obligations": [{"obligation": "explain the retention test", "title_quote": "Retention test"}],
                   "hook": {"chunk": ids[0], "quote": "", "kind": "none"}, "first_substance_chunk": ids[-1],
                   "chapters": [{"start_chunk": ids[0], "end_chunk": ids[-1], "label": "all", "role": "main_content"}],
                   "promise_ledger": [{"obligation_index": 0, "setup_chunks": [ids[0]], "partial_chunks": [],
                                       "fulfilled_chunks": [ids[-1]], "status": "fulfilled", "note": ""}],
                   "spans": []}
        else:
            decisions = []
            for kid in re.findall(r"^(K\d\d): type=", user, re.M):
                opt = re.search(rf"{kid}: type=.*?option (O\d)", user, re.S).group(1)
                decisions.append({"candidate": kid, "verdict": "accept", "severity": "medium", "evidence": ["E01"],
                                  "quote": "", "explanation": "mechanism", "counter_explanation": "could be intended",
                                  "edit_option": opt, "proposed_text": "A tighter line.", "edit_rationale": "shorter"})
            out = {"decisions": decisions}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(out)}}],
                                         "usage": {"prompt_tokens": 10, "completion_tokens": 5}})

    return httpx.MockTransport(handler)


def test_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("EPOCH_DATA_DIR", str(tmp_path / "data"))
    from pipeline.orchestration import settings

    settings.load_dotenv.cache_clear()
    monkeypatch.setenv("CEREBRAS_API_KEY", "test-key")
    from contracts.common import det_uuid
    from contracts.package import validate_package
    from pipeline.media import stages as media
    from pipeline.orchestration.graph import attach_visual
    from pipeline.orchestration.io import write_json
    from pipeline.orchestration.stage import StageResult, StageSpec, run_stage
    from pipeline.orchestration.workspace import register_video
    from pipeline.package_export import export_spec, export_stage
    from pipeline.reasoning import narrative as nar
    from pipeline.reasoning.chunks import make_chunks
    from pipeline.reasoning.llm import CerebrasClient
    from pipeline.scoring.stage import score_spec, score_stage
    from pipeline.visual.job import visual_job_spec, visual_job_stage

    ws, src = register_video(FIX, title="Retention test fixture", category="education", language="en")
    for spec, fn in [(media.probe_spec(src, True), media.probe_stage(src, True)), (media.proxy_spec(), media.proxy_stage(src)),
                     (media.audio_spec(), media.audio_stage(src)), (media.video_scan_spec(), media.video_scan_stage(src)),
                     (media.frames_spec(), media.frames_stage(src))]:
        assert run_stage(ws, spec, fn).status == "complete", spec.name

    # injected transcript (asr/align) and embeddings: same file shapes as the real stages
    segs = [{"segment_id": det_uuid("seg", i), "interval": {"start_ms": i * 5000, "end_ms": i * 5000 + 4500},
             "text": f"Sentence number {i} explains the retention test in plain words.", "language": "en",
             "precision": "segment", "source": "asr", "word_ids": [], "speaker_id": None, "original_asr_text": None,
             "correction_revision": 0} for i in range(15)]

    def inject(name, files):
        def fn(ctx):
            for rel, obj in files.items():
                write_json(ctx.out / rel, obj)
            return StageResult("complete")
        return run_stage(ws, StageSpec(name=name, version="test", deps=("probe",)), fn)

    inject("asr", {"vad.json": {"speech": [{"start_ms": s["interval"]["start_ms"], "end_ms": s["interval"]["end_ms"]} for s in segs],
                                "speech_fraction": 0.9}})
    inject("align", {"transcript.json": {"segments": segs, "words": [], "stats": {"aligned_words": 0, "unaligned_words": 0}}})
    chunks = make_chunks(segs)
    inject("embed", {"chunks.json": {"chunks": chunks, "pairs": [{"earlier": chunks[0]["chunk_id"], "later": chunks[-1]["chunk_id"],
                                                                     "cosine": 0.9}] if len(chunks) > 2 else []}})

    # visual job -> shipped runtime with fake backend -> result zip
    vj = run_stage(ws, visual_job_spec(src), visual_job_stage(src))
    assert vj.status == "complete"
    zname = json.loads(vj.path("job_summary.json").read_text())["zip"]
    job_dir = tmp_path / "colab" / "job"
    zipfile.ZipFile(vj.path(zname)).extractall(job_dir)
    sys.path.insert(0, str(job_dir / "runtime"))
    for m in [m for m in sys.modules if m.startswith("epoch_vlm")]:
        del sys.modules[m]
    import epoch_vlm.runner as R

    assert R.main(["--job", str(job_dir), "--out", str(tmp_path / "colab" / "out"), "--profile", "Q35-9B-BF16", "--fake"]) == 0
    sys.path.remove(str(job_dir / "runtime"))
    res_zip = next((tmp_path / "colab").glob("*.visualresult.zip"))

    # a FAKE model must be refused by the importer ...
    assert attach_visual(ws, src, res_zip) is False
    # ... and the same output relabelled as the pinned profile imports (test-only relabel)
    from pipeline.model_registry import VLM_PROFILES

    relabelled = tmp_path / "relabelled.visualresult.zip"
    with zipfile.ZipFile(res_zip) as zin, zipfile.ZipFile(relabelled, "w") as zout:
        for n in zin.namelist():
            data = zin.read(n)
            if n == "result.json":
                r = json.loads(data)
                r["model"].update(repo=VLM_PROFILES["Q35-9B-BF16"]["repo"], revision=VLM_PROFILES["Q35-9B-BF16"]["revision"])
                data = json.dumps(r).encode()
            zout.writestr(n, data)
    assert attach_visual(ws, src, relabelled) is True

    llm = lambda: CerebrasClient(api_key="k", base_url="https://mock/v1", transport=mock_llm_transport())  # noqa: E731
    rec = run_stage(ws, nar.narrative_spec(src), nar.narrative_stage(src, llm_factory=llm))
    assert rec.status == "complete", rec.data.get("error")
    narj = json.loads(rec.path("narrative.json").read_text(encoding="utf-8"))
    assert narj["issues"], "mock accepts every candidate, so issues must exist"
    assert run_stage(ws, score_spec(), score_stage(src)).status == "complete"
    ex = run_stage(ws, export_spec(src), export_stage(src, ws))
    assert ex.status == "complete", ex.data.get("error")
    pkg = next(ex.dir.glob("*.retention.zip"))
    vp = validate_package(pkg)
    assert vp.records["issues"] and vp.records["risk"] and vp.records["scenarios"]
    assert vp.manifest.package_kind == "partial_analysis"  # OCR shelved => declared missing, never hidden
    assert "ocr" in vp.manifest.missing_stage_names
    for i in vp.records["issues"]:
        assert i.evidence_ids and i.suggested_edit_ids
    # idempotent: same inputs re-export to the same cached package
    ex2 = run_stage(ws, export_spec(src), export_stage(src, ws))
    assert next(ex2.dir.glob("*.retention.zip")).read_bytes() == pkg.read_bytes()
    shutil.rmtree(tmp_path / "colab", ignore_errors=True)
