"""Browser proxy (H.264/yuv420p + AAC MP4) and source->proxy mapping check.

TRD §3: long edge <= 1280 / short edge <= 720 ("720p"), <= 30 fps, aspect
preserved, autorotated by ffmpeg. Verification decodes checkpoint frames from
source and proxy and requires the best visual match within +-100 ms; otherwise
precision claims are disabled for the run (mapping_verified=False).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pipeline.media.ffmpeg import MediaError, run_ffmpeg

MAX_LONG, MAX_SHORT, MAX_FPS = 1280, 720, 30
CHECKPOINTS = tuple(round(0.05 + 0.1125 * i, 4) for i in range(9))  # 0.05 .. 0.95
STATIC_MAE = 0.75  # source neighbourhood this still cannot localise an offset
TOLERANCE_MS = 100


def proxy_size(display_w: int, display_h: int) -> tuple[int, int]:
    long_, short = max(display_w, display_h), min(display_w, display_h)
    scale = min(1.0, MAX_LONG / long_, MAX_SHORT / short)
    w = max(2, int(display_w * scale) // 2 * 2)
    h = max(2, int(display_h * scale) // 2 * 2)
    return w, h


def make_proxy(src: Path, dst: Path, meta: dict) -> dict:
    w, h = proxy_size(meta["display_width"], meta["display_height"])
    args = ["-i", str(src), "-map", "0:v:0"]
    if meta["has_audio"]:
        args += ["-map", "0:a:0"]
    args += [
        "-vf", f"scale={w}:{h}:flags=bicubic,format=yuv420p",
        "-fpsmax", str(MAX_FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-profile:v", "high",
        "-g", "60", "-keyint_min", "30", "-sc_threshold", "0",
    ]
    if meta["has_audio"]:
        args += ["-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "48000",
                 "-af", "aresample=async=1:first_pts=0"]
    args += ["-movflags", "+faststart", str(dst)]
    tmp = dst.with_suffix(".partial.mp4")
    args[-1] = str(tmp)
    run_ffmpeg(args)
    tmp.replace(dst)
    return {"width": w, "height": h, "max_fps": MAX_FPS, "video_codec": "h264", "audio_codec": "aac" if meta["has_audio"] else None}


@dataclass
class MappingCheck:
    verified: bool
    max_offset_ms: int
    duration_delta_ms: int
    checkpoints: list[dict]
    reason: str | None


def _thumb_at(path: Path, t_s: float, rotate_cw: int = 0):
    """Gray 64x36 thumbnail of the frame displayed at t (latest pts <= t)."""
    import av
    import numpy as np

    with av.open(str(path)) as c:
        vs = c.streams.video[0]
        tb = float(vs.time_base)
        start = float(c.start_time or 0) / 1_000_000
        target = t_s + start
        c.seek(int(max(0.0, target - 2.0) / tb), stream=vs, backward=True, any_frame=False)
        chosen = None
        for fr in c.decode(vs):
            if fr.pts is None:
                continue
            ft = fr.pts * tb
            if ft <= target + 1e-6:
                chosen = fr
            else:
                break
        if chosen is None:
            raise MediaError("seek_failed", f"no frame at {t_s:.3f}s in {path.name}")
        img = chosen.to_ndarray(format="gray")
        k = rotate_cw // 90
        if k:
            img = np.rot90(img, k=-k)
        import cv2

        small = cv2.resize(img, (64, 36), interpolation=cv2.INTER_AREA).astype("float32")
        return small, int(round((chosen.pts * tb - start) * 1000))


def verify_mapping(src: Path, proxy: Path, duration_ms: int, rotation_cw: int, proxy_duration_ms: int) -> MappingCheck:
    """Best-match offset search at checkpoints (+-200 ms in 40 ms steps)."""
    import numpy as np

    rows, worst = [], 0
    for frac in CHECKPOINTS:
        t = duration_ms / 1000.0 * frac
        ref, _ = _thumb_at(src, t, rotation_cw)
        if float(ref.std()) < 2.0:
            rows.append({"t_ms": int(t * 1000), "skipped": "flat_frame"})
            continue
        # A still neighbourhood matches every offset equally; it carries no timing information.
        before, _ = _thumb_at(src, max(0.0, t - 0.2), rotation_cw)
        after, _ = _thumb_at(src, min(duration_ms / 1000.0 - 0.05, t + 0.2), rotation_cw)
        if max(float(np.mean(np.abs(before - ref))), float(np.mean(np.abs(after - ref)))) < STATIC_MAE:
            rows.append({"t_ms": int(t * 1000), "skipped": "static_neighbourhood"})
            continue
        best = None
        for off in range(-200, 201, 40):
            cand, _ = _thumb_at(proxy, max(0.0, t + off / 1000.0))
            err = float(np.mean(np.abs(cand - ref)))
            if best is None or err < best[1] - 1e-6 or (abs(err - best[1]) <= 1e-6 and abs(off) < abs(best[0])):
                best = (off, err)
        rows.append({"t_ms": int(t * 1000), "best_offset_ms": best[0], "mae": round(best[1], 3)})
        worst = max(worst, abs(best[0]))
    dur_delta = abs(proxy_duration_ms - duration_ms)
    checked = [r for r in rows if "best_offset_ms" in r]
    verified = len(checked) >= 2 and worst <= TOLERANCE_MS and dur_delta <= TOLERANCE_MS
    reason = None
    if len(checked) < 2:
        reason = f"only {len(checked)} checkpoint(s) had motion/texture to localise timing"
    elif worst > TOLERANCE_MS:
        reason = f"proxy offset {worst} ms exceeds {TOLERANCE_MS} ms"
    elif dur_delta > TOLERANCE_MS:
        reason = f"proxy duration differs by {dur_delta} ms"
    return MappingCheck(verified, worst, dur_delta, rows, reason)
