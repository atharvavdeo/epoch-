"""Durable local analysis jobs. One child process at a time; only validated packages are imported."""
from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import File, Form, UploadFile
from pydantic import BaseModel, Field

from contracts.common import Category, Language, new_uuid, utc_now
from contracts.package import validate_package
from pipeline.orchestration.io import read_json, write_json
from pipeline.orchestration.settings import REPO_ROOT, env_python
from pipeline.script.parse import TEXT_SUFFIXES, decode_text, parse_transcript_text

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
MAX_UPLOAD_BYTES = 2 * 1024 ** 3
MAX_TEXT_BYTES = 2 * 1024 ** 2
TERMINAL = {"complete", "failed", "cancelled"}


class TextAnalysisIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    category: Category
    language: Language
    text: str = Field(min_length=1, max_length=MAX_TEXT_BYTES)
    project_id: str | None = None
    audience: str | None = Field(default=None, max_length=2000)
    source_name: str = Field(default="pasted-script.txt", min_length=1, max_length=200)


class AnalysisJobs:
    def __init__(self, api):
        self.api = api
        self.root = api.APP_DIR / "analysis_jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.pending = queue.Queue()
        self.processes = {}
        # Never silently restart an interrupted expensive analysis or cloud call.
        for path in self.root.glob("*/job.json"):
            job = read_json(path)
            if job["status"] not in TERMINAL:
                job.update(status="failed", finished_at=utc_now(),
                           error={"code": "analysis_interrupted", "message": "Service restarted during analysis; retry to resume cached stages."})
                write_json(path, job)
        threading.Thread(target=self._worker, daemon=True, name="analysis-worker").start()

    def _dir(self, job_id):
        try:
            uuid.UUID(job_id)
        except (ValueError, TypeError, AttributeError):
            raise self.api.ApiError(404, "job_not_found", "Unknown analysis job")
        return self.root / str(uuid.UUID(job_id))

    def get(self, job_id):
        with self.lock:
            path = self._dir(job_id) / "job.json"
            if not path.exists():
                raise self.api.ApiError(404, "job_not_found", "Unknown analysis job")
            return read_json(path)

    def update(self, job_id, **changes):
        with self.lock:
            job = self.get(job_id)
            job.update(changes)
            write_json(self._dir(job_id) / "job.json", job)
            return job

    def submit(self, path, meta, kind):
        if not meta.title.strip():
            raise self.api.ApiError(422, "invalid_title", "Enter a title")
        env_python("media")  # fail before accepting when the worker environment is absent
        if meta.project_id:
            p = self.api.get_project(meta.project_id)
        else:
            p = self.api.create_project(self.api.ProjectIn(title=meta.title.strip(), category=meta.category,
                     declared_language=meta.language, description=meta.audience))
        project = {k: p.get(k) for k in ("project_id", "title", "category", "declared_language", "created_at", "updated_at", "description")}
        jid, now = new_uuid(), utc_now()
        directory = self._dir(jid)
        directory.mkdir()
        destination = directory / Path(path).name
        Path(path).replace(destination)
        notes = ["Retention scenarios are uncalibrated; candidate findings require review."]
        if kind == "text":
            notes.append("Script timestamps are subtitle cues or estimates; voice and audio are not measured.")
        elif kind == "audio":
            notes.append("Audio uses a blank playback picture; visual pacing is not analysed.")
        else:
            notes.append("Visual AI requires a separate Colab run. OCR is not requested; existing cached OCR may be retained.")
        job = {"job_id": jid, "project_id": p["project_id"], "title": p["title"], "kind": kind,
               "status": "queued", "stage": None, "stages": [], "progress": 0, "log_tail": [],
               "run_id": None, "error": None, "created_at": now, "started_at": None, "finished_at": None, "notes": notes}
        write_json(directory / "request.json", {"path": str(destination), "project": project, "kind": kind})
        write_json(directory / "job.json", job)
        self.pending.put(jid)
        return job

    def list(self, project_id):
        with self.lock:
            jobs = [read_json(p) for p in self.root.glob("*/job.json")]
        return sorted((j for j in jobs if not project_id or j["project_id"] == project_id), key=lambda j: j["created_at"], reverse=True)

    @staticmethod
    def _stop(proc):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        proc.wait(timeout=10)

    def cancel(self, job_id):
        with self.lock:
            job = self.get(job_id)
            if job["status"] in TERMINAL:
                return job
            job = self.update(job_id, status="cancelled", finished_at=utc_now())
            proc = self.processes.get(job_id)
            if proc:
                self._stop(proc)
            return job

    def close(self):
        with self.lock:
            for job in self.list(None):
                if job["status"] not in TERMINAL:
                    self.update(job["job_id"], status="failed", finished_at=utc_now(),
                                error={"code": "analysis_interrupted", "message": "Service stopped; retry to resume cached stages."})
            for proc in self.processes.values():
                self._stop(proc)
            self.pending.put(None)

    def _execute(self, job_id):
        directory = self._dir(job_id)
        proc = None
        try:
            with self.lock:
                if self.get(job_id)["status"] != "queued":
                    return
                self.update(job_id, status="running", started_at=utc_now())
                cmd = [str(env_python("media")), "-u", "-m", "pipeline.analysis_job", "--request",
                       str(directory / "request.json"), "--result", str(directory / "result.json")]
                if os.name != "nt":
                    cmd = ["nice", "-n", "10", *cmd]
                env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "EPOCH_ASR_THREADS": "6"}
                proc = subprocess.Popen(cmd, cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, encoding="utf-8", errors="replace", start_new_session=os.name != "nt",
                       creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0) if os.name == "nt" else 0)
                self.processes[job_id] = proc
            for raw in proc.stdout:
                line = raw.rstrip()
                with self.lock:
                    job = self.get(job_id)
                    if job["status"] == "cancelled":
                        break
                    if line.startswith("[epoch-job] "):
                        self.update(job_id, **json.loads(line[len("[epoch-job] "):]))
                    else:
                        # Keep only a bounded tail; credentials are never put into command arguments.
                        self.update(job_id, log_tail=(job["log_tail"] + [line[-1000:]])[-25:])
            rc = proc.wait()
            with self.lock:
                if self.get(job_id)["status"] == "cancelled":
                    return
                result = read_json(directory / "result.json") if (directory / "result.json").exists() else {}
                if rc or result.get("error") or not result.get("package"):
                    error = result.get("error") or {"code": "analysis_failed", "message": f"Analysis worker exited with code {rc}"}
                    self.update(job_id, status="failed", finished_at=utc_now(), error=error)
                    return
                # Cancellation cannot race a package commit. Importer's validator owns all persistent changes.
                package = validate_package(Path(result["package"]))
                if package.project.project_id != self.get(job_id)["project_id"]:
                    raise self.api.ApiError(409, "wrong_project", "Worker package belongs to another project; nothing imported.")
                self.update(job_id, stage="import", progress=0.98)
                committed = self.api.import_package(self.api.ENGINE, Path(result["package"]), self.api.RUNS)
                self.update(job_id, status="complete", stage="import", progress=1, run_id=committed["run_id"],
                            stages=result["stages"] + [{"name": "import", "status": "complete"}], finished_at=utc_now())
        except Exception as exc:
            with self.lock:
                if self.get(job_id)["status"] != "cancelled":
                    self.update(job_id, status="failed", finished_at=utc_now(),
                                error={"code": getattr(exc, "code", "analysis_failed"), "message": str(exc)[:1000]})
        finally:
            if proc:
                if proc.poll() is None:
                    self._stop(proc)
                proc.stdout.close()
            with self.lock:
                self.processes.pop(job_id, None)

    def _worker(self):
        while True:
            jid = self.pending.get()
            try:
                if jid is None:
                    return
                self._execute(jid)
            finally:
                self.pending.task_done()


