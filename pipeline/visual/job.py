"""visual_job stage: package everything the Colab VLM needs into one zip.

Bundle layout (job.json lists every file with sha256):
  job.json                     clips, frames, context, limits, profiles
  frames/<frame_id>.jpg        448 px base frames (+ 896 px refinement frames)
  runtime/epoch_vlm/*.py       runner code (self-contained)
  runtime/prompts/visual_observation.v2.md
  runtime/locks/vlm.txt        hashed Colab environment lock

Clip plan (TRD §4): non-overlapping 20 s cores (final shortened; a <2 s tail
merges into the previous core), +-2 s context, <=32 frames chosen at run
time by priority from 1 fps + cut-boundary frames. OCR and transcript are
optional context: when absent the prompt says so and coverage records it.
"""

from __future__ import annotations

import bisect
import shutil
import statistics
import zipfile
from pathlib import Path

from contracts.common import det_uuid, fingerprint, sha256_file, utc_now
from epoch_vlm import BOOTSTRAP_PROTOCOL, JOB_PROTOCOL
from pipeline.media.frames import REFINE_LONG_EDGE, extract_window_frames
from pipeline.model_registry import VLM_PROFILES
from pipeline.orchestration.io import read_json, write_json
from pipeline.orchestration.settings import REPO_ROOT
from pipeline.orchestration.stage import StageContext, StageError, StageResult, StageSpec

CLIP_MS, CONTEXT_MS, MERGE_TAIL_MS = 20_000, 2_000, 2_000
DEFAULT_PROFILES = ["Q35-9B-BF16"]  # D17: user-chosen default; 27B only by explicit opt-in
LIMITS = {"max_input_tokens": 12288, "max_new_tokens": 1024, "frame_cap": 32, "refine_frame_cap": 24,
          "max_base_clips": 45, "max_refinements": 8, "max_repairs": 8, "oom_retry_token_cap": 6144,
          "stop_fail_fraction": 0.2}
RUNTIME_FILES = ["epoch_vlm/__init__.py", "epoch_vlm/backends.py", "epoch_vlm/fetch.py", "epoch_vlm/preflight.py",
                 "epoch_vlm/prompting.py", "epoch_vlm/runner.py", "epoch_vlm/schema.py",
                 "prompts/visual_observation.v2.md", "locks/vlm.txt"]
MAX_TRANSCRIPT_CHARS, MAX_OCR_LINES = 2500, 20


def runtime_digest() -> str:
    return fingerprint([[f, sha256_file(REPO_ROOT / f)] for f in RUNTIME_FILES])


def plan_clips(video_start_ms: int, video_end_ms: int) -> list[dict]:
    cores = []
    s = video_start_ms
    while s < video_end_ms:
        cores.append([s, min(s + CLIP_MS, video_end_ms)])
        s += CLIP_MS
    if len(cores) > 1 and cores[-1][1] - cores[-1][0] < MERGE_TAIL_MS:
        cores[-2][1] = cores.pop()[1]
    return [{"clip_id": f"c{i:03d}", "core": {"start_ms": a, "end_ms": b},
             "context": {"start_ms": max(video_start_ms, a - CONTEXT_MS), "end_ms": min(video_end_ms, b + CONTEXT_MS)}}
            for i, (a, b) in enumerate(cores)]


def _overlap(a0, a1, b0, b1) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def _grid_reasons(grid: list[dict], frame_ms: list[int], frame_pts: list[int], cuts: list[dict], end_ms: int) -> dict:
    """All sampling reasons per grid frame (grid.json keeps only the strongest)."""
    reasons: dict[int, set] = {g["source_pts"]: set() for g in grid}
    for t in range(0, end_ms, 1000):
        i = bisect.bisect_right(frame_ms, t) - 1
        if i >= 0 and frame_pts[i] in reasons:
            reasons[frame_pts[i]].add("uniform_1fps")
    idx = {p: i for i, p in enumerate(frame_pts)}
    for c in cuts:
        i = idx.get(c["pts"])
        if i is None:
            continue
        if frame_pts[i] in reasons:
            reasons[frame_pts[i]].add("shot_boundary_after")
        if i > 0 and frame_pts[i - 1] in reasons:
            reasons[frame_pts[i - 1]].add("shot_boundary_before")
    return reasons


def _position(quad, w, h) -> tuple[str, float]:
    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    cx, cy = (min(xs) + max(xs)) / 2 / w, (min(ys) + max(ys)) / 2 / h
    vert = "top" if cy < 0.33 else "bottom" if cy > 0.67 else "middle"
    horiz = "left" if cx < 0.33 else "right" if cx > 0.67 else "center"
    return f"{vert}-{horiz}", round(100 * (max(ys) - min(ys)) / h, 1)


