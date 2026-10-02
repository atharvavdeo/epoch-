"""SQLite index (Schema §4). Immutable run files stay on disk; rows index them.

Foreign keys ON. Review state lives in its own column, separate from the
immutable extracted issue rows. Switching the active run never deletes data.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import (
    Column, ForeignKey, Index, Integer, MetaData, String, Table, Text, create_engine, event,
)

meta = MetaData()

projects = Table("projects", meta,
                 Column("project_id", String, primary_key=True), Column("title", Text, nullable=False),
                 Column("category", String, nullable=False), Column("declared_language", String, nullable=False),
                 Column("description", Text), Column("active_run_id", String), Column("created_at", String, nullable=False),
                 Column("updated_at", String, nullable=False))
assets = Table("assets", meta,
               Column("asset_id", String, primary_key=True),
               Column("project_id", String, ForeignKey("projects.project_id"), nullable=False),
               Column("kind", String, nullable=False), Column("sha256", String, nullable=False),
               Column("duration_ms", Integer, nullable=False), Column("json", Text, nullable=False))
runs = Table("runs", meta,
             Column("run_id", String, primary_key=True),
             Column("project_id", String, ForeignKey("projects.project_id"), nullable=False),
             Column("asset_id", String, ForeignKey("assets.asset_id"), nullable=False),
             Column("status", String, nullable=False), Column("package_kind", String, nullable=False),
             Column("created_at", String, nullable=False), Column("dir", Text, nullable=False),
             Column("json", Text, nullable=False), Column("manifest_json", Text, nullable=False),
             Column("package_sha256", String, nullable=False, unique=True))
Index("ix_runs_project_created", runs.c.project_id, runs.c.created_at)
artifacts = Table("artifacts", meta,
                  Column("run_id", String, ForeignKey("runs.run_id"), primary_key=True),
                  Column("artifact_id", String, primary_key=True), Column("relative_path", Text, nullable=False),
                  Column("kind", String, nullable=False), Column("bytes", Integer, nullable=False))
evidence = Table("evidence", meta,
                 Column("run_id", String, ForeignKey("runs.run_id"), primary_key=True),
                 Column("evidence_id", String, primary_key=True), Column("kind", String, nullable=False),
                 Column("ref_id", String, nullable=False), Column("start_ms", Integer, nullable=False),
                 Column("end_ms", Integer, nullable=False), Column("json", Text, nullable=False))
Index("ix_evidence_run_kind", evidence.c.run_id, evidence.c.kind)
issues = Table("issues", meta,
               Column("run_id", String, ForeignKey("runs.run_id"), primary_key=True),
               Column("issue_id", String, primary_key=True), Column("type", String, nullable=False),
               Column("severity", String, nullable=False), Column("risk_track", String, nullable=False),
               Column("start_ms", Integer, nullable=False), Column("end_ms", Integer, nullable=False),
               Column("json", Text, nullable=False),
               Column("review_status", String, nullable=False, default="open"), Column("review_reason", Text),
               Column("reviewed_at", String))
Index("ix_issues_run_start", issues.c.run_id, issues.c.start_ms)
suggestions = Table("suggestions", meta,
                    Column("run_id", String, ForeignKey("runs.run_id"), primary_key=True),
                    Column("suggestion_id", String, primary_key=True), Column("json", Text, nullable=False))
scenarios = Table("scenarios", meta,
                  Column("scenario_id", String, primary_key=True),
                  Column("run_id", String, ForeignKey("runs.run_id"), nullable=False),
                  Column("origin", String, nullable=False), Column("created_at", String, nullable=False),
                  Column("json", Text, nullable=False))
imports = Table("imports", meta,
                Column("import_id", String, primary_key=True), Column("status", String, nullable=False),
                Column("package_sha256", String), Column("filename", Text), Column("errors_json", Text),
                Column("committed_run_id", String), Column("created_at", String, nullable=False),
                Column("updated_at", String, nullable=False))


def make_engine(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(f"sqlite:///{db_path}", future=True, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    meta.create_all(eng)
    return eng
