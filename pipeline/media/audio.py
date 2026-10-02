"""Audio extraction and deterministic measurements (F38–F41, F46).

- ASR input: mono 16 kHz PCM, padded to the container origin
  (aresample first_pts=0) so WAV t=0 == source t=0.
- Quality measurements run on source-rate audio, never on normalised audio.
- Distinguishes no audio stream / corrupt audio / valid silence.
"""

from __future__ import annotations

import re
import wave
from pathlib import Path

from pipeline.media.ffmpeg import MediaError, run_ffmpeg, stream_ffmpeg_stdout

AUDIO_CONFIG = {
    "asr_rate": 16000,
    "silencedetect": "n=-50dB:d=0.5",
    "clip_level": 0.999,
    "clip_window_ms": 1000,
    "clip_candidate_fraction": 0.001,  # FEATURES: >=0.1% clipped samples in 1 s
    "rms_window_ms": 500,
}


def extract_asr_wav(src: Path, dst: Path) -> dict:
    tmp = dst.with_suffix(".partial.wav")
    run_ffmpeg(["-i", str(src), "-map", "0:a:0", "-vn", "-af", "aresample=async=1:first_pts=0",
                "-ac", "1", "-ar", str(AUDIO_CONFIG["asr_rate"]), "-c:a", "pcm_s16le", str(tmp)])
    tmp.replace(dst)
    with wave.open(str(dst), "rb") as w:
        frames, rate = w.getnframes(), w.getframerate()
    return {"sample_rate": rate, "duration_ms": int(round(frames * 1000 / rate)), "channels": 1}


def _parse_loudness(stderr: str) -> dict:
    frames = re.findall(r"t:\s*([\d.]+)\s+TARGET:.*?M:\s*(-?[\d.]+|-inf)\s+S:\s*(-?[\d.]+|-inf)", stderr)
    series_t, series_s = [], []
    for t, _m, s in frames:
        series_t.append(int(round(float(t) * 1000)))
        series_s.append(None if s == "-inf" or float(s) <= -120 else round(float(s), 2))
    integ = re.search(r"Integrated loudness:\s*I:\s*(-?[\d.]+|-inf)\s*LUFS", stderr)
    lra = re.search(r"Loudness range:\s*LRA:\s*(-?[\d.]+)\s*LU", stderr)
    tpk = re.search(r"True peak:\s*Peak:\s*(-?[\d.]+|-inf)\s*dBFS", stderr)
    num = lambda m: None if (m is None or m.group(1) == "-inf") else float(m.group(1))  # noqa: E731
    # keep 1 value per second (short-term loudness is a 3 s window anyway)
    st_t, st_v = [], []
    for t, v in zip(series_t, series_s):
        if t % 1000 < 100:
            st_t.append(t - t % 1000)
            st_v.append(v)
    return {"integrated_lufs": num(integ), "lra_lu": num(lra), "true_peak_dbfs": num(tpk),
            "short_term_t_ms": st_t, "short_term_lufs": st_v}


def _parse_silence(stderr: str, end_ms: int) -> list[dict]:
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", stderr)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", stderr)]
    out = []
    for i, st in enumerate(starts):
        en = ends[i] if i < len(ends) else end_ms / 1000.0
        a, b = max(0, int(round(st * 1000))), min(end_ms, int(round(en * 1000)))
        if b > a:
            out.append({"start_ms": a, "end_ms": b})
    return out


def analyse_audio(src: Path, duration_ms: int, sample_rate: int, channels: int) -> dict:
    """Loudness, silence, clipping and RMS on source-rate audio."""
    import numpy as np

    af = f"aresample=async=1:first_pts=0,ebur128=peak=true:framelog=info,silencedetect={AUDIO_CONFIG['silencedetect']}"
    try:
        r = run_ffmpeg(["-i", str(src), "-map", "0:a:0", "-vn", "-af", af, "-f", "null", "-"])
    except MediaError as exc:
        return {"status": "corrupt", "reason": str(exc)[:500]}
    loud = _parse_loudness(r.stderr)
    silence = _parse_silence(r.stderr, duration_ms)

    ch = max(1, int(channels or 1))
    win = int(sample_rate * AUDIO_CONFIG["clip_window_ms"] / 1000)
    rms_win = int(sample_rate * AUDIO_CONFIG["rms_window_ms"] / 1000)
    clip_t, clip_frac, rms_t, rms_db = [], [], [], []
    peak = 0.0
    carry = np.zeros(0, dtype=np.float32)
    pos = 0  # in sample frames
    try:
        for buf in stream_ffmpeg_stdout(["-i", str(src), "-map", "0:a:0", "-vn", "-af", "aresample=async=1:first_pts=0",
                                         "-f", "f32le", "-acodec", "pcm_f32le", "-ac", str(ch), "-ar", str(sample_rate), "-"],
                                        chunk_bytes=win * ch * 4 * 8):
            data = np.concatenate([carry, np.frombuffer(buf, dtype=np.float32)])
            usable = (len(data) // (win * ch)) * win * ch
            block, carry = data[:usable], data[usable:]
            if usable == 0:
                continue
            frames = block.reshape(-1, ch)
            for k in range(0, len(frames), win):
                w = frames[k:k + win]
                a = np.abs(w)
                peak = max(peak, float(a.max()))
                clip_t.append(int(round((pos + k) * 1000 / sample_rate)))
                clip_frac.append(round(float(np.mean(a >= AUDIO_CONFIG["clip_level"])), 6))
                mono = w.mean(axis=1)
                for j in range(0, len(mono), rms_win):
                    seg = mono[j:j + rms_win]
                    if len(seg) == 0:
                        continue
                    rms = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2)))
                    rms_t.append(int(round((pos + k + j) * 1000 / sample_rate)))
                    rms_db.append(round(20 * np.log10(rms), 2) if rms > 1e-7 else None)
            pos += len(frames)
    except MediaError as exc:
        return {"status": "corrupt", "reason": str(exc)[:500]}

    clipped = [
        {"start_ms": t, "end_ms": min(duration_ms, t + AUDIO_CONFIG["clip_window_ms"]), "fraction": f}
        for t, f in zip(clip_t, clip_frac) if f >= AUDIO_CONFIG["clip_candidate_fraction"]
    ]
    all_silent = bool(silence) and sum(s["end_ms"] - s["start_ms"] for s in silence) >= 0.98 * duration_ms
    return {
        "status": "valid_silence" if all_silent else "valid",
        "loudness": loud,
        "silence": silence,
        "clipping_windows": [c for c in clipped if c["end_ms"] > c["start_ms"]],
        "rms": {"t_ms": rms_t, "dbfs": rms_db},
        "sample_peak": round(peak, 6),
        "decoded_ms": int(round(pos * 1000 / sample_rate)),
    }
