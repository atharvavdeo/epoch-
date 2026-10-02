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
