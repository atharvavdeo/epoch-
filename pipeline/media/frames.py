"""Sampling grid and frame extraction (TRD §3–§4, D07).

One grid serves OCR and the VLM so every sampled source frame has a single
identity: uniform 1 fps (frame displayed at k*1000 ms) + the frames on both
sides of every shot boundary. Frames are chosen by exact PTS; at_ms is the
frame's own presentation time, never the requested instant.

Outputs per frame: full-resolution upright JPEG (OCR input, crops) and a
<=448 px long-edge JPEG (VLM input, packaged evidence thumbnail).
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from contracts.common import det_uuid

UNIFORM_MS = 1000
MAX_GRID_FRAMES = 2000  # TRD §3 OCR cap
VLM_LONG_EDGE = 448
REFINE_LONG_EDGE = 896
SRC_JPEG_QUALITY = 92
VLM_JPEG_QUALITY = 90
REASON_PRIORITY = {"shot_boundary_after": 0, "shot_boundary_before": 1, "uniform_1fps": 2, "refinement_2fps": 3}


@dataclass
class GridFrame:
    frame_id: str
    pts: int
    at_ms: int
    sampling_reason: str


def frame_id_for(asset_sha: str, pts: int) -> str:
    return det_uuid("frame", asset_sha, pts)


def plan_grid(asset_sha: str, frame_ms: list[int], frame_pts: list[int], cuts: list[dict], video_end_ms: int) -> list[GridFrame]:
    chosen: dict[int, tuple[int, str]] = {}  # pts -> (at_ms, reason)

    def add(i: int, reason: str) -> None:
        if not (0 <= i < len(frame_pts)):
            return
        p = frame_pts[i]
        cur = chosen.get(p)
        if cur is None or REASON_PRIORITY[reason] < REASON_PRIORITY[cur[1]]:
            chosen[p] = (frame_ms[i], reason)

    for t in range(0, video_end_ms, UNIFORM_MS):
        i = bisect.bisect_right(frame_ms, t) - 1
        if i >= 0:
            add(i, "uniform_1fps")
    boundary: list[tuple[int, str]] = []
    pts_index = {p: i for i, p in enumerate(frame_pts)}
    for c in cuts:
        i = pts_index.get(c["pts"])
        if i is None:
            continue
        boundary += [(i, "shot_boundary_after"), (i - 1, "shot_boundary_before")]
    uniform_count = len(chosen)
    for i, reason in boundary:
        if len(chosen) >= MAX_GRID_FRAMES and frame_pts[i] not in chosen:
            continue
        add(i, reason)
    grid = [GridFrame(frame_id_for(asset_sha, p), p, ms, r) for p, (ms, r) in chosen.items()]
    grid.sort(key=lambda g: (g.at_ms, g.pts))
    if len(grid) > MAX_GRID_FRAMES:
        raise ValueError(f"grid {len(grid)} exceeds cap with {uniform_count} uniform frames")
    return grid


def _resize_long(img, long_edge: int):
    from PIL import Image

    w, h = img.size
    scale = min(1.0, long_edge / max(w, h))
    if scale >= 1.0:
        return img, (w, h)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    return img.resize(size, Image.BICUBIC), size


def extract_frames(src: Path, grid: list[GridFrame], rotation_cw: int, out_src: Path, out_vlm: Path) -> list[dict]:
    """Sequential decode; write the two JPEGs for every grid frame."""
    import av
    import numpy as np
    from PIL import Image

    out_src.mkdir(parents=True, exist_ok=True)
    out_vlm.mkdir(parents=True, exist_ok=True)
    want = {g.pts: g for g in grid}
    records: list[dict] = []
    with av.open(str(src)) as c:
        vs = c.streams.video[0]
        vs.thread_type = "AUTO"
        tb = Fraction(vs.time_base.numerator, vs.time_base.denominator)
        for packet in c.demux(vs):
            try:
                frames = packet.decode()
            except av.error.InvalidDataError:
                continue
            for fr in frames:
                g = want.get(fr.pts)
                if g is None:
                    continue
                arr = fr.to_ndarray(format="rgb24")
                k = rotation_cw // 90
                if k:
                    arr = np.ascontiguousarray(np.rot90(arr, k=-k))
                img = Image.fromarray(arr)
                sw, sh = img.size
                img.save(out_src / f"{g.frame_id}.jpg", quality=SRC_JPEG_QUALITY)
                small, (vw, vh) = _resize_long(img, VLM_LONG_EDGE)
                small.save(out_vlm / f"{g.frame_id}.jpg", quality=VLM_JPEG_QUALITY)
                transforms = ([f"rotate_cw:{rotation_cw}"] if rotation_cw else []) + (
                    [f"resize:{vw}x{vh}"] if (vw, vh) != (sw, sh) else [])
                records.append({
                    "frame_id": g.frame_id, "at_ms": g.at_ms, "source_pts": int(fr.pts),
                    "time_base_num": tb.numerator, "time_base_den": tb.denominator,
                    "width": vw, "height": vh, "source_width": sw, "source_height": sh,
                    "sampling_reason": g.sampling_reason, "crop_box": None, "clip_id": None,
                    "transformations": transforms,
                })
                del want[fr.pts]
    if want:
        missing = sorted(g.at_ms for g in want.values())[:10]
        raise RuntimeError(f"{len(want)} planned frames were not decoded (first at_ms: {missing})")
    records.sort(key=lambda r: (r["at_ms"], r["source_pts"]))
    return records


def extract_window_frames(src: Path, asset_sha: str, start_ms: int, end_ms: int, step_ms: int, zero_s: Fraction,
                          rotation_cw: int, out_dir: Path, long_edge: int, extra_pts: set[int] | None = None) -> list[dict]:
    """Seek-based extraction of every `step_ms` instant inside [start,end) plus extra PTS (refinement)."""
    import av
    import numpy as np
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    targets = list(range(start_ms, end_ms, step_ms))
    picked: dict[int, tuple[int, object]] = {}
    with av.open(str(src)) as c:
        vs = c.streams.video[0]
        tb = Fraction(vs.time_base.numerator, vs.time_base.denominator)
        seek_to = max(0.0, (start_ms / 1000.0) + float(zero_s) - 3.0)
        c.seek(int(seek_to / tb), stream=vs, backward=True, any_frame=False)
        prev = None
        ti = 0
        for fr in c.decode(vs):
            if fr.pts is None:
                continue
            f_ms = int(round((fr.pts * tb - zero_s) * 1000))
            while prev is not None and ti < len(targets) and targets[ti] < f_ms:
                picked.setdefault(prev[0], (prev[1], prev[2]))
                ti += 1
            if extra_pts and fr.pts in extra_pts and start_ms <= f_ms < end_ms:
                picked.setdefault(int(fr.pts), (f_ms, fr))
            prev = (int(fr.pts), f_ms, fr)
            if f_ms >= end_ms:
                break
        while prev is not None and ti < len(targets):
            picked.setdefault(prev[0], (prev[1], prev[2]))
            ti += 1
        out = []
        for pts, (f_ms, fr) in sorted(picked.items(), key=lambda kv: kv[1][0]):
            fid = frame_id_for(asset_sha, pts)
            arr = fr.to_ndarray(format="rgb24")
            k = rotation_cw // 90
            if k:
                arr = np.ascontiguousarray(np.rot90(arr, k=-k))
            img = Image.fromarray(arr)
            sw, sh = img.size
            small, (vw, vh) = _resize_long(img, long_edge)
            small.save(out_dir / f"{fid}.jpg", quality=VLM_JPEG_QUALITY)
            out.append({
                "frame_id": fid, "at_ms": f_ms, "source_pts": pts, "time_base_num": tb.numerator,
                "time_base_den": tb.denominator, "width": vw, "height": vh, "source_width": sw,
                "source_height": sh, "sampling_reason": "refinement_2fps", "crop_box": None, "clip_id": None,
                "transformations": ([f"rotate_cw:{rotation_cw}"] if rotation_cw else []) + (
                    [f"resize:{vw}x{vh}"] if (vw, vh) != (sw, sh) else []),
            })
    return out
