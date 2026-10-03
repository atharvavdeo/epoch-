"""Local API behaviour (A01-A03). Run in the api env:
  .venvs/api/Scripts/python.exe -m pytest tests/test_api.py
Needs fixtures/generated/sample.retention.zip (written by tests/test_pipeline_e2e.py)."""

import io
import os
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "fixtures" / "generated" / "sample.retention.zip"
pytestmark = pytest.mark.skipif(not PKG.exists(), reason="run tests/test_pipeline_e2e.py first")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["EPOCH_DATA_DIR"] = str(tmp_path_factory.mktemp("apidata"))
    from fastapi.testclient import TestClient

    from apps.api.main import app

    return TestClient(app)


def _import(client, data: bytes, name="x.retention.zip") -> dict:
    r = client.post("/api/v1/imports", files={"file": (name, io.BytesIO(data), "application/zip")})
    assert r.status_code == 202, r.text
    iid = r.json()["import_id"]
    for _ in range(200):
        st = client.get(f"/api/v1/imports/{iid}").json()
        if st["status"] in ("committed", "rejected"):
            return st
        time.sleep(0.05)
    raise AssertionError("import did not finish")


def test_import_is_idempotent_and_review_flow(client):
    data = PKG.read_bytes()
    a = _import(client, data)
    assert a["status"] == "committed", a
    b = _import(client, data)
    assert b["status"] == "committed" and b["committed_run_id"] == a["committed_run_id"]
    projects = client.get("/api/v1/projects").json()["items"]
    assert len(projects) == 1 and len(projects[0]["runs"]) == 1
    run_id = a["committed_run_id"]
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["package_kind"] == "partial_analysis" and "ocr" in run["missing_stages"]
    issues = client.get(f"/api/v1/runs/{run_id}/issues").json()["items"]
    assert issues and all(i["suggestions"] for i in issues)
    ev = client.get(f"/api/v1/runs/{run_id}/evidence/{issues[0]['evidence_ids'][0]}").json()
    assert ev["evidence"]["evidence_id"] == issues[0]["evidence_ids"][0] and ev["ref"] is not None
    vis = next(i for i in issues if i["type"] == "technical_visual_fault")
    vev = client.get(f"/api/v1/runs/{run_id}/evidence/{vis['evidence_ids'][0]}").json()
    iv = vev["ref"]["interval"]
    assert vev["frames"] and all(iv["start_ms"] <= f["at_ms"] < iv["end_ms"] for f in vev["frames"])
    r = client.patch(f"/api/v1/runs/{run_id}/issues/{issues[0]['issue_id']}/review", json={"status": "dismissed", "reason": "intentional"})
    assert r.status_code == 200
    again = client.get(f"/api/v1/runs/{run_id}/issues?review_status=dismissed").json()["items"]
    assert [i["issue_id"] for i in again] == [issues[0]["issue_id"]]
    tl = client.get(f"/api/v1/runs/{run_id}/timeline").json()
    assert tl["risk"] and tl["scenarios"] and tl["duration_ms"] > 60000
    # assumptions must be acknowledged before summary numbers
    assert client.post(f"/api/v1/runs/{run_id}/scenarios", json={"retention_at_30s": 0.7, "retention_at_end": 0.3,
                                                                  "acknowledged": False}).status_code == 409
    sc = client.post(f"/api/v1/runs/{run_id}/scenarios", json={"retention_at_30s": 0.7, "retention_at_end": 0.3, "acknowledged": True})
    assert sc.status_code == 201 and sc.json()["summary"]["assumed_apv_pct"]["upper"] <= 100
    assert client.post(f"/api/v1/runs/{run_id}/scenarios", json={"retention_at_30s": 0.3, "retention_at_end": 0.7,
                                                                  "acknowledged": True}).status_code == 422
    # media with HTTP Range
    proxy = run["proxy_artifact_id"]
    full = client.get(f"/api/v1/runs/{run_id}/artifacts/{proxy}")
    assert full.status_code == 200 and full.content[4:8] == b"ftyp"
    part = client.get(f"/api/v1/runs/{run_id}/artifacts/{proxy}", headers={"Range": "bytes=100-199"})
    assert part.status_code == 206 and len(part.content) == 100 and part.content == full.content[100:200]
    assert client.get(f"/api/v1/runs/{run_id}/artifacts/art_doesnotexist").status_code == 404


def test_corrupt_and_malicious_packages_are_rejected_atomically(client):
    before = client.get("/api/v1/projects").json()["items"]
    data = PKG.read_bytes()
    bad = _import(client, data[: len(data) // 2], "truncated.zip")
    assert bad["status"] == "rejected" and bad["errors"]
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for n in zin.namelist():
            zout.writestr(n, zin.read(n))
        zout.writestr("../evil.json", "{}")
    trav = _import(client, buf.getvalue(), "traversal.zip")
    assert trav["status"] == "rejected" and trav["errors"][0]["code"] == "unsafe_path"
    buf2 = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(buf2, "w") as zout:
        for n in zin.namelist():
            raw = zin.read(n)
            zout.writestr(n, raw.replace(b"Sentence number 1 ", b"Sentence number X ") if n == "data/transcript.jsonl" else raw)
    tamper = _import(client, buf2.getvalue(), "tampered.zip")
    assert tamper["status"] == "rejected" and tamper["errors"][0]["code"] == "hash_mismatch"
    assert client.get("/api/v1/projects").json()["items"] == before  # nothing partially committed
    assert client.post("/api/v1/imports", files={"file": ("x.txt", io.BytesIO(b"hi"), "text/plain")}).status_code == 415


def test_transcript_export_and_relations(client):
    run_id = client.get("/api/v1/projects").json()["items"][0]["runs"][0]["run_id"]
    srt = client.get(f"/api/v1/runs/{run_id}/transcript.srt")
    assert srt.status_code == 200 and " --> " in srt.text and srt.text.startswith("1\n")
    assert client.get(f"/api/v1/runs/{run_id}/transcript.vtt").text.startswith("WEBVTT")
    assert client.get(f"/api/v1/runs/{run_id}/transcript.doc").status_code == 404
    rel = client.get(f"/api/v1/runs/{run_id}/relations").json()
    assert {"questions", "abstract_stretches", "cognitive_load", "rhythm", "summary"} <= set(rel)
