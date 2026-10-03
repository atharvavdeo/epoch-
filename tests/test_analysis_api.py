"""Browser analysis contract, real child-process cancellation and validated package commit."""
import json
import subprocess
import sys
import time

from test_api import client, PKG, _import

SCRIPT = " ".join(["This example explains a useful process with clear steps and a concrete result."] * 3)


def terminal(client, job_id):
    for _ in range(200):
        j = client.get(f"/api/v1/jobs/{job_id}").json()
        if j["status"] in ("complete", "failed", "cancelled"):
            return j
        time.sleep(.02)
    raise AssertionError("job did not stop")


def test_upload_rejections_do_not_create_projects(client, monkeypatch):
    from apps.api import analysis
    monkeypatch.setattr(analysis, "MAX_TEXT_BYTES", 32)
    before = client.get("/api/v1/projects").json()
    fields = dict(title="Validation test", category="education", language="en")
    for filename, data, code in [("x.exe", b"x", 415), ("x.mp4", b"", 422), ("x.txt", b"\xff", 422),
                                  ("x.txt", b"short", 422), ("x.txt", b"x" * 33, 413)]:
        r = client.post("/api/v1/analyses", data=fields, files={"file": (filename, data)})
        assert r.status_code == code, r.text
    assert client.post("/api/v1/analyses/text", json={**fields, "text": "short"}).status_code == 422
    assert client.get("/api/v1/projects").json() == before
    assert client.get("/api/v1/jobs/not-a-uuid").status_code == 404


def test_job_commits_validated_package_and_reports_progress(client, monkeypatch):
    from apps.api import analysis
    run_id = _import(client, PKG.read_bytes())["committed_run_id"]
    project = client.get(f"/api/v1/runs/{run_id}").json()["project"]
    real_popen = subprocess.Popen
    def child(cmd, **kwargs):
        result_path = cmd[cmd.index("--result") + 1]
        result = dict(package=str(PKG), stages=[dict(name="export", status="complete")])
        code = "from pathlib import Path; import json; print('[epoch-job] ' + json.dumps({'stage':'export','progress':.9})); Path(" + repr(result_path) + ").write_text(" + repr(json.dumps(result)) + ")"
        return real_popen([sys.executable, "-c", code], **kwargs)
    monkeypatch.setattr(analysis.subprocess, "Popen", child)
    r = client.post("/api/v1/analyses/text", json=dict(title=project["title"], category=project["category"], language=project["declared_language"],
                                                     project_id=project["project_id"], text=SCRIPT))
    assert r.status_code == 202, r.text
    done = terminal(client, r.json()["job_id"])
    assert done["status"] == "complete" and done["run_id"] == run_id and done["progress"] == 1
    assert done["stages"][-1] == {"name": "import", "status": "complete"}
    assert any(j["job_id"] == done["job_id"] for j in client.get("/api/v1/jobs", params={"project_id": project["project_id"]}).json()["items"])


def test_cancellation_kills_child_and_never_imports(client, monkeypatch):
    from apps.api import analysis, main
    real_popen, children = subprocess.Popen, []
    def child(cmd, **kwargs):
        p = real_popen([sys.executable, "-c", "import time; print('running', flush=True); time.sleep(60)"], **kwargs)
        children.append(p)
        return p
    monkeypatch.setattr(analysis.subprocess, "Popen", child)
    r = client.post("/api/v1/analyses", data=dict(title="Cancellation test", category="other", language="en"),
                    files={"file": ("../../script.txt", SCRIPT.encode())})
    assert r.status_code == 202, r.text
    jid = r.json()["job_id"]
    for _ in range(100):
        if children:
            break
        time.sleep(.01)
    assert children
    cancel = client.post(f"/api/v1/jobs/{jid}/cancel")
    assert cancel.status_code == 200 and cancel.json()["status"] == "cancelled"
    children[0].wait(timeout=2)
    main.analysis_jobs.pending.join()
    done = client.get(f"/api/v1/jobs/{jid}").json()
    assert done["status"] == "cancelled" and done["run_id"] is None
    assert not client.get(f"/api/v1/projects/{done['project_id']}").json()["runs"]


def test_wrong_project_package_is_rejected_before_import(client, monkeypatch):
    from apps.api import analysis, main
    real_popen = subprocess.Popen
    def child(cmd, **kwargs):
        result_path = cmd[cmd.index("--result") + 1]
        data = dict(package=str(PKG), stages=[])
        code = "from pathlib import Path; Path(" + repr(result_path) + ").write_text(" + repr(json.dumps(data)) + ")"
        return real_popen([sys.executable, "-c", code], **kwargs)
    monkeypatch.setattr(analysis.subprocess, "Popen", child)
    r = client.post("/api/v1/analyses/text", json=dict(title="Wrong project check", category="other", language="en", text=SCRIPT))
    assert r.status_code == 202
    done = terminal(client, r.json()["job_id"])
    main.analysis_jobs.pending.join()
    assert done["status"] == "failed" and done["error"]["code"] == "wrong_project" and done["run_id"] is None
    assert not client.get(f"/api/v1/projects/{done['project_id']}").json()["runs"]
