"""Media stage functions (run in the controller/media environment)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from pipeline.media.audio import AUDIO_CONFIG, analyse_audio, extract_asr_wav
from pipeline.media.ffmpeg import MediaError, ffmpeg_version
from pipeline.media.frames import UNIFORM_MS, VLM_LONG_EDGE, extract_frames, plan_grid
from pipeline.media.probe import probe_video
from pipeline.media.proxy import make_proxy, verify_mapping
from pipeline.media.video_scan import (
    DETECTOR_CONFIG,
    SAMPLE_MS,
    VIDEO_FILTER_CONFIG,
    build_shots,
    run_video_filters,
    scan_video,
    shot_metrics,
)
from pipeline.orchestration.io import read_json, write_json
from pipeline.orchestration.stage import StageContext, StageError, StageResult, StageSpec

MIN_DURATION_MS, MAX_DURATION_MS = 300_000, 900_000  # PRD §3 global scope


def _frac(s: str) -> Fraction:
    n, d = s.split("/")
    return Fraction(int(n), int(d))


def load_probe(rec) -> dict:
    p = read_json(rec.path("probe.json"))
    p["zero"] = _frac(p["zero_s"])
    return p


# --------------------------------------------------------------------- probe


def probe_spec(source: dict, allow_out_of_scope: bool) -> StageSpec:
    return StageSpec(name="probe", version="1", config={"allow_out_of_scope_duration": allow_out_of_scope,
                                                        "scope_ms": [MIN_DURATION_MS, MAX_DURATION_MS]},
                     extra={"source_sha256": source["sha256"]}, versions={"ffmpeg": ffmpeg_version()})


def probe_stage(source: dict, allow_out_of_scope: bool):
    def fn(ctx: StageContext) -> StageResult:
        try:
            r = probe_video(Path(source["path"]))
        except MediaError as exc:
            raise StageError(exc.code, str(exc), recommended_action="Re-export the video as H.264/AAC MP4.") from exc
        warnings = []
        if not (MIN_DURATION_MS <= r.duration_ms <= MAX_DURATION_MS):
            msg = f"duration {r.duration_ms / 1000:.1f}s is outside the 300-900 s scope"
            if not allow_out_of_scope:
                raise StageError("out_of_scope_duration", msg,
                                 recommended_action="Use a 5-15 minute video or pass --allow-out-of-scope (labelled).")
            warnings.append(msg + " (allowed by operator, labelled)")
        if r.corrupt_packets:
            warnings.append(f"{r.corrupt_packets} corrupt packets reported by demuxer")
        write_json(ctx.out / "probe.json", {
            "metadata": r.metadata, "duration_ms": r.duration_ms, "zero_s": f"{r.zero_s.numerator}/{r.zero_s.denominator}",
            "video_start_ms": r.video_start_ms, "video_end_ms": r.video_end_ms, "audio_start_ms": r.audio_start_ms,
            "audio_end_ms": r.audio_end_ms, "corrupt_packets": r.corrupt_packets, "out_of_scope": bool(warnings and not (
                MIN_DURATION_MS <= r.duration_ms <= MAX_DURATION_MS)),
        })
        ctx.log(f"{r.metadata['width']}x{r.metadata['height']} rot={r.metadata['rotation']} "
                f"vfr={r.metadata['vfr']} audio={r.metadata['has_audio']} duration={r.duration_ms}ms")
        return StageResult("complete", {"duration_ms": r.duration_ms, "frame_count": r.metadata["frame_count"]}, warnings)

    return fn


# --------------------------------------------------------------------- proxy

PROXY_CONFIG = {"max_long": 1280, "max_short": 720, "max_fps": 30, "crf": 23, "preset": "veryfast", "gop": 60,
                "audio": "aac128k48k", "tolerance_ms": 100}


def proxy_spec() -> StageSpec:
    return StageSpec(name="proxy", version="1", deps=("probe",), config=PROXY_CONFIG, versions={"ffmpeg": ffmpeg_version()})


def proxy_stage(source: dict):
    def fn(ctx: StageContext) -> StageResult:
        pr = load_probe(ctx.dep("probe"))
        dst = ctx.out / "proxy.mp4"
        info = make_proxy(Path(source["path"]), dst, pr["metadata"])
        try:
            p2 = probe_video(dst)
        except MediaError as exc:
            raise StageError("proxy_unreadable", f"proxy cannot be probed: {exc}", retryable=True) from exc
        chk = verify_mapping(Path(source["path"]), dst, pr["duration_ms"], pr["metadata"]["rotation"], p2.duration_ms)
        write_json(ctx.out / "proxy.json", {**info, "proxy_duration_ms": p2.duration_ms, "mapping_verified": chk.verified,
                                            "max_offset_ms": chk.max_offset_ms, "duration_delta_ms": chk.duration_delta_ms,
                                            "checkpoints": chk.checkpoints, "reason": chk.reason})
        ctx.log(f"proxy {info['width']}x{info['height']} mapping_verified={chk.verified} ({chk.reason or 'ok'})")
        warnings = [] if chk.verified else [f"source->proxy mapping unverified: {chk.reason}; precision claims disabled"]
        return StageResult("complete", {"mapping_verified": chk.verified}, warnings)

    return fn


# --------------------------------------------------------------------- audio


def audio_spec() -> StageSpec:
    return StageSpec(name="audio", version="1", deps=("probe",), config=AUDIO_CONFIG, versions={"ffmpeg": ffmpeg_version()})


def audio_stage(source: dict):
    def fn(ctx: StageContext) -> StageResult:
        pr = load_probe(ctx.dep("probe"))
        m = pr["metadata"]
        if not m["has_audio"]:
            write_json(ctx.out / "audio.json", {"status": "no_audio", "reason": "no decodable audio stream"})
            ctx.log("no audio stream: audio-dependent tracks will be unknown, not clean")
            return StageResult("complete", {"status": "no_audio"})
        wav = extract_asr_wav(Path(source["path"]), ctx.out / "audio16k.wav")
        analysis = analyse_audio(Path(source["path"]), pr["duration_ms"], m["audio_sample_rate"], m["audio_channels"])
        analysis["asr_wav"] = wav
        write_json(ctx.out / "audio.json", analysis)
        warnings = []
        if analysis["status"] == "corrupt":
            warnings.append("audio decode failed: " + analysis.get("reason", ""))
        if abs(wav["duration_ms"] - pr["duration_ms"]) > 200:
            warnings.append(f"ASR WAV duration {wav['duration_ms']}ms differs from media {pr['duration_ms']}ms")
        ctx.log(f"audio status={analysis['status']} silence={len(analysis.get('silence', []))} "
                f"clip_windows={len(analysis.get('clipping_windows', []))}")
        return StageResult("partial" if analysis["status"] == "corrupt" else "complete",
                           {"status": analysis["status"]}, warnings)

    return fn


# ---------------------------------------------------------------- video scan


def video_scan_spec() -> StageSpec:
    return StageSpec(name="video_scan", version="1", deps=("probe",),
                     config={"detector": DETECTOR_CONFIG, "sample_ms": SAMPLE_MS, "filters": VIDEO_FILTER_CONFIG},
                     versions={"ffmpeg": ffmpeg_version(), "scenedetect": _ver("scenedetect"), "av": _ver("av")})


def _ver(mod: str) -> str:
    try:
        import importlib.metadata as md

        return md.version(mod)
    except Exception:
        return "unknown"


def video_scan_stage(source: dict):
    def fn(ctx: StageContext) -> StageResult:
        pr = load_probe(ctx.dep("probe"))
        src = Path(source["path"])
        scan = scan_video(src, pr["zero"], pr["video_end_ms"])
        if not scan.frame_ms:
            raise StageError("decode_failed", "no video frames could be decoded")
        shots = build_shots(scan, pr["video_end_ms"])
        for s in shots:
            s["metrics"] = shot_metrics(s, scan.samples)
        filters = run_video_filters(src, pr["video_end_ms"])
        write_json(ctx.out / "scan.json", {"cuts": scan.cuts, "gaps": scan.gaps, "samples": scan.samples,
                                           "decode_errors": scan.decode_errors, "frames_decoded": scan.frames_decoded})
        write_json(ctx.out / "frame_index.json", {"frame_pts": scan.frame_pts, "frame_ms": scan.frame_ms})
        write_json(ctx.out / "shots.json", shots)
        write_json(ctx.out / "filters.json", filters)
        warnings = [f"{scan.decode_errors} undecodable packets/frames"] if scan.decode_errors else []
        ctx.log(f"frames={scan.frames_decoded} cuts={len(scan.cuts)} shots={len(shots)} "
                f"black={len(filters['black'])} freeze={len(filters['freeze'])} gaps={len(scan.gaps)}")
        return StageResult("complete", {"cuts": len(scan.cuts), "shots": len(shots)}, warnings)

    return fn


# -------------------------------------------------------------------- frames


def frames_spec() -> StageSpec:
    return StageSpec(name="frames", version="1", deps=("probe", "video_scan"),
                     config={"uniform_ms": UNIFORM_MS, "vlm_long_edge": VLM_LONG_EDGE, "boundary_frames": True,
                             "jpeg": [92, 90]}, versions={"av": _ver("av"), "pillow": _ver("pillow")})


def frames_stage(source: dict):
    def fn(ctx: StageContext) -> StageResult:
        pr = load_probe(ctx.dep("probe"))
        vs = ctx.dep("video_scan")
        idx = read_json(vs.path("frame_index.json"))
        cuts = read_json(vs.path("scan.json"))["cuts"]
        grid = plan_grid(source["sha256"], idx["frame_ms"], idx["frame_pts"], cuts, pr["video_end_ms"])
        ctx.log(f"grid {len(grid)} frames ({sum(g.sampling_reason == 'uniform_1fps' for g in grid)} uniform)")
        records = extract_frames(Path(source["path"]), grid, pr["metadata"]["rotation"], ctx.out / "src", ctx.out / "vlm")
        write_json(ctx.out / "grid.json", records)
        return StageResult("complete", {"frames": len(records)})

    return fn
