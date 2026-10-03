"""Prediction API v3 contract (GET flat fields, POST baseline validation). Run in the api env:
  .venvs/api/Scripts/python.exe -m pytest tests/test_predict_api.py
Needs fixtures/generated/sample.retention.zip (written by tests/test_pipeline_e2e.py)."""

import io
import os
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "fixtures" / "generated" / "sample.retention.zip"
pytestmark = pytest.mark.skipif(not PKG.exists(), reason="run tests/test_pipeline_e2e.py first")


@pytest.fixture(scope="module")
def run_id(tmp_path_factory):
    os.environ["EPOCH_DATA_DIR"] = str(tmp_path_factory.mktemp("apidata_predict"))
    from fastapi.testclient import TestClient

    from apps.api.main import app

    client = TestClient(app)
    r = client.post("/api/v1/imports", files={"file": ("x.retention.zip", io.BytesIO(PKG.read_bytes()), "application/zip")})
    iid = r.json()["import_id"]
    for _ in range(200):
        st = client.get(f"/api/v1/imports/{iid}").json()
        if st["status"] in ("committed", "rejected"):
            break
        time.sleep(0.05)
    assert st["status"] == "committed", st
    rid = st["committed_run_id"]
    # The e2e fixture package is built without the predict stage: write a v3 prediction row for this run, built
    # from its own transcript by the same functions the stage uses (pack -> stored row, exactly like export).
    import json

    from apps.api.importer import read_jsonl
    from apps.api.main import _run_row
    from contracts.entities import RetentionPrediction
    from pipeline.predict.evidence import analyse_transcript
    from pipeline.predict.features import build_features
    from pipeline.predict.model import drop_moments, predict
    from pipeline.predict.risk import apply_risk_to_seconds, attach_findings
    from pipeline.predict.view import pack

    d = Path(_run_row(rid).dir)
    segs = read_jsonl(d, "transcript")
    T = max(s["interval"]["end_ms"] for s in segs) + 2000
    st_ = {"hook_ms": None, "hook_end_ms": None, "first_substance_ms": 40_000, "promises": [], "spans": []}
    F, info = build_features(T, segs, [], st_)
    pred = predict(F, duration_ms=T)
    ev = analyse_transcript(F, segs, T, info, st_)
    apply_risk_to_seconds(pred["per_second"], ev["risk_bins"])
    moments = drop_moments(pred)
    attach_findings(moments, ev["findings"], segs)
    rec = {"prediction_id": "00000000-0000-4000-8000-000000000001", "run_id": rid, "model_version": pred["model_version"],
           "label": pred["label"], "calibrated": False, "anchors": pred["anchors"],
           "features": [{k: round(v, 4) for k, v in f.items() if v} for f in F], "per_second": pred["per_second"],
           "summary": {**pred["summary"], "timing_source": info["timing_quality"]}, "drop_moments": moments,
           "weights": pred["weights"], "notes": pred["notes"], "analysis": ev, "feature_info": info,
           "risk_bins": ev["risk_bins"], "findings": ev["findings"], "baseline": pred["baseline"],
           "risk_weights": ev["risk_weights"], "band_label": pred["band_label"], "created_at": "2026-10-03T00:00:00Z"}
    row = RetentionPrediction.model_validate(pack(rec)).model_dump(mode="json")
    (d / "data" / "predictions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    return client, rid


def test_get_prediction_exposes_v3_contract(run_id):
    client, rid = run_id
    p = client.get(f"/api/v1/runs/{rid}/prediction").json()
    assert "features" not in p and p["calibrated"] is False
    for k in ("risk_bins", "findings", "baseline", "risk_weights", "per_second", "drop_moments", "summary", "analysis"):
        assert k in p, k
    assert {"cumulative_watch_s", "neutral_cumulative_watch_s", "retention", "neutral"} <= p["per_second"][0].keys()
    assert {"avd_s", "neutral_avd_s", "duration_s", "apv_pct", "delta_vs_neutral_s"} <= p["summary"]["watch_time"].keys()
    assert {"kind", "shape_k", "end_drop_multiplier", "end_drop_fraction", "anchors", "description"} <= p["baseline"].keys()
    assert {"severity", "evidence", "group_alpha", "group_beta"} <= p["risk_weights"].keys()
    if p["risk_bins"]:
        assert {"start_s", "end_s", "risk", "groups", "top_finding_id", "finding_ids"} <= p["risk_bins"][0].keys()
    assert all("headline" in m and "finding_ids" in m for m in p["drop_moments"])
    assert all({"finding_id", "title", "group_label", "priority_score", "priority_rank"} <= f.keys() for f in p["findings"])


def test_recompute_accepts_and_validates_baseline_params(run_id):
    client, rid = run_id
    url = f"/api/v1/runs/{rid}/prediction"
    ok = client.post(url, json={"retention_at_30s": 0.8, "retention_at_end": 0.45, "acknowledged": True,
                                "shape_k": 0.8, "end_drop_multiplier": 2.0, "end_drop_fraction": 0.1})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["recomputed"] and body["baseline"]["shape_k"] == 0.8 and body["baseline"]["end_drop_multiplier"] == 2.0
    assert body["per_second"][-1]["retention"] == pytest.approx(body["per_second"][-1]["neutral"], abs=0.5)
    default = client.post(url, json={"retention_at_30s": 0.8, "retention_at_end": 0.45, "acknowledged": True}).json()
    assert default["baseline"]["shape_k"] == 0.6
    for bad in ({"shape_k": 0.1}, {"shape_k": 1.5}, {"end_drop_multiplier": 0.5}, {"end_drop_multiplier": 4},
                {"end_drop_fraction": 0.5}, {"end_drop_fraction": -0.1}):
        r = client.post(url, json={"retention_at_30s": 0.8, "retention_at_end": 0.45, "acknowledged": True, **bad})
        assert r.status_code == 422, (bad, r.status_code)
    r = client.post(url, json={"retention_at_30s": 0.8, "retention_at_end": 0.45, "acknowledged": False, "shape_k": 0.8})
    assert r.status_code == 409