def build_job(source: dict, deps: dict, out: Path, profiles: list[str], log=print) -> dict:
    probe = read_json(deps["probe"].path("probe.json"))
    vs = deps["video_scan"]
    scan, shots, filters = read_json(vs.path("scan.json")), read_json(vs.path("shots.json")), read_json(vs.path("filters.json"))
    idx = read_json(vs.path("frame_index.json"))
    frames_rec = deps["frames"]
    grid = read_json(frames_rec.path("grid.json"))
    audio = read_json(deps["audio"].path("audio.json")) if "audio" in deps else {"status": "unknown"}
    transcript = read_json(deps["align"].path("transcript.json"))["segments"] if "align" in deps else None
    vad = read_json(deps["asr"].path("vad.json"))["speech"] if "asr" in deps else None
    ocr_tracks = read_json(deps["ocr"].path("ocr_tracks.json")) if "ocr" in deps else None
    meta = probe["metadata"]
    W, H = meta["display_width"], meta["display_height"]
    end_ms = probe["video_end_ms"]

    reasons = _grid_reasons(grid, idx["frame_ms"], idx["frame_pts"], scan["cuts"], end_ms)
    by_id = {g["frame_id"]: g for g in grid}
    samples = scan["samples"]
    clips = plan_clips(probe["video_start_ms"], end_ms)
    if len(clips) > LIMITS["max_base_clips"] + 1:
        raise StageError("too_many_clips", f"{len(clips)} clips exceeds cap {LIMITS['max_base_clips']}")

    (out / "bundle" / "frames").mkdir(parents=True, exist_ok=True)
    used_frames: set[str] = set()
    for c in clips:
        core, ctx = c["core"], c["context"]
        fr = [g for g in grid if ctx["start_ms"] <= g["at_ms"] < ctx["end_ms"]]
        c["frames"] = []
        for n, g in enumerate(fr, 1):
            role = "core" if core["start_ms"] <= g["at_ms"] < core["end_ms"] else "context"
            c["frames"].append({"ref": f"F{n:02d}", "frame_id": g["frame_id"], "at_ms": g["at_ms"], "role": role,
                                "reasons": sorted(reasons.get(g["source_pts"], {g["sampling_reason"]})),
                                "sampling_reason": g["sampling_reason"], "file": f"frames/{g['frame_id']}.jpg",
                                "width": g["width"], "height": g["height"]})
            used_frames.add(g["frame_id"])
        # transcript context
        c["transcript"], chars = [], 0
        for s in transcript or []:
            iv = s["interval"]
            if _overlap(iv["start_ms"], iv["end_ms"], ctx["start_ms"], ctx["end_ms"]) and chars < MAX_TRANSCRIPT_CHARS:
                c["transcript"].append({"segment_id": s["segment_id"], "start_ms": iv["start_ms"], "end_ms": iv["end_ms"],
                                        "text": s["text"][:600],
                                        "in_core": _overlap(iv["start_ms"], iv["end_ms"], core["start_ms"], core["end_ms"]) > 0})
                chars += len(s["text"])
        c["transcript_available"] = transcript is not None
        # OCR context
        c["ocr"] = []
        if ocr_tracks:
            refs_by_frame = {f["frame_id"]: f["ref"] for f in c["frames"]}
            cand = [t for t in ocr_tracks if _overlap(t["start_ms"], t["end_ms"], ctx["start_ms"], ctx["end_ms"])]
            cand.sort(key=lambda t: -(t["detector_confidence"] * (t["end_ms"] - t["start_ms"])))
            for t in cand[:MAX_OCR_LINES]:
                pos, hpct = _position(t["samples"][0]["quad"], W, H)
                c["ocr"].append({"text": t["text"][:120], "start_ms": t["start_ms"], "end_ms": t["end_ms"],
                                 "frame_refs": [refs_by_frame[s["frame_id"]] for s in t["samples"] if s["frame_id"] in refs_by_frame],
                                 "position": pos, "height_pct": hpct, "confidence": round(t["detector_confidence"], 2)})
        c["ocr_available"] = ocr_tracks is not None
        # measurements
        in_core = [i for i, t in enumerate(samples["t_ms"]) if core["start_ms"] <= t < core["end_ms"]]
        mot = [samples["motion"][i] for i in in_core[1:]]
        speech_pct = None
        if vad is not None:
            sp = sum(_overlap(v["start_ms"], v["end_ms"], core["start_ms"], core["end_ms"]) for v in vad)
            speech_pct = round(100 * sp / (core["end_ms"] - core["start_ms"]))
        c["measurements"] = {
            "shots": [{"start_ms": s["start_ms"], "end_ms": s["end_ms"], "boundary_score": s.get("boundary_score")}
                      for s in shots if _overlap(s["start_ms"], s["end_ms"], core["start_ms"], core["end_ms"])],
            "cuts_in_core": sum(1 for x in scan["cuts"] if core["start_ms"] < x["at_ms"] < core["end_ms"]),
            "motion_mean": round(statistics.fmean(mot), 4) if mot else None,
            "motion_max": round(max(mot), 4) if mot else None,
            "black": [b for b in filters["black"] if _overlap(b["start_ms"], b["end_ms"], core["start_ms"], core["end_ms"])],
            "freeze": [{"start_ms": f["start_ms"], "end_ms": f["end_ms"]} for f in filters["freeze"]
                       if _overlap(f["start_ms"], f["end_ms"], core["start_ms"], core["end_ms"])],
            "silence": [s for s in audio.get("silence", []) if _overlap(s["start_ms"], s["end_ms"], core["start_ms"], core["end_ms"])],
            "speech_pct": speech_pct,
        }
        c["input_digest"] = fingerprint({k: c[k] for k in ("core", "context", "frames", "transcript", "ocr", "measurements")}
                                        | {"frame_sha": [sha256_file(frames_rec.path(f"vlm/{f['frame_id']}.jpg")) for f in c["frames"]]})

    for fid in sorted(used_frames):
        shutil.copyfile(frames_rec.path(f"vlm/{fid}.jpg"), out / "bundle" / "frames" / f"{fid}.jpg")

    refinements = plan_refinements(clips, scan, ocr_tracks, W, H)
    for r in refinements:
        extra = {c["pts"] for c in scan["cuts"] if r["interval"]["start_ms"] <= c["at_ms"] < r["interval"]["end_ms"]}
        fr = extract_window_frames(Path(source["path"]), source["sha256"], r["interval"]["start_ms"], r["interval"]["end_ms"],
                                   500, _frac(probe["zero_s"]), meta["rotation"], out / "bundle" / "frames",
                                   REFINE_LONG_EDGE, extra_pts=extra)
        if len(fr) > LIMITS["refine_frame_cap"]:
            step = len(fr) / LIMITS["refine_frame_cap"]
            fr = [fr[int(i * step)] for i in range(LIMITS["refine_frame_cap"])]
        r["frames"] = [{"ref": f"R{n:02d}", "frame_id": f["frame_id"], "at_ms": f["at_ms"], "role": "core",
                        "reasons": ["refinement_2fps"], "sampling_reason": "refinement_2fps",
                        "file": f"frames/{f['frame_id']}.jpg", "width": f["width"], "height": f["height"]} for f in fr]
        r["frame_records"] = fr
        r["input_digest"] = fingerprint({"interval": r["interval"], "reason": r["reason"],
                                         "frames": [[f["frame_id"], sha256_file(out / "bundle" / "frames" / f"{f['frame_id']}.jpg")] for f in fr]})
    # remove refinement frames that were subsampled away
    keep = used_frames | {f["frame_id"] for r in refinements for f in r["frames"]}
    for p in (out / "bundle" / "frames").glob("*.jpg"):
        if p.stem not in keep:
            p.unlink()

    rt = out / "bundle" / "runtime"
    for f in RUNTIME_FILES:
        dst = rt / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / f, dst)
    files = [{"path": p.relative_to(out / "bundle").as_posix(), "sha256": sha256_file(p), "bytes": p.stat().st_size}
             for p in sorted((out / "bundle").rglob("*")) if p.is_file()]
    profiles_cfg = {k: VLM_PROFILES[k] for k in profiles}
    return {"clips": clips, "refinements": refinements, "files": files, "profiles": profiles_cfg,
            "asset": {"asset_id": source["asset_id"], "sha256": source["sha256"], "duration_ms": probe["duration_ms"],
                      "video_end_ms": end_ms, "display_width": W, "display_height": H},
            "project": {k: source["project"][k] for k in ("title", "category", "declared_language")},
            "context_available": {"transcript": transcript is not None, "ocr": ocr_tracks is not None, "vad": vad is not None}}


