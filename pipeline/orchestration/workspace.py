"""Asset workspaces: one directory per (project, source bytes)."""

from __future__ import annotations

from pathlib import Path

from contracts.common import Category, Language, det_uuid, new_uuid, sha256_file, utc_now
from pipeline.orchestration.io import read_json, write_json
from pipeline.orchestration.settings import REPO_ROOT, data_dir
from pipeline.orchestration.stage import StageError, Workspace


def register_video(video: Path, *, title: str, category: str, language: str, project_id: str | None = None,
                   description: str | None = None) -> tuple[Workspace, dict]:
    """Hash the source once and create/reuse its workspace (source.json)."""
    video = Path(video).resolve()
    if not video.exists():
        raise StageError("source_missing", f"video not found: {video}")
    Category(category)
    Language(language)
    if not (1 <= len(title) <= 300):
        raise StageError("invalid_title", "title must be 1–300 characters")
    sha = sha256_file(video)
    root = data_dir() / "work" / sha[:16]
    src_path = root / "source.json"
    if src_path.exists():
        source = read_json(src_path)
        if source["sha256"] != sha:
            raise StageError("workspace_collision", f"workspace {root} belongs to different bytes")
        changed = (source["project"]["title"], source["project"]["category"], source["project"]["declared_language"]) != (
            title, category, language)
        source["path"] = str(video)  # file may have moved; bytes are what matter
        if project_id and project_id != source["project"]["project_id"]:
            raise StageError("project_mismatch", "this video is already registered to another project_id")
        if changed:
            source["project"].update(title=title, category=category, declared_language=language, updated_at=utc_now())
        write_json(src_path, source)
    else:
        pid = project_id or new_uuid()
        now = utc_now()
        source = {
            "kind": "video",
            "path": str(video),
            "sha256": sha,
            "bytes": video.stat().st_size,
            "original_name": video.name,
            "asset_id": det_uuid("asset", pid, sha),
            "project": {"project_id": pid, "title": title, "category": category, "declared_language": language,
                        "created_at": now, "updated_at": now, "active_run_id": None, "description": description},
        }
        write_json(src_path, source)
    return Workspace(root, REPO_ROOT), source


def open_workspace(key: str) -> tuple[Workspace, dict]:
    """Open by sha prefix (>=8 hex) or workspace path."""
    p = Path(key)
    if not (p / "source.json").exists():
        work = data_dir() / "work"
        matches = [d for d in work.glob(f"{key}*") if (d / "source.json").exists()] if work.exists() else []
        if len(matches) != 1:
            raise StageError("workspace_not_found", f"no unique workspace for '{key}' ({len(matches)} matches)")
        p = matches[0]
    return Workspace(p, REPO_ROOT), read_json(p / "source.json")
