"""Language hints and transcript text helpers (stdlib only, any env)."""

from __future__ import annotations

import unicodedata


def script_counts(text: str) -> tuple[int, int]:
    dev = lat = 0
    for ch in text:
        cp = ord(ch)
        if 0x0900 <= cp <= 0x097F:
            dev += 1
        elif ch.isascii() and ch.isalpha():
            lat += 1
    return dev, lat


def language_hint(text: str, declared: str) -> str:
    """Per-segment language from script share (F47 text analysis).

    >=70% Devanagari letters -> hi, >=70% Latin -> en, otherwise mixed.
    Borrowed English terms inside Hindi stay a mixed hint, not a 'switch'.
    """
    dev, lat = script_counts(text)
    total = dev + lat
    if total == 0:
        return declared if declared in ("en", "hi") else "unknown"
    if dev / total >= 0.7:
        return "hi"
    if lat / total >= 0.7:
        # Romanised Hindi is Latin script; trust the declaration for hi/mixed videos.
        return "en" if declared in ("en", "unknown") else "mixed"
    return "mixed"


def normalise(text: str) -> str:
    """NFC + collapsed whitespace; used for quote/substring validation."""
    return " ".join(unicodedata.normalize("NFC", text).split())


# Whisper repetition loops emit many copies of a phrase squeezed into a few
# hundred ms. Real speech in this project measures ~3.6 words/s median, ~5
# at p90; 10 words/s over >=6 words is physically implausible. Repeated text
# at a normal rate is NOT dropped: genuine creator repetition is a finding.
LOOP_GUARD = {"max_words_per_s": 10.0, "min_words": 6}


def loop_guard(segments: list[dict], cfg: dict = LOOP_GUARD) -> tuple[list[int], list[dict]]:
    """Return (kept indices, dropped records) for ASR segments with start_ms/end_ms/text."""
    kept, dropped = [], []
    for i, s in enumerate(segments):
        n = len(s["text"].split())
        dur_s = max(1e-3, (s["end_ms"] - s["start_ms"]) / 1000.0)
        rate = n / dur_s
        if n >= cfg["min_words"] and rate > cfg["max_words_per_s"]:
            dropped.append({"asr_index": i, "interval": {"start_ms": s["start_ms"], "end_ms": s["end_ms"]},
                            "text": s["text"], "words_per_s": round(rate, 1), "reason": "impossible_speech_rate"})
        else:
            kept.append(i)
    return kept, dropped
