"""Experiment: why did faster-whisper drop punctuation after 7:43 on the test video, and what fixes it?

Runs in the asr env on a short window only (CPU), with three decoder settings, and prints the text plus a
punctuation/casing score. Usage:
  .venvs/asr/Scripts/python.exe scripts/asr_punct_experiment.py <wav16k> <model_dir> <start_s> <dur_s>
"""
import re
import sys
import time

import soundfile as sf
from faster_whisper import WhisperModel

wav, model_dir, start, dur = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
audio, sr = sf.read(wav, dtype="float32")
clip = audio[int(start * sr): int((start + dur) * sr)]
model = WhisperModel(model_dir, device="cpu", compute_type="float32", cpu_threads=6)
PROMPT = "Hello, and welcome back. In this video, I'll explain how MrBeast keeps viewers watching."
variants = {
    "baseline (as shipped)": dict(condition_on_previous_text=True),
    "initial_prompt": dict(condition_on_previous_text=True, initial_prompt=PROMPT),
    "no_condition": dict(condition_on_previous_text=False),
}
for name, kw in variants.items():
    t = time.time()
    segs, _ = model.transcribe(clip, language="en", beam_size=5, temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
                               vad_filter=True, **kw)
    text = " ".join(s.text.strip() for s in segs)
    words = text.split()
    punct = sum(1 for w in words if re.search(r"[.?!,]$", w))
    caps = sum(1 for w in words if w[:1].isupper())
    print(f"== {name}: {time.time() - t:.0f}s, {len(words)} words, {punct} punctuated words, {caps} capitalised")
    print(text[:700])
    print(flush=True)
