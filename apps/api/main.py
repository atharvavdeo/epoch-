"""Local API (TRD §6). Run:

  .venvs/api/Scripts/python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8765

All routes under /api/v1. Errors use the Schema §7 envelope. The built
website (apps/web/dist) is served at / for the offline demo.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update

from apps.api import db
from apps.api.importer import ImportRejected, cleanup_orphans, import_package, read_jsonl
from contracts.common import Category, Language, new_uuid, utc_now
from contracts.package import LIMITS
from pipeline.orchestration.settings import REPO_ROOT, data_dir

APP_DIR = data_dir() / "app"
RUNS = APP_DIR / "runs"
ENGINE = db.make_engine(APP_DIR / "app.sqlite")
UPLOADS = APP_DIR / "uploads"
for d in (RUNS, UPLOADS):
    d.mkdir(parents=True, exist_ok=True)
cleanup_orphans(ENGINE, RUNS)

app = FastAPI(title="Epoch retention review (local)", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def err(status: int, code: str, message: str, *, retryable: bool = False, action: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "stage": None, "retryable": retryable, "attempt": 0, "evidence_ids": [],
        "details": {}, "recommended_action": action, "occurred_at": utc_now()}, "request_id": uuid.uuid4().hex})


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, action: str | None = None):
        self.status, self.code, self.message, self.action = status, code, message, action


@app.exception_handler(ApiError)
async def _api_error(_: Request, exc: ApiError):
    return err(exc.status, exc.code, exc.message, action=exc.action)


@app.exception_handler(HTTPException)
async def _http_error(_: Request, exc: HTTPException):
    return err(exc.status_code, "http_error", str(exc.detail))


# --------------------------------------------------------------- import worker
_jobs: "queue.Queue[tuple[str, Path]]" = queue.Queue()


def _worker() -> None:  # concurrency 1 (TRD §6): no Redis/Celery
    while True:
        import_id, path = _jobs.get()
        _set_import(import_id, "validating")
        try:
            res = import_package(ENGINE, path, RUNS)
            _set_import(import_id, "committed", committed=res["run_id"])
        except ImportRejected as exc:
            _set_import(import_id, "rejected", errors=[{"code": exc.code, "message": exc.message}])
        except Exception as exc:  # unexpected: still atomic, still reported
            _set_import(import_id, "rejected", errors=[{"code": "import_failed", "message": f"{type(exc).__name__}: {exc}"[:500]}])
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # swept on next start; never kills the worker


def _set_import(import_id: str, status: str, *, committed: str | None = None, errors: list | None = None) -> None:
    with ENGINE.begin() as c:
        c.execute(update(db.imports).where(db.imports.c.import_id == import_id).values(
            status=status, updated_at=utc_now(), committed_run_id=committed,
            errors_json=json.dumps(errors) if errors else None))


threading.Thread(target=_worker, daemon=True, name="import-worker").start()


# ------------------------------------------------------------------ helpers
def _run_row(run_id: str):
    with ENGINE.connect() as c:
        r = c.execute(select(db.runs).where(db.runs.c.run_id == run_id)).first()
    if r is None:
        raise ApiError(404, "run_not_found", f"run {run_id} is not imported")
    return r


def _project_out(row) -> dict:
    with ENGINE.connect() as c:
        runs = c.execute(select(db.runs.c.run_id, db.runs.c.status, db.runs.c.package_kind, db.runs.c.created_at)
                         .where(db.runs.c.project_id == row.project_id).order_by(db.runs.c.created_at.desc())).all()
    state = "empty" if not runs else ("ready" if any(r.package_kind == "analysis" for r in runs) else "partial")
    return {"project_id": row.project_id, "title": row.title, "category": row.category,
            "declared_language": row.declared_language, "description": row.description, "active_run_id": row.active_run_id,
            "created_at": row.created_at, "updated_at": row.updated_at, "state": state if runs else "awaiting_analysis",
            "runs": [dict(r._mapping) for r in runs]}


# ------------------------------------------------------------------ projects
class ProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    category: Category
    declared_language: Language
    description: str | None = None


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "data_dir": str(APP_DIR)}


@app.post("/api/v1/projects", status_code=201)
def create_project(p: ProjectIn):
    now = utc_now()
    pid = new_uuid()
    with ENGINE.begin() as c:
        c.execute(insert(db.projects).values(project_id=pid, title=p.title, category=p.category.value,
                                             declared_language=p.declared_language.value, description=p.description,
                                             active_run_id=None, created_at=now, updated_at=now))
        row = c.execute(select(db.projects).where(db.projects.c.project_id == pid)).first()
    return _project_out(row)


@app.get("/api/v1/projects")
def list_projects(limit: int = Query(50, ge=1, le=100)):
    with ENGINE.connect() as c:
        rows = c.execute(select(db.projects).order_by(db.projects.c.updated_at.desc()).limit(limit)).all()
    return {"items": [_project_out(r) for r in rows], "next_cursor": None}


@app.get("/api/v1/projects/{project_id}")
def get_project(project_id: str):
    with ENGINE.connect() as c:
        row = c.execute(select(db.projects).where(db.projects.c.project_id == project_id)).first()
    if row is None:
        raise ApiError(404, "project_not_found", "unknown project")
    return _project_out(row)


@app.get("/api/v1/projects/{project_id}/analysis-request")
def analysis_request(project_id: str):
    """'Prepare analysis': a request file + the exact CLI command. Never launches Colab."""
    p = get_project(project_id)
    cmd = (f'.venvs/media/Scripts/python.exe -m pipeline.cli analyze "<path-to-video>" --title "{p["title"]}" '
           f'--category {p["category"]} --language {p["declared_language"]} --project-id {project_id}')
    return {"project_id": project_id, "title": p["title"], "category": p["category"],
            "declared_language": p["declared_language"], "command": cmd,
            "note": "Uploading a video here does not start GPU analysis. Run the command, then the Colab notebook, then import the package."}


class ActiveRunIn(BaseModel):
    run_id: str


@app.post("/api/v1/projects/{project_id}/active-run")
def set_active_run(project_id: str, body: ActiveRunIn):
    r = _run_row(body.run_id)
    if r.project_id != project_id:
        raise ApiError(409, "wrong_project", "run belongs to another project")
    with ENGINE.begin() as c:
        c.execute(update(db.projects).where(db.projects.c.project_id == project_id).values(active_run_id=body.run_id,
                                                                                            updated_at=utc_now()))
    return get_project(project_id)


# ------------------------------------------------------------------- imports
@app.post("/api/v1/imports", status_code=202)
async def create_import(file: UploadFile = File(...)):
    if not (file.filename or "").endswith(".zip"):
        raise ApiError(415, "unsupported_format", "upload the *.retention.zip analysis package")
    import_id = new_uuid()
    fd, tmp_name = tempfile.mkstemp(prefix="import_", suffix=".zip", dir=UPLOADS)
    os.close(fd)  # Windows keeps the mkstemp handle locked otherwise
    tmp = Path(tmp_name)
    size = 0
    with open(tmp, "wb") as out:
        while chunk := await file.read(4 * 1024 * 1024):
            size += len(chunk)
            if size > LIMITS["zip_bytes"]:  # enforced while streaming
                out.close()
                tmp.unlink(missing_ok=True)
                raise ApiError(413, "package_too_large", "package exceeds 2 GiB")
            out.write(chunk)
    now = utc_now()
    with ENGINE.begin() as c:
        c.execute(insert(db.imports).values(import_id=import_id, status="queued", filename=file.filename, created_at=now,
                                            updated_at=now))
    _jobs.put((import_id, tmp))
    return {"import_id": import_id, "status": "queued"}


@app.get("/api/v1/imports/{import_id}")
def get_import(import_id: str):
    with ENGINE.connect() as c:
        r = c.execute(select(db.imports).where(db.imports.c.import_id == import_id)).first()
    if r is None:
        raise ApiError(404, "import_not_found", "unknown import")
    return {"import_id": r.import_id, "status": r.status, "filename": r.filename, "committed_run_id": r.committed_run_id,
            "errors": json.loads(r.errors_json) if r.errors_json else []}


# ---------------------------------------------------------------------- runs
@app.get("/api/v1/runs/{run_id}")
def get_run(run_id: str):
    r = _run_row(run_id)
    with ENGINE.connect() as c:
        a = c.execute(select(db.assets).where(db.assets.c.asset_id == r.asset_id)).first()
        proxy = c.execute(select(db.artifacts).where(db.artifacts.c.run_id == run_id, db.artifacts.c.kind == "proxy")).first()
    man = json.loads(r.manifest_json)
    run = json.loads(r.json)
    return {"run": run, "asset": json.loads(a.json), "package_kind": r.package_kind,
            "missing_stages": man["missing_stage_reasons"], "completed_stages": man["completed_stage_names"],
            "proxy_artifact_id": proxy.artifact_id if proxy else None,
            "coverage": read_jsonl(Path(r.dir), "coverage")}


@app.get("/api/v1/runs/{run_id}/transcript")
def get_transcript(run_id: str):
    r = _run_row(run_id)
    return {"segments": read_jsonl(Path(r.dir), "transcript"), "words": read_jsonl(Path(r.dir), "words")}


@app.get("/api/v1/runs/{run_id}/timeline")
def get_timeline(run_id: str, start_ms: int = Query(0, ge=0), end_ms: int | None = Query(None, ge=1)):
    r = _run_row(run_id)
    d = Path(r.dir)
    end = end_ms or 10 ** 9
    if end <= start_ms:
        raise ApiError(422, "invalid_range", "end_ms must exceed start_ms")
    ov = lambda iv: iv["start_ms"] < end and iv["end_ms"] > start_ms  # noqa: E731
    signals = read_jsonl(d, "signals")
    with ENGINE.connect() as c:
        scen = [json.loads(x.json) for x in c.execute(select(db.scenarios).where(db.scenarios.c.run_id == run_id)
                                                     .order_by(db.scenarios.c.created_at.desc()))]
    return {"run_id": run_id, "risk": [b for b in read_jsonl(d, "risk") if ov(b["interval"])],
            "scenarios": scen, "coverage": [c for c in read_jsonl(d, "coverage") if ov(c["interval"])],
            "chapters": [s for s in signals if s["feature_id"] == "F61"],
            "markers": [s for s in signals if s["name"] in ("hook", "time_to_substance")],
            "structure_spans": [s for s in signals if s["feature_id"] in ("F55", "F62", "F63", "F64", "F53", "F54", "F59", "F51")],
            "promises": read_jsonl(d, "promises"),
            "shots": [s for s in read_jsonl(d, "shots") if ov(s["interval"])],
            "duration_ms": _run_duration(r)}


def _run_duration(r) -> int:
    with ENGINE.connect() as c:
        return c.execute(select(db.assets.c.duration_ms).where(db.assets.c.asset_id == r.asset_id)).scalar_one()


@app.get("/api/v1/runs/{run_id}/issues")
def get_issues(run_id: str, modality: str | None = None, type: str | None = None, review_status: str | None = None):
    _run_row(run_id)
    with ENGINE.connect() as c:
        rows = c.execute(select(db.issues).where(db.issues.c.run_id == run_id)).all()
        sugs = {x.suggestion_id: json.loads(x.json) for x in c.execute(select(db.suggestions).where(db.suggestions.c.run_id == run_id))}
    out = []
    for row in rows:
        i = json.loads(row.json)
        i["review_status"], i["review_reason"] = row.review_status, row.review_reason
        if modality and modality not in i["modality_tags"]:
            continue
        if type and i["type"] != type:
            continue
        if review_status and i["review_status"] != review_status:
            continue
        i["suggestions"] = [sugs[s] for s in i["suggested_edit_ids"] if s in sugs]
        out.append(i)
    # stable priority: severity, then evidence strength, then start, then id
    out.sort(key=lambda i: (SEV_ORDER[i["severity"]], i["evidence_status"] != "supported", i["affected_interval"]["start_ms"], i["issue_id"]))
    return {"items": out}


@app.get("/api/v1/runs/{run_id}/evidence/{evidence_id}")
def get_evidence(run_id: str, evidence_id: str):
    r = _run_row(run_id)
    with ENGINE.connect() as c:
        e = c.execute(select(db.evidence).where(db.evidence.c.run_id == run_id, db.evidence.c.evidence_id == evidence_id)).first()
    if e is None:
        raise ApiError(404, "evidence_not_found", "evidence not in this run")
    ev = json.loads(e.json)
    table = {"transcript": ("transcript", "segment_id"), "frame": ("frames", "frame_id"),
             "observation": ("observations", "observation_id"), "signal": ("signals", "signal_id"), "ocr": ("ocr", "track_id")}
    name, key = table[ev["kind"]]
    ref = next((x for x in read_jsonl(Path(r.dir), name) if x[key] == ev["ref_id"]), None)
    frames = []
    if ev["kind"] == "observation" and ref:
        fr = {f["frame_id"]: f for f in read_jsonl(Path(r.dir), "frames")}
        frames = [fr[f] for f in ref["sampled_frame_ids"] if f in fr]
    elif ev["kind"] == "frame" and ref:
        frames = [ref]
    elif ev["kind"] == "signal" and ref and ref.get("modality") == "visual":
        # sampled stills inside the measured interval (or the nearest one), so a freeze/black finding is visible
        fr = sorted(read_jsonl(Path(r.dir), "frames"), key=lambda f: f["at_ms"])
        a, b = ref["interval"]["start_ms"], ref["interval"]["end_ms"]
        inside = [f for f in fr if a <= f["at_ms"] < b]
        if len(inside) > 8:
            inside = [inside[round(i * (len(inside) - 1) / 7)] for i in range(8)]
        frames = inside or ([min(fr, key=lambda f: abs(f["at_ms"] - (a + b) // 2))] if fr else [])
    return {"evidence": ev, "ref": ref, "frames": frames}


class ReviewIn(BaseModel):
    status: str = Field(pattern="^(open|accepted|dismissed)$")
    reason: str | None = Field(default=None, max_length=1000)


@app.patch("/api/v1/runs/{run_id}/issues/{issue_id}/review")
def review_issue(run_id: str, issue_id: str, body: ReviewIn):
    _run_row(run_id)
    with ENGINE.begin() as c:
        n = c.execute(update(db.issues).where(db.issues.c.run_id == run_id, db.issues.c.issue_id == issue_id)
                      .values(review_status=body.status, review_reason=body.reason, reviewed_at=utc_now())).rowcount
    if not n:
        raise ApiError(404, "issue_not_found", "issue not in this run")
    return {"issue_id": issue_id, "review_status": body.status, "review_reason": body.reason,
            "note": "Review state does not change the baseline scenario (RETENTION_MODEL §7)."}


class ScenarioIn(BaseModel):
    retention_at_30s: float = Field(gt=0, le=1)
    retention_at_end: float = Field(gt=0, le=1)
    kappa: float = Field(default=1.0, ge=0, le=10)
    acknowledged: bool


@app.post("/api/v1/runs/{run_id}/scenarios", status_code=201)
def create_scenario(run_id: str, body: ScenarioIn):
    """Recompute the baseline with user assumptions (same deterministic code as the pipeline)."""
    from pipeline.scoring.risk import BinRisk, TrackBin
    from pipeline.scoring.scenario import Assumptions, ScenarioUnavailable, compute_scenario

    r = _run_row(run_id)
    if not body.acknowledged:
        raise ApiError(409, "assumptions_not_acknowledged", "confirm 'These are assumptions' before computing summaries")
    rows = read_jsonl(Path(r.dir), "risk")
    bins = []
    for b in rows:
        tr = {k: TrackBin(v["risk"], v["coverage"], v["lower"], v["upper"]) for k, v in b["track_values"].items()}
        # a point value exists exactly when coverage was complete (display_value set); then lower == upper
        point = b["combined_lower"] if b["display_value"] is not None else None
        bins.append(BinRisk(b["interval"]["start_ms"], b["interval"]["end_ms"], tr, b["combined_lower"], b["combined_upper"],
                            b["evidence_coverage"], point, b["contributing_issue_ids"], None))
    try:
        sc = compute_scenario(bins, _run_duration(r), Assumptions(body.retention_at_30s, body.retention_at_end, body.kappa),
                              scoring_profile="multimodal-v1")
    except ScenarioUnavailable as exc:
        raise ApiError(422, "scenario_unavailable", str(exc)) from exc
    sid = new_uuid()
    sc.update(scenario_id=sid, base_run_id=run_id, edit_plan_id=None, created_at=utc_now(),
              assumptions=body.model_dump())
    with ENGINE.begin() as c:
        c.execute(insert(db.scenarios).values(scenario_id=sid, run_id=run_id, origin="user", created_at=sc["created_at"],
                                              json=json.dumps(sc)))
    return sc


# ------------------------------------------------------------------- media
@app.get("/api/v1/runs/{run_id}/artifacts/{artifact_id}")
def get_artifact(run_id: str, artifact_id: str, request: Request):
    r = _run_row(run_id)
    with ENGINE.connect() as c:
        a = c.execute(select(db.artifacts).where(db.artifacts.c.run_id == run_id, db.artifacts.c.artifact_id == artifact_id)).first()
    if a is None or a.kind not in ("proxy", "frame_image"):  # whitelisted media only, never arbitrary paths
        raise ApiError(404, "artifact_not_found", "no such media artifact in this run")
    path = (Path(r.dir) / a.relative_path).resolve()
    if Path(r.dir).resolve() not in path.parents:
        raise ApiError(404, "artifact_not_found", "invalid artifact path")
    ctype = "video/mp4" if a.kind == "proxy" else "image/jpeg"
    size = path.stat().st_size
    rng = request.headers.get("range")
    if not rng:
        return FileResponse(path, media_type=ctype, headers={"Accept-Ranges": "bytes", "Cache-Control": "max-age=3600"})
    try:
        unit, spec = rng.split("=", 1)
        start_s, end_s = spec.split(",")[0].split("-")
        start = int(start_s) if start_s else max(0, size - int(end_s))
        end = int(end_s) if (end_s and start_s) else size - 1
        assert unit == "bytes" and 0 <= start <= end < size
    except Exception:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})

    def body():
        with open(path, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = fh.read(min(1024 * 1024, left))
                if not chunk:
                    break
                left -= len(chunk)
                yield chunk

    return StreamingResponse(body(), status_code=206, media_type=ctype, headers={
        "Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes", "Content-Length": str(end - start + 1)})


# ----------------------------------------------------------------- website
WEB_DIST = REPO_ROOT / "apps" / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise ApiError(404, "not_found", "unknown API route")
        f = WEB_DIST / path
        return FileResponse(f if f.is_file() else WEB_DIST / "index.html")
