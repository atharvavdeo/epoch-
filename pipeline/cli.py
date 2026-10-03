"""Operator CLI (controller). Run with the media environment's python:

  .venvs/media/Scripts/python.exe -m pipeline.cli <command> ...

Commands are listed in ARCHITECTURE.md §6. No command launches Colab.
"""

from __future__ import annotations

import argparse
import sys

from pipeline.orchestration.stage import StageError


def _print_status(ws) -> None:
    from pipeline.orchestration.graph import VIDEO_STAGE_ORDER

    print(f"workspace: {ws.root}")
    for name in VIDEO_STAGE_ORDER:
        rec = ws.current(name)
        if rec is None:
            print(f"  {name:<14} -")
            continue
        warn = rec.data.get("warnings") or []
        print(f"  {name:<14} {rec.status:<9} {rec.fp16}  {rec.data.get('elapsed_s', '')}s"
              + (f"  ! {warn[0]}" if warn else ""))


def cmd_analyze(a: argparse.Namespace) -> int:
    from pipeline.orchestration.graph import run_local_until
    from pipeline.orchestration.workspace import register_video

    ws, source = register_video(a.video, title=a.title, category=a.category, language=a.language,
                                project_id=a.project_id)
    print(f"asset {source['asset_id']}  project {source['project']['project_id']}")
    ok = run_local_until(ws, source, until=a.until, allow_out_of_scope=a.allow_out_of_scope,
                         force=set(a.force or []), retry_partial=a.retry_partial, with_ocr=a.with_ocr)
    _print_status(ws)
    from pipeline.outputs import export_outputs

    print(f"readable outputs: {export_outputs(ws, source)}")
    return 0 if ok else 2


AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}


def wrap_audio(path):
    """Audio-only input: mux it with a blank 2 fps picture into MKV so the same validated probe/audio stages run.

    The audio stream is copied unchanged when MKV can hold it; otherwise re-encoded losslessly to FLAC.
    """
    import subprocess
    from pathlib import Path

    from pipeline.media.ffmpeg import ffmpeg_exe
    from pipeline.orchestration.settings import data_dir

    out = Path(data_dir()) / "transcribe_inputs" / (path.stem + ".mkv")
    out.parent.mkdir(parents=True, exist_ok=True)
    base = [ffmpeg_exe(), "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x36:r=2", "-i", str(path),
            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "ultrafast", "-shortest"]
    if subprocess.run(base + ["-c:a", "copy", str(out)]).returncode != 0:
        subprocess.run(base + ["-c:a", "flac", str(out)], check=True)
    print(f"audio-only input wrapped for the pipeline: {out}")
    return out


def cmd_transcribe(a: argparse.Namespace) -> int:
    """Audio or video in, transcript out (SRT/VTT/TXT/word JSON in outputs/<video>/). Use when no subtitles exist."""
    from pipeline.orchestration.graph import run_transcribe
    from pipeline.orchestration.workspace import register_video
    from pipeline.outputs import export_outputs
    from pathlib import Path

    media = Path(a.media)
    if media.suffix.lower() in AUDIO_EXT:
        media = wrap_audio(media)
    ws, source = register_video(str(media), title=a.title or Path(a.media).stem, category=a.category,
                                language=a.language, project_id=None)
    ok = run_transcribe(ws, source, allow_out_of_scope=a.allow_out_of_scope, force=set(a.force or []))
    out = export_outputs(ws, source)
    print(f"transcript: {out / 'transcript.srt'}  {out / '07_transcript.txt'}" if ok else "transcription failed; see status")
    return 0 if ok else 2


def cmd_status(a: argparse.Namespace) -> int:
    from pipeline.orchestration.workspace import open_workspace

    ws, _ = open_workspace(a.workspace)
    _print_status(ws)
    return 0


def cmd_outputs(a: argparse.Namespace) -> int:
    from pipeline.orchestration.workspace import open_workspace
    from pipeline.outputs import export_outputs

    ws, source = open_workspace(a.workspace)
    print(f"readable outputs: {export_outputs(ws, source)}")
    return 0


def cmd_attach_visual(a: argparse.Namespace) -> int:
    from pipeline.orchestration.graph import attach_visual
    from pipeline.orchestration.workspace import open_workspace

    ws, source = open_workspace(a.workspace)
    ok = attach_visual(ws, source, a.result_zip)
    _print_status(ws)
    return 0 if ok else 2


def cmd_finish(a: argparse.Namespace) -> int:
    from pipeline.orchestration.graph import run_finish
    from pipeline.orchestration.workspace import open_workspace
    from pipeline.outputs import export_outputs

    ws, source = open_workspace(a.workspace)
    ok = run_finish(ws, source, force=set(a.force or []))
    _print_status(ws)
    print(f"readable outputs: {export_outputs(ws, source)}")
    return 0 if ok else 2


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Hindi/Devanagari in logs on Windows consoles
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="epoch", description="PS5 retention pipeline controller")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("analyze", help="run local stages for a video (up to the Colab visual job)")
    p.add_argument("video")
    p.add_argument("--title", required=True)
    p.add_argument("--category", required=True, choices=["tech_review", "education", "other"])
    p.add_argument("--language", required=True, choices=["en", "hi", "mixed", "unknown"])
    p.add_argument("--project-id")
    p.add_argument("--until", default="visual_job", help="last stage to run")
    p.add_argument("--allow-out-of-scope", action="store_true", help="permit durations outside 300-900 s (labelled)")
    p.add_argument("--force", nargs="*", help="stage names to recompute even if cached")
    p.add_argument("--retry-partial", action="store_true", help="re-open partial/failed stages to retry failed units")
    p.add_argument("--with-ocr", action="store_true", help="include the (slow, optional) OCR stage")
    p.set_defaults(fn=cmd_analyze)

    p = sub.add_parser("transcribe", help="audio/video -> transcript only (SRT, VTT, TXT, word timings)")
    p.add_argument("media")
    p.add_argument("--title")
    p.add_argument("--category", default="other", choices=["tech_review", "education", "other"])
    p.add_argument("--language", default="unknown", choices=["en", "hi", "mixed", "unknown"])
    p.add_argument("--force", nargs="*", help="stage names to recompute even if cached")
    p.add_argument("--allow-out-of-scope", action="store_true", help="permit durations outside 300-900 s (labelled)")
    p.set_defaults(fn=cmd_transcribe)

    p = sub.add_parser("status", help="show stage status for a workspace")
    p.add_argument("workspace", help="sha prefix or workspace path")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("outputs", help="write readable CSV/TXT/JSON + Colab zip to outputs/<video>/")
    p.add_argument("workspace", help="sha prefix or workspace path")
    p.set_defaults(fn=cmd_outputs)

    p = sub.add_parser("attach-visual", help="import a Colab *.visualresult.zip (validated, never trusted blindly)")
    p.add_argument("workspace", help="sha prefix or workspace path")
    p.add_argument("result_zip")
    p.set_defaults(fn=cmd_attach_visual)

    p = sub.add_parser("finish", help="embed -> narrative (Cerebras) -> score -> export package")
    p.add_argument("workspace", help="sha prefix or workspace path")
    p.add_argument("--force", nargs="*", help="stage names to recompute")
    p.set_defaults(fn=cmd_finish)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except StageError as exc:
        print(f"ERROR [{exc.code}] {exc.message}", file=sys.stderr)
        if exc.recommended_action:
            print(f"  -> {exc.recommended_action}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
