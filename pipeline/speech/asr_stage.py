"""ASR stage (subprocess in the asr env): faster-whisper large-v3, CPU FP32.

Checkpointed per chunk: the audio is split at the middle of VAD non-speech
gaps into <=300 s chunks; each finished chunk is written atomically to
units/chunk_XXX.json and journalled, so a crash loses at most one chunk.
Temperature fallback is kept (robustness) with a fixed CTranslate2 seed so
reruns on the same machine/threads are reproducible.
"""

from __future__ import annotations

import time
from pathlib import Path

from pipeline.orchestration.io import append_jsonl, read_json, read_jsonl, write_json
from pipeline.orchestration.stage import StageError, subprocess_main
from pipeline.speech.common import language_hint

CHUNK_TARGET_S = 300.0
MIN_GAP_S = 0.3


def plan_chunks(speech: list[tuple[float, float]], total_s: float) -> list[tuple[float, float]]:
    """Chunk boundaries at the midpoint of the widest gap before the target length."""
    if total_s <= CHUNK_TARGET_S or not speech:
        return [(0.0, total_s)]
    gaps = [((a_end + b_start) / 2.0, b_start - a_end) for (_, a_end), (b_start, _) in zip(speech, speech[1:])
            if b_start - a_end >= MIN_GAP_S]
    bounds, start = [], 0.0
    while total_s - start > CHUNK_TARGET_S:
        window = [(mid, w) for mid, w in gaps if start + 0.5 * CHUNK_TARGET_S < mid <= start + CHUNK_TARGET_S]
        cut = max(window, key=lambda g: (g[1], -g[0]))[0] if window else start + CHUNK_TARGET_S
        bounds.append((start, cut))
        start = cut
    bounds.append((start, total_s))
    return bounds


def run(args: dict, out: Path) -> dict:
    import ctranslate2
    import numpy as np
    import soundfile as sf
    from faster_whisper import WhisperModel
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    cfg = args["config"]
    audio, sr = sf.read(args["wav"], dtype="float32")
    if sr != 16000:
        raise StageError("bad_sample_rate", f"ASR WAV must be 16 kHz, got {sr}")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    total_s = len(audio) / sr

    vad_opts = VadOptions(**cfg["vad"])
    speech = get_speech_timestamps(audio, vad_opts)
    speech_s = [(s["start"] / sr, s["end"] / sr) for s in speech]
    write_json(out / "vad.json", {"method": "silero-vad (faster-whisper bundled)", "options": cfg["vad"],
                                  "speech": [{"start_ms": int(round(a * 1000)), "end_ms": int(round(b * 1000))}
                                             for a, b in speech_s],
                                  "speech_fraction": round(sum(b - a for a, b in speech_s) / total_s, 4) if total_s else 0.0})
    chunks = plan_chunks(speech_s, total_s)
    print(f"audio {total_s:.1f}s, {len(speech_s)} speech regions, {len(chunks)} chunks", flush=True)

    ctranslate2.set_random_seed(int(cfg["seed"]))
    threads = int(args.get("threads") or 0)
    t_load = time.time()
    model = WhisperModel(args["model_dir"], device="cpu", compute_type="float32", cpu_threads=threads,
                         num_workers=1)
    load_s = time.time() - t_load
    print(f"model loaded in {load_s:.1f}s (float32, cpu_threads={threads or 'auto'})", flush=True)

    lang = args["language"]
    whisper_lang = {"en": "en", "hi": "hi", "mixed": "hi", "unknown": None}[lang]
    units_dir = out / "units"
    units_dir.mkdir(exist_ok=True)
    journal = out / "units.jsonl"
    done = {r["chunk"] for r in read_jsonl(journal, tolerate_torn_tail=True) if (units_dir / r["file"]).exists()}

    timings = []
    for ci, (c0, c1) in enumerate(chunks):
        fname = f"chunk_{ci:03d}.json"
        if ci in done:
            print(f"chunk {ci}: reused checkpoint", flush=True)
            continue
        t0 = time.time()
        seg_audio = audio[int(c0 * sr): int(c1 * sr)]
        segments, info = model.transcribe(
            seg_audio, language=whisper_lang, task="transcribe", beam_size=cfg["beam_size"],
            temperature=cfg["temperature"], vad_filter=True, vad_parameters=cfg["vad"],
            condition_on_previous_text=cfg["condition_on_previous_text"], word_timestamps=False,
            compression_ratio_threshold=cfg["compression_ratio_threshold"],
            log_prob_threshold=cfg["log_prob_threshold"], no_speech_threshold=cfg["no_speech_threshold"],
        )
        rows = []
        for s in segments:
            text = s.text.strip()
            if not text:
                continue
            a, b = c0 + s.start, min(c1, c0 + s.end)
            if b <= a:
                continue
            rows.append({"start_ms": int(round(a * 1000)), "end_ms": int(round(b * 1000)), "text": text,
                         "avg_logprob": round(float(s.avg_logprob), 4), "no_speech_prob": round(float(s.no_speech_prob), 4),
                         "compression_ratio": round(float(s.compression_ratio), 3), "temperature": float(s.temperature),
                         "chunk": ci})
        elapsed = time.time() - t0
        write_json(units_dir / fname, {"chunk": ci, "start_s": c0, "end_s": c1, "detected_language": info.language,
                                       "language_probability": round(float(info.language_probability), 4),
                                       "segments": rows, "elapsed_s": round(elapsed, 2)})
        append_jsonl(journal, {"chunk": ci, "file": fname, "segments": len(rows)})
        timings.append(elapsed)
        print(f"chunk {ci + 1}/{len(chunks)} [{c0:.0f}-{c1:.0f}s] {len(rows)} segments in {elapsed:.0f}s "
              f"(RTF {elapsed / max(1e-6, c1 - c0):.2f})", flush=True)

    segs, detected = [], []
    for ci in range(len(chunks)):
        u = read_json(units_dir / f"chunk_{ci:03d}.json")
        detected.append({"chunk": ci, "language": u["detected_language"], "probability": u["language_probability"]})
        segs.extend(u["segments"])
    segs.sort(key=lambda r: (r["start_ms"], r["end_ms"]))
    for r in segs:
        r["language_hint"] = language_hint(r["text"], lang)
    write_json(out / "asr_segments.json", {"segments": segs, "chunks": [{"start_s": a, "end_s": b} for a, b in chunks],
                                           "detected_languages": detected, "whisper_language": whisper_lang,
                                           "model_load_s": round(load_s, 2), "duration_s": round(total_s, 3)})
    if not segs:
        return {"status": "partial", "summary": {"segments": 0, "reason": "no speech recognised"}}
    return {"status": "complete", "summary": {"segments": len(segs), "chunks": len(chunks)}}


if __name__ == "__main__":
    subprocess_main(run)