def _frac(s: str):
    from fractions import Fraction

    n, d = s.split("/")
    return Fraction(int(n), int(d))


def plan_refinements(clips: list[dict], scan: dict, ocr_tracks: list | None, W: int, H: int) -> list[dict]:
    """<=8 deterministic candidate windows (<=10 s): small text, dense cuts, motion spikes."""
    end = clips[-1]["core"]["end_ms"]
    cands: list[dict] = []
    for t in ocr_tracks or []:
        q = t["samples"][0]["quad"]
        h = (max(p[1] for p in q) - min(p[1] for p in q)) / H
        if h < 0.035 and t["detector_confidence"] >= 0.5:
            s = max(0, t["start_ms"] - 1000)
            cands.append({"reason": "small_text", "start": s, "score": 1.0 - h / 0.035,
                          "focus_text": "read the small on-screen text exactly and judge whether a viewer could read it in time."})
    cut_ms = [c["at_ms"] for c in scan["cuts"]]
    for s in range(0, end, 5000):
        n = sum(1 for x in cut_ms if s <= x < s + 10_000)
        if n >= 5:
            cands.append({"reason": "fast_cuts", "start": s, "score": n / 10.0,
                          "focus_text": "describe what each quick shot shows and whether the sequence stays understandable."})
    mot = scan["samples"]["motion"]
    if len(mot) > 20:
        thr = sorted(mot)[int(0.98 * len(mot))]
        for t, m in zip(scan["samples"]["t_ms"], mot):
            if m >= thr and m > 0.05:
                cands.append({"reason": "fast_action", "start": max(0, t - 3000), "score": m,
                              "focus_text": "describe the visible action across these stills; say what cannot be judged."})
    picked: list[dict] = []
    # round-robin over reasons keeps variety among the <=8 windows
    pools = {r: sorted([c for c in cands if c["reason"] == r], key=lambda c: -c["score"]) for r in ("small_text", "fast_cuts", "fast_action")}
    while len(picked) < LIMITS["max_refinements"] and any(pools.values()):
        for r in ("small_text", "fast_cuts", "fast_action"):
            while pools[r]:
                c = pools[r].pop(0)
                a, b = c["start"], min(end, c["start"] + 10_000)
                if b - a < 2000 or any(_overlap(a, b, p["interval"]["start_ms"], p["interval"]["end_ms"]) for p in picked):
                    continue
                clip = next(cl for cl in clips if cl["core"]["start_ms"] <= a < cl["core"]["end_ms"] or cl is clips[-1])
                picked.append({"refine_id": f"r{len(picked):02d}", "clip_id": clip["clip_id"], "reason": c["reason"],
                               "reason_text": c["reason"].replace("_", " "), "focus_text": c["focus_text"],
                               "interval": {"start_ms": a, "end_ms": b}, "crops": []})
                break
            if len(picked) >= LIMITS["max_refinements"]:
                break
    return picked


