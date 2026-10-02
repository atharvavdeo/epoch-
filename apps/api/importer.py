"""Atomic, idempotent package import (Schema §4, A01).

validate (same validator as export) -> extract into staging -> move to
runs/<run_id>/ -> one DB transaction. A failure at any step leaves the
database unchanged and removes staging; a crash between move and commit is
cleaned on startup (orphan run dirs without a DB row). Same ZIP twice ->
the existing run (by package sha256). Same run_id with different bytes ->
rejected (immutability).
"""

from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from pathlib import Path

from sqlalchemy import insert, select, update

from apps.api import db
from contracts.common import sha256_file, utc_now
from contracts.package import PackageError, validate_package


class ImportRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def cleanup_orphans(engine, runs_root: Path) -> list[str]:
    removed = []
    if not runs_root.exists():
        return removed
    with engine.connect() as c:
        known = {r[0] for r in c.execute(select(db.runs.c.run_id))}
    for d in runs_root.iterdir():
        if d.is_dir() and (d.name not in known or d.name.endswith(".staging")):
            shutil.rmtree(d, ignore_errors=True)
            removed.append(d.name)
    return removed


def import_package(engine, zip_path: Path, runs_root: Path) -> dict:
    """Return {"run_id", "project_id", "status": "committed"|"duplicate"}; raise ImportRejected."""
    sha = sha256_file(zip_path)
    with engine.connect() as c:
        dup = c.execute(select(db.runs.c.run_id, db.runs.c.project_id).where(db.runs.c.package_sha256 == sha)).first()
    if dup:
        return {"run_id": dup.run_id, "project_id": dup.project_id, "status": "duplicate"}
    try:
        vp = validate_package(zip_path)
    except PackageError as exc:
        raise ImportRejected(exc.code, exc.message) from exc
    run_id = vp.run.run_id
    with engine.connect() as c:
        if c.execute(select(db.runs.c.run_id).where(db.runs.c.run_id == run_id)).first():
            raise ImportRejected("run_conflict", f"run {run_id} already exists with different package bytes; runs are immutable")

    staging = runs_root / f"{run_id}.staging.{uuid.uuid4().hex[:8]}"
    final = runs_root / run_id
    try:
        staging.mkdir(parents=True)
        with zipfile.ZipFile(zip_path) as z:
            for f in vp.manifest.files:  # extract only validated, listed files (never arbitrary members)
                dst = staging / f.relative_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                with z.open(f.relative_path) as src, open(dst, "wb") as out:
                    shutil.copyfileobj(src, out)
            (staging / "manifest.json").write_bytes(z.read("manifest.json"))
        if final.exists():
            shutil.rmtree(final)
        staging.rename(final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    now = utc_now()
    try:
        with engine.begin() as c:
            p = vp.project
            if not c.execute(select(db.projects.c.project_id).where(db.projects.c.project_id == p.project_id)).first():
                c.execute(insert(db.projects).values(project_id=p.project_id, title=p.title, category=p.category,
                                                     declared_language=p.declared_language, description=p.description,
                                                     active_run_id=None, created_at=p.created_at, updated_at=now))
            a = vp.asset
            if not c.execute(select(db.assets.c.asset_id).where(db.assets.c.asset_id == a.asset_id)).first():
                c.execute(insert(db.assets).values(asset_id=a.asset_id, project_id=a.project_id, kind=a.kind, sha256=a.sha256,
                                                   duration_ms=a.duration_ms, json=a.model_dump_json()))
            r = vp.run
            c.execute(insert(db.runs).values(run_id=r.run_id, project_id=r.project_id, asset_id=r.asset_id, status=r.status,
                                             package_kind=vp.manifest.package_kind, created_at=r.created_at, dir=str(final),
                                             json=r.model_dump_json(), manifest_json=vp.manifest.model_dump_json(),
                                             package_sha256=sha))
            c.execute(insert(db.artifacts), [{"run_id": run_id, "artifact_id": f.artifact_id, "relative_path": f.relative_path,
                                              "kind": f.kind, "bytes": f.bytes} for f in vp.manifest.files])
            ev = vp.records["evidence"]
            if ev:
                c.execute(insert(db.evidence), [{"run_id": run_id, "evidence_id": e.evidence_id, "kind": e.kind, "ref_id": e.ref_id,
                                                 "start_ms": e.interval.start_ms, "end_ms": e.interval.end_ms,
                                                 "json": e.model_dump_json()} for e in ev])
            iss = vp.records["issues"]
            if iss:
                c.execute(insert(db.issues), [{"run_id": run_id, "issue_id": i.issue_id, "type": i.type, "severity": i.severity,
                                               "risk_track": i.risk_track, "start_ms": i.affected_interval.start_ms,
                                               "end_ms": i.affected_interval.end_ms, "json": i.model_dump_json(),
                                               "review_status": i.review_status, "review_reason": i.review_reason,
                                               "reviewed_at": None} for i in iss])
            sug = vp.records["suggestions"]
            if sug:
                c.execute(insert(db.suggestions), [{"run_id": run_id, "suggestion_id": s.suggestion_id,
                                                    "json": s.model_dump_json()} for s in sug])
            for s in vp.records["scenarios"]:
                c.execute(insert(db.scenarios).values(scenario_id=s.scenario_id, run_id=run_id, origin="package",
                                                      created_at=s.created_at, json=s.model_dump_json()))
            # newest run becomes active; older runs stay readable (never overwritten)
            c.execute(update(db.projects).where(db.projects.c.project_id == vp.project.project_id)
                      .values(active_run_id=run_id, updated_at=now))
    except Exception:
        shutil.rmtree(final, ignore_errors=True)  # DB unchanged -> remove files too (atomic)
        raise
    return {"run_id": run_id, "project_id": vp.project.project_id, "status": "committed",
            "package_kind": vp.manifest.package_kind, "issues": len(vp.records["issues"])}


def read_jsonl(run_dir: Path, name: str) -> list[dict]:
    p = Path(run_dir) / "data" / f"{name}.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