def install(api):
    manager = AnalysisJobs(api)
    api.analysis_jobs = manager
    previous_lifespan = api.app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with previous_lifespan(app):
            try:
                yield
            finally:
                manager.close()
    api.app.router.lifespan_context = lifespan

    def check_text(name, raw):
        parsed = parse_transcript_text(name, raw)
        if parsed["words"] < 20 or parsed["duration_ms"] < 10_000 or parsed["duration_ms"] > 3_600_000:
            raise api.ApiError(422, "invalid_script", "Provide at least 20 words on a timeline between ten seconds and one hour.")

    @api.app.post("/api/v1/analyses/text", status_code=202)
    def text_analysis(body: TextAnalysisIn):
        name = Path(body.source_name.replace("\\", "/")).name or "pasted-script.txt"
        if Path(name).suffix.lower() not in TEXT_SUFFIXES:
            name += ".txt"
        check_text(name, body.text)
        directory = api.UPLOADS / new_uuid()
        directory.mkdir()
        path = directory / name
        try:
            path.write_text(body.text, encoding="utf-8")
            return manager.submit(path, body, "text")
        finally:
            path.unlink(missing_ok=True)
            directory.rmdir()

    @api.app.post("/api/v1/analyses", status_code=202)
    async def upload_analysis(file: UploadFile = File(...), title: str = Form(..., min_length=1, max_length=300), category: Category = Form(...),
                              language: Language = Form(...), project_id: str | None = Form(None), audience: str | None = Form(None, max_length=2000)):
        name = Path((file.filename or "").replace("\\", "/")).name
        suffix = Path(name).suffix.lower()
        kind = "video" if suffix in VIDEO_SUFFIXES else "audio" if suffix in AUDIO_SUFFIXES else "text" if suffix in TEXT_SUFFIXES else None
        if not kind:
            raise api.ApiError(415, "unsupported_format", "Upload a video, audio file or UTF-8 script; use package import for ZIPs.")
        meta = TextAnalysisIn(title=title, category=category, language=language, text="upload", project_id=project_id, audience=audience)
        directory = api.UPLOADS / new_uuid()
        directory.mkdir()
        path = directory / name
        size, limit = 0, MAX_TEXT_BYTES if kind == "text" else MAX_UPLOAD_BYTES
        try:
            with path.open("wb") as fh:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise api.ApiError(413, "upload_too_large", "Upload exceeds the local file size limit.")
                    fh.write(chunk)
            if size == 0:
                raise api.ApiError(422, "empty_upload", "Choose a non-empty file.")
            if kind == "text":
                try:
                    raw = decode_text(path.read_bytes())
                except UnicodeDecodeError:
                    raise api.ApiError(422, "invalid_encoding", "Save the script as UTF-8 text.")
                check_text(name, raw)
            return manager.submit(path, meta, kind)
        finally:
            await file.close()
            path.unlink(missing_ok=True)
            directory.rmdir()

    @api.app.get("/api/v1/jobs")
    def list_jobs(project_id: str | None = None):
        return {"items": manager.list(project_id)}

    @api.app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str):
        return manager.get(job_id)

    @api.app.post("/api/v1/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        return manager.cancel(job_id)
