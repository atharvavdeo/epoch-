"""One sequential decode pass: shot boundaries + 2 fps analytic samples.

Shots: PySceneDetect AdaptiveDetector (threshold 3.0, min_content_val 15,
min shot 0.3 s) fed PTS-exact timecodes (TRD §3). Samples every 500 ms use
the frame actually displayed at that instant (latest pts <= t):
  F11 motion   mean |diff| of 64x36 gray between consecutive samples (0-1)
  F23 luma     mean, p05, p95, dark/bright clipped fractions (0-1)
  F24 sat      mean HSV saturation (0-1)
  F26 blur     Laplacian variance of the central 50% crop at source res
Values are measurements, not verdicts; thresholds are relative later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

SAMPLE_MS = 500
DETECTOR_CONFIG = {"detector": "AdaptiveDetector", "adaptive_threshold": 3.0, "min_content_val": 15.0,
                   "min_scene_len_s": 0.3, "window_width": 2, "analysis_width": 256}
GAP_FACTOR = 3.0  # pts jump > 3x median frame spacing => decode gap


@dataclass
class ScanResult:
    frame_pts: list[int] = field(repr=False)
    frame_ms: list[int] = field(repr=False)
    cuts: list[dict] = field(default_factory=list)  # {at_ms, pts, prev_pts, score}
    gaps: list[dict] = field(default_factory=list)  # {start_ms, end_ms}
    samples: dict = field(default_factory=dict)  # name -> list aligned with samples["t_ms"]
    decode_errors: int = 0
    frames_decoded: int = 0


def _analysis_size(w: int, h: int, target_w: int) -> tuple[int, int]:
    if w <= target_w:
        return w - w % 2, h - h % 2
    hh = int(round(h * target_w / w))
    return target_w, max(2, hh - hh % 2)


def scan_video(src: Path, zero_s: Fraction, video_end_ms: int) -> ScanResult:
    import av
    import cv2
    import numpy as np
    from scenedetect.common import FrameTimecode, Timecode
    from scenedetect.detectors import AdaptiveDetector
    from scenedetect.stats_manager import StatsManager

    det = AdaptiveDetector(adaptive_threshold=DETECTOR_CONFIG["adaptive_threshold"],
                           min_content_val=DETECTOR_CONFIG["min_content_val"],
                           window_width=DETECTOR_CONFIG["window_width"],
                           min_scene_len=DETECTOR_CONFIG["min_scene_len_s"])
    stats = StatsManager()
    det.stats_manager = stats

    res = ScanResult(frame_pts=[], frame_ms=[])
    s = {k: [] for k in ("t_ms", "frame_ms", "motion", "luma_mean", "luma_p05", "luma_p95",
                          "dark_clip", "bright_clip", "sat_mean", "blur_lapvar")}
    next_sample = 0
    prev_small = None
    last_frame = None  # (VideoFrame, ms, small_bgr)

    def take_sample(t_ms: int, frame, f_ms: int, small_bgr) -> None:
        nonlocal prev_small
        gray = frame.to_ndarray(format="gray")
        h, w = gray.shape
        crop = gray[h // 4: h - h // 4, w // 4: w - w // 4]
        tiny = cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA).astype("float32")
        motion = float(np.mean(np.abs(tiny - prev_small)) / 255.0) if prev_small is not None else 0.0
        prev_small = tiny
        hsv = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2HSV)
        s["t_ms"].append(t_ms)
        s["frame_ms"].append(f_ms)
        s["motion"].append(round(motion, 5))
        s["luma_mean"].append(round(float(gray.mean()) / 255.0, 5))
        p05, p95 = np.percentile(gray, [5, 95])
        s["luma_p05"].append(round(float(p05) / 255.0, 5))
        s["luma_p95"].append(round(float(p95) / 255.0, 5))
        s["dark_clip"].append(round(float(np.mean(gray <= 18)), 5))
        s["bright_clip"].append(round(float(np.mean(gray >= 233)), 5))
        s["sat_mean"].append(round(float(hsv[..., 1].mean()) / 255.0, 5))
        s["blur_lapvar"].append(round(float(cv2.Laplacian(crop, cv2.CV_64F).var()), 3))

    with av.open(str(src)) as c:
        vs = c.streams.video[0]
        vs.thread_type = "AUTO"
        tb = Fraction(vs.time_base.numerator, vs.time_base.denominator)
        rate = vs.average_rate or vs.guessed_rate or Fraction(25)
        fps = Fraction(rate.numerator, rate.denominator)
        start_pts = int(round(zero_s / tb))
        aw = ah = None
        for packet in c.demux(vs):
            try:
                frames = packet.decode()
            except av.error.InvalidDataError:
                res.decode_errors += 1
                continue
            for fr in frames:
                if fr.pts is None:
                    res.decode_errors += 1
                    continue
                f_ms = int(round((fr.pts * tb - zero_s) * 1000))
                if aw is None:
                    aw, ah = _analysis_size(fr.width, fr.height, DETECTOR_CONFIG["analysis_width"])
                small = fr.reformat(width=aw, height=ah, format="bgr24").to_ndarray()
                # Emit samples whose instant lies before this frame: they show the previous frame.
                while last_frame is not None and next_sample < f_ms and next_sample < video_end_ms:
                    take_sample(next_sample, last_frame[0], last_frame[1], last_frame[2])
                    next_sample += SAMPLE_MS
                tc = FrameTimecode(Timecode(pts=int(fr.pts) - start_pts, time_base=tb), fps=fps)
                for cut_tc in det.process_frame(tc, small):
                    res.cuts.append({"pts": int(cut_tc.pts) + start_pts if hasattr(cut_tc, "pts") else None,
                                     "tc_seconds": float(cut_tc.seconds)})
                res.frame_pts.append(int(fr.pts))
                res.frame_ms.append(f_ms)
                res.frames_decoded += 1
                last_frame = (fr, f_ms, small)
        for cut_tc in det.post_process(FrameTimecode(Timecode(pts=res.frame_pts[-1] - start_pts, time_base=tb), fps=fps)) if res.frame_pts else []:
            res.cuts.append({"pts": int(cut_tc.pts) + start_pts if hasattr(cut_tc, "pts") else None,
                             "tc_seconds": float(cut_tc.seconds)})
        while last_frame is not None and next_sample < video_end_ms:
            take_sample(next_sample, last_frame[0], last_frame[1], last_frame[2])
            next_sample += SAMPLE_MS

        # Resolve cut timecodes to decoded frames and attach adaptive scores.
        order = sorted(range(len(res.frame_pts)), key=lambda i: res.frame_pts[i])
        res.frame_pts = [res.frame_pts[i] for i in order]
        res.frame_ms = [res.frame_ms[i] for i in order]
        pts_index = {p: i for i, p in enumerate(res.frame_pts)}
        key = getattr(det, "_adaptive_ratio_key", None)
        resolved = []
        for cut in res.cuts:
            pts = cut["pts"]
            if pts is None or pts not in pts_index:
                target = cut["tc_seconds"] + float(zero_s)
                pts = min(res.frame_pts, key=lambda p: abs(float(p * tb) - target))
            i = pts_index[pts]
            if i == 0:
                continue
            score = None
            if key is not None:
                try:
                    tc = FrameTimecode(Timecode(pts=pts - start_pts, time_base=tb), fps=fps)
                    m = stats.get_metrics(tc, [key])
                    score = float(m[0]) if m and m[0] is not None else None
                except Exception:
                    score = None
            resolved.append({"at_ms": res.frame_ms[i], "pts": pts, "prev_pts": res.frame_pts[i - 1],
                             "prev_ms": res.frame_ms[i - 1], "score": score})
        uniq = {r["pts"]: r for r in resolved}
        res.cuts = sorted(uniq.values(), key=lambda r: r["at_ms"])

        # Decode gaps.
        deltas = [b - a for a, b in zip(res.frame_ms, res.frame_ms[1:])]
        if deltas:
            med = sorted(deltas)[len(deltas) // 2] or 1
            for a, b in zip(res.frame_ms, res.frame_ms[1:]):
                if b - a > GAP_FACTOR * med and b - a > 250:
                    res.gaps.append({"start_ms": a, "end_ms": b})
    res.samples = s
    return res


def build_shots(scan: ScanResult, video_end_ms: int) -> list[dict]:
    """Shots cover [first frame, video end) without overlap; gaps are boundaries."""
    if not scan.frame_ms:
        return []
    bounds = [(c["at_ms"], "adaptive_detector", c.get("score")) for c in scan.cuts]
    bounds += [(g["end_ms"], "decode_gap", None) for g in scan.gaps]
    bounds = sorted({b[0]: b for b in bounds}.values())
    start = scan.frame_ms[0]
    shots, prev_src = [], "video_start"
    for at, src, score in bounds:
        if at <= start or at >= video_end_ms:
            continue
        shots.append({"start_ms": start, "end_ms": at, "start_boundary_source": prev_src,
                      "end_boundary_source": src, "boundary_score": score})
        start, prev_src = at, src
    shots.append({"start_ms": start, "end_ms": video_end_ms, "start_boundary_source": prev_src,
                  "end_boundary_source": "video_end", "boundary_score": None})
    return shots


def shot_metrics(shot: dict, samples: dict) -> dict:
    """Aggregate 2 fps samples inside a shot (raw values, no judgement)."""
    import statistics

    idx = [i for i, t in enumerate(samples["t_ms"]) if shot["start_ms"] <= t < shot["end_ms"]]
    out = {"duration_ms": shot["end_ms"] - shot["start_ms"], "samples": len(idx)}
    for name in ("motion", "luma_mean", "sat_mean", "blur_lapvar"):
        vals = [samples[name][i] for i in idx]
        if name == "motion":
            vals = vals[1:]  # first sample's motion spans the cut itself
        out[f"{name}_mean"] = round(statistics.fmean(vals), 5) if vals else None
        out[f"{name}_max"] = round(max(vals), 5) if vals else None
    return out


def parse_video_filters(stderr: str, video_end_ms: int) -> dict:
    """Parse ffmpeg blackdetect/freezedetect logs (seconds -> ms)."""
    import re

    blacks = [
        {"start_ms": int(round(float(a) * 1000)), "end_ms": int(round(float(b) * 1000))}
        for a, b in re.findall(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)", stderr)
    ]
    starts = [float(x) for x in re.findall(r"freeze_start:\s*([\d.]+)", stderr)]
    ends = [float(x) for x in re.findall(r"freeze_end:\s*([\d.]+)", stderr)]
    freezes = []
    for i, st in enumerate(starts):
        en = ends[i] if i < len(ends) else video_end_ms / 1000.0
        freezes.append({"start_ms": int(round(st * 1000)), "end_ms": int(round(en * 1000)), "open_ended": i >= len(ends)})
    clean = lambda xs: [x for x in xs if x["end_ms"] > x["start_ms"]]  # noqa: E731
    return {"black": clean(blacks), "freeze": clean(freezes)}


VIDEO_FILTER_CONFIG = {"scale_width": 320, "blackdetect": "d=0.5:pic_th=0.98:pix_th=0.10",
                       "freezedetect": "n=0.003:d=2"}


def run_video_filters(src: Path, video_end_ms: int) -> dict:
    from pipeline.media.ffmpeg import run_ffmpeg

    vf = (f"scale={VIDEO_FILTER_CONFIG['scale_width']}:-2,blackdetect={VIDEO_FILTER_CONFIG['blackdetect']},"
          f"freezedetect={VIDEO_FILTER_CONFIG['freezedetect']}")
    r = run_ffmpeg(["-i", str(src), "-map", "0:v:0", "-an", "-vf", vf, "-f", "null", "-"])
    return parse_video_filters(r.stderr, video_end_ms)
