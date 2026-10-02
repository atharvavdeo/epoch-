"""Demux-level probe: streams, rotation, exact PTS list, VFR flag, duration.

Never derives frame times from average FPS (TRD §3). Time zero is the
container start time (ffmpeg's output origin).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from pipeline.media.ffmpeg import MediaError

SUPPORTED_SUFFIXES = {".mp4", ".mov", ".mkv", ".m4v"}


@dataclass
class ProbeResult:
    metadata: dict  # contracts.entities.VideoMetadata shape
    duration_ms: int
    zero_s: Fraction  # container start in seconds (timeline origin)
    video_time_base: Fraction
    frame_pts: list[int] = field(repr=False)  # sorted presentation PTS of every video packet
    video_start_ms: int = 0
    video_end_ms: int = 0
    audio_start_ms: int | None = None
    audio_end_ms: int | None = None
    corrupt_packets: int = 0


def _rotation_cw(container, vstream) -> int:
    """Clockwise degrees needed to show decoded frames upright."""
    rot = 0
    try:
        for frame in container.decode(vstream):
            rot = int(round(frame.rotation or 0))
            break
    except Exception as exc:  # decode failure is reported by caller
        raise MediaError("decode_failed", f"first video frame could not be decoded: {exc}") from exc
    # ffmpeg display-matrix angle is counter-clockwise; upright needs the inverse.
    return (-rot) % 360


def probe_video(path: Path) -> ProbeResult:
    import av

    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise MediaError("unsupported_format", f"{path.suffix} not accepted; use MP4/MOV/MKV (R01)")
    try:
        container = av.open(str(path))
    except Exception as exc:
        raise MediaError("open_failed", f"cannot open media: {exc}") from exc
    with container:
        vstreams = [s for s in container.streams if s.type == "video"]
        astreams = [s for s in container.streams if s.type == "audio"]
        if not vstreams:
            raise MediaError("no_video_stream", "file has no video stream")
        vs = vstreams[0]
        as_ = astreams[0] if astreams else None
        tb = Fraction(vs.time_base.numerator, vs.time_base.denominator)
        container_format = container.format.name
        zero_s = Fraction(container.start_time or 0, 1_000_000)  # AV_TIME_BASE microseconds
        # Copy every native field now: touching stream objects after the
        # container closes is a use-after-free inside PyAV (segfault).
        vs_index = vs.index
        w, h = vs.codec_context.width, vs.codec_context.height
        video_codec = vs.codec_context.name
        avg_rate = vs.average_rate or vs.guessed_rate
        audio_codec = as_.codec_context.name if as_ else None
        audio_rate = as_.codec_context.sample_rate if as_ else None
        audio_channels = as_.codec_context.channels if as_ else None
        has_audio_stream = as_ is not None

        streams = []
        for s in container.streams:
            t = s.type if s.type in ("video", "audio", "subtitle", "data", "attachment") else "unknown"
            codec = s.codec_context.name if getattr(s, "codec_context", None) is not None else None
            streams.append({"index": s.index, "type": t, "codec": codec})

        # Demux pass (no decode): exact PTS of every video packet, end times.
        vpts: list[int] = []
        v_end = Fraction(0)
        a_start: Fraction | None = None
        a_end: Fraction | None = None
        corrupt = 0
        demux_streams = [vs] + ([as_] if as_ else [])
        for pkt in container.demux(*demux_streams):
            if pkt.size == 0 or pkt.pts is None:
                continue
            if pkt.is_corrupt:
                corrupt += 1
            ptb = Fraction(pkt.time_base.numerator, pkt.time_base.denominator)
            end = (pkt.pts + (pkt.duration or 0)) * ptb
            if pkt.stream_index == vs_index:
                vpts.append(int(pkt.pts))
                v_end = max(v_end, end)
            else:
                start = pkt.pts * ptb
                a_start = start if a_start is None else min(a_start, start)
                a_end = end if a_end is None else max(a_end, end)
        if not vpts:
            raise MediaError("no_video_packets", "video stream contains no packets")
        vpts.sort()

    # Separate open for rotation (decoding the first frame only).
    with av.open(str(path)) as c2:
        rotation = _rotation_cw(c2, c2.streams.video[0])

    deltas = [b - a for a, b in zip(vpts, vpts[1:]) if b > a]
    vfr = False
    if len(deltas) > 10:
        med = statistics.median(deltas)
        spread = statistics.pstdev(deltas) / med if med else 0.0
        vfr = spread > 0.10 or (max(deltas) > 1.5 * med and min(deltas) < 0.67 * med)
    fps = Fraction(avg_rate.numerator, avg_rate.denominator) if avg_rate else Fraction(len(vpts), 1) / max(v_end - zero_s, Fraction(1))

    def ms(x: Fraction) -> int:
        return int(round((x - zero_s) * 1000))

    video_start_ms = ms(vpts[0] * tb)
    video_end_ms = ms(v_end)
    duration_ms = max(video_end_ms, ms(a_end) if a_end is not None else 0)
    if duration_ms <= 0:
        raise MediaError("zero_duration", "media duration is zero")

    dw, dh = (h, w) if rotation in (90, 270) else (w, h)
    meta = {
        "container": container_format,
        "width": w,
        "height": h,
        "display_width": dw,
        "display_height": dh,
        "rotation": rotation,
        "fps_num": fps.numerator,
        "fps_den": fps.denominator,
        "vfr": vfr,
        "source_start_pts": int(round(zero_s / tb)),
        "time_base_num": tb.numerator,
        "time_base_den": tb.denominator,
        "has_audio": has_audio_stream and a_end is not None,
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "audio_sample_rate": audio_rate,
        "audio_channels": audio_channels,
        "frame_count": len(vpts),
        "streams": streams,
    }
    return ProbeResult(
        metadata=meta,
        duration_ms=duration_ms,
        zero_s=zero_s,
        video_time_base=tb,
        frame_pts=vpts,
        video_start_ms=video_start_ms,
        video_end_ms=video_end_ms,
        audio_start_ms=ms(a_start) if a_start is not None else None,
        audio_end_ms=ms(a_end) if a_end is not None else None,
        corrupt_packets=corrupt,
    )


def pts_to_ms(pts: int, tb: Fraction, zero_s: Fraction) -> int:
    return int(round((pts * tb - zero_s) * 1000))
