"""Alignment stage (subprocess in the asr env): WhisperX CTC alignment.

Aligner per segment language hint: en -> facebook/wav2vec2-base-960h,
hi -> theainerd/Wav2Vec2-large-xlsr-hindi (both pinned revisions, loaded
from verified local snapshots). Mixed segments try the Hindi aligner (it
covers Devanagari); Latin-only words it cannot align stay unaligned.

Only words WhisperX actually aligned (they carry a score) keep times.
Interpolated words get null times: no fabricated precision (Schema Word).
One aligner attempt per segment (COLAB_RUNBOOK §6); failure keeps ASR
segment times and disables word-precise cut suggestions for that span.

ASR repetition loops (impossible speech rate, common.loop_guard) are removed
before alignment and listed under `dropped_segments` with the reason. Segment
IDs keep the original ASR index so they stay stable.
"""

from __future__ import annotations

import time
from pathlib import Path

from contracts.common import det_uuid
from pipeline.orchestration.io import read_json, write_json
from pipeline.speech.common import loop_guard
from pipeline.orchestration.stage import subprocess_main


def _load_aligner(snapshot_dir: str, lang: str):
    from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

    processor = Wav2Vec2Processor.from_pretrained(snapshot_dir, local_files_only=True)
    model = Wav2Vec2ForCTC.from_pretrained(snapshot_dir, local_files_only=True).to("cpu").eval()
    vocab = processor.tokenizer.get_vocab()
    meta = {"language": lang, "dictionary": {c.lower(): i for c, i in vocab.items()}, "type": "huggingface"}
    return model, meta


def _match_words(tokens: list[str], aligned: list[dict]) -> list[dict | None]:
    """Map our whitespace tokens to WhisperX words in order (it drops empty tokens)."""
    out: list[dict | None] = []
    j = 0
    for tok in tokens:
        t = tok.strip()
        if j < len(aligned) and aligned[j]["word"].strip() == t:
            out.append(aligned[j])
            j += 1
        else:
            out.append(None)
    return out


def run(args: dict, out: Path) -> dict:
    import numpy as np
    import soundfile as sf
    import torch
    import whisperx.alignment as wa

    torch.set_num_threads(int(args.get("threads") or 0) or torch.get_num_threads())
    asr = read_json(args["asr_segments"])
    audio, sr = sf.read(args["wav"], dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = np.ascontiguousarray(audio)
    asset_sha, asr_fp = args["asset_sha256"], args["asr_fingerprint"]
    kept, dropped = loop_guard(asr["segments"], args["loop_guard"])
    for d in dropped:
        print(f"dropped ASR loop artefact {d['interval']} ({d['words_per_s']} words/s): {d['text'][:70]}", flush=True)

    needed = sorted({"hi" if asr["segments"][i]["language_hint"] in ("hi", "mixed") else "en" for i in kept})
    aligners, load_errors = {}, {}
    for lang in needed:
        try:
            aligners[lang] = _load_aligner(args["aligners"][lang], lang)
        except Exception as exc:  # aligner unavailable -> those segments stay segment-precision
            load_errors[lang] = f"{type(exc).__name__}: {exc}"[:300]
            print(f"aligner {lang} unavailable: {load_errors[lang]}", flush=True)

    segments, words = [], []
    stats = {"aligned_words": 0, "unaligned_words": 0, "failed_segments": 0}
    t0 = time.time()
    for n_done, idx in enumerate(kept):
        s = asr["segments"][idx]
        seg_id = det_uuid("segment", asset_sha, asr_fp, idx)
        tokens = [t for t in s["text"].split(" ") if t.strip()]
        lang = "hi" if s["language_hint"] in ("hi", "mixed") else "en"
        aligned_words: list[dict | None] = [None] * len(tokens)
        err = None
        if lang in aligners:
            model, meta = aligners[lang]
            try:
                res = wa.align([{"start": s["start_ms"] / 1000.0, "end": s["end_ms"] / 1000.0, "text": s["text"]}],
                               model, meta, audio, "cpu", interpolate_method="nearest", return_char_alignments=False)
                flat = [w for seg in res["segments"] for w in seg.get("words", [])]
                aligned_words = _match_words(tokens, flat)
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"[:300]
                stats["failed_segments"] += 1
        else:
            err = load_errors.get(lang, "no aligner")
            stats["failed_segments"] += 1

        word_ids = []
        all_aligned = bool(tokens)
        for wi, tok in enumerate(tokens):
            wid = det_uuid("word", seg_id, wi)
            w = aligned_words[wi]
            genuine = w is not None and "score" in w and "start" in w and "end" in w
            st = int(round(w["start"] * 1000)) if genuine else None
            en = int(round(w["end"] * 1000)) if genuine else None
            if genuine and en <= st:
                genuine, st, en = False, None, None  # zero-length -> no claim of word precision
            all_aligned &= genuine
            stats["aligned_words" if genuine else "unaligned_words"] += 1
            words.append({"word_id": wid, "segment_id": seg_id, "text": tok, "start_ms": st, "end_ms": en,
                          "alignment_status": "aligned" if genuine else "unaligned",
                          "detector_confidence": round(float(w["score"]), 3) if genuine else None})
            word_ids.append(wid)
        segments.append({"segment_id": seg_id, "interval": {"start_ms": s["start_ms"], "end_ms": s["end_ms"]},
                         "text": s["text"], "language": s["language_hint"],
                         "precision": "word" if all_aligned else "segment", "source": "asr", "word_ids": word_ids,
                         "speaker_id": None, "original_asr_text": None, "correction_revision": 0,
                         "_asr": {k: s[k] for k in ("avg_logprob", "no_speech_prob", "compression_ratio", "temperature")},
                         "_align_error": err})
        if (n_done + 1) % 25 == 0:
            print(f"aligned {n_done + 1}/{len(kept)} segments ({time.time() - t0:.0f}s)", flush=True)

    stats["dropped_segments"] = len(dropped)
    write_json(out / "transcript.json", {"segments": segments, "words": words, "stats": stats, "dropped_segments": dropped,
                                         "aligner_load_errors": load_errors, "elapsed_s": round(time.time() - t0, 1)})
    total = stats["aligned_words"] + stats["unaligned_words"]
    print(f"words aligned {stats['aligned_words']}/{total}; failed segments {stats['failed_segments']}", flush=True)
    status = "complete" if not load_errors and stats["failed_segments"] == 0 else "partial"
    return {"status": status, "summary": {**stats, "segments": len(segments)}}


if __name__ == "__main__":
    subprocess_main(run)
