"""User scripts retain subtitle cues or explicitly estimated timings; no fabricated word alignment."""
from pathlib import Path

from contracts.common import det_uuid, sha256_file
from pipeline.orchestration.io import write_json
from pipeline.orchestration.settings import REPO_ROOT, data_dir
from pipeline.orchestration.stage import StageError, StageResult, StageSpec, Workspace
from pipeline.script.parse import ESTIMATED_WPM, PARSER_VERSION, parse_file


def register_script(path: Path, project: dict):
    parsed = parse_file(path)
    if parsed["words"] < 20 or parsed["duration_ms"] < 10_000:
        raise StageError("script_too_short", "Provide at least 20 words and a timeline of at least ten seconds.")
    if parsed["duration_ms"] > 3_600_000:
        raise StageError("script_too_long", "Script timeline must be at most one hour.")
    sha = sha256_file(path)
    root = data_dir() / "work" / f"{sha[:16]}_{project['project_id'][:8]}"
    source = {"kind": "script", "path": str(path.resolve()), "sha256": sha, "bytes": path.stat().st_size,
              "original_name": path.name, "asset_id": det_uuid("asset", project["project_id"], sha),
              "project": project, "duration_ms": parsed["duration_ms"], "timing_source": parsed["timing"],
              "metadata": {"word_count": parsed["words"], "estimated_wpm": ESTIMATED_WPM, "timing": "estimated_script"}}
    write_json(root / "source.json", source)
    return Workspace(root, REPO_ROOT), source


def script_spec(source):
    return StageSpec(name="script", version="1", config={"parser": PARSER_VERSION},
                     extra={"sha256": source["sha256"], "language": source["project"]["declared_language"],
                            "asset_id": source["asset_id"]})


def script_stage(source):
    def fn(ctx):
        parsed = parse_file(Path(source["path"]))
        segments = [{"segment_id": det_uuid("script_segment", source["asset_id"], i),
                     "interval": {"start_ms": s["start_ms"], "end_ms": s["end_ms"]}, "text": s["text"],
                     "language": source["project"]["declared_language"], "precision": "segment" if parsed["timed"] else "estimated",
                     "source": "user", "word_ids": [], "speaker_id": None, "original_asr_text": None,
                     "correction_revision": 0} for i, s in enumerate(parsed["segments"])]
        write_json(ctx.out / "transcript.json", {"segments": segments, "words": [], "timing_source": parsed["timing"],
                   "stats": {"aligned_words": 0, "unaligned_words": parsed["words"]}, "dropped_segments": []})
        ctx.log(f"{len(segments)} user-supplied segments; {parsed['timing']}; no voice or audio measurements")
        return StageResult("complete", {"segments": len(segments)}, parsed["warnings"])
    return fn