def visual_job_spec(source: dict, profiles: list[str] | None = None) -> StageSpec:
    profiles = profiles or DEFAULT_PROFILES
    return StageSpec(name="visual_job", version="1", deps=("probe", "video_scan", "frames"),
                     optional_deps=("audio", "asr", "align", "ocr"),
                     config={"clip_ms": CLIP_MS, "context_ms": CONTEXT_MS, "limits": LIMITS, "profiles": profiles},
                     extra={"runtime_digest": runtime_digest(), "title": source["project"]["title"],
                            "category": source["project"]["category"],
                            "language": source["project"]["declared_language"]})


def visual_job_stage(source: dict, profiles: list[str] | None = None):
    profiles = profiles or DEFAULT_PROFILES

    def fn(ctx: StageContext) -> StageResult:
        built = build_job(source, ctx.deps, ctx.out, profiles, log=ctx.log)
        job = {"protocol": JOB_PROTOCOL, "bootstrap_protocol": BOOTSTRAP_PROTOCOL,
               "job_id": det_uuid("visual_job", ctx.fingerprint), "job_fingerprint": ctx.fingerprint,
               "created_at": utc_now(), "runtime_digest": runtime_digest(), "profiles_allowed": profiles,
               "limits": LIMITS, **{k: v for k, v in built.items() if k != "files"}}
        for r in job["refinements"]:
            r.pop("frame_records", None)
        job["files"] = built["files"]
        write_json(ctx.out / "bundle" / "job.json", job)
        zname = f"{source['sha256'][:16]}_{ctx.fingerprint[:16]}.visualjob.zip"
        zpath = ctx.out / zname
        with zipfile.ZipFile(zpath, "w") as z:
            for p in sorted((ctx.out / "bundle").rglob("*")):
                if p.is_file():
                    comp = zipfile.ZIP_STORED if p.suffix == ".jpg" else zipfile.ZIP_DEFLATED
                    z.write(p, p.relative_to(ctx.out / "bundle").as_posix(), compress_type=comp)
        write_json(ctx.out / "job_summary.json", {"zip": zname, "clips": len(job["clips"]),
                                                  "refinements": len(job["refinements"]), "frames": len(built["files"]),
                                                  "context_available": built["context_available"],
                                                  "bytes": zpath.stat().st_size})
        warn = [f"{k} not available to the VLM (coverage will say so)" for k, v in built["context_available"].items() if not v]
        ctx.log(f"job {zname}: {len(job['clips'])} clips, {len(job['refinements'])} refinements, "
                f"{zpath.stat().st_size / 1e6:.1f} MB")
        return StageResult("complete", {"zip": zname, "clips": len(job["clips"])}, warn)

    return fn
