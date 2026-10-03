"""Transcript/script text -> timed segments (stdlib only; imported by the media env and the API).

Mirrors apps/web/src/transcriptParse.ts so the upload preview and the pipeline agree:
- .srt/.vtt (or any text containing "-->") keep their cue timestamps;
- plain .txt/.md become sentences/paragraphs on a timeline estimated at 150 words per minute.
One deliberate difference: duration is the latest cue end (the preview uses the last cue), so overlapping
subtitle cues can never fall outside the asset.
"""

from __future__ import annotations

import re
from pathlib import Path

ESTIMATED_WPM = 150
PARSER_VERSION = "script-parse-v1"
TEXT_SUFFIXES = {".txt", ".md", ".srt", ".vtt"}

_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
_SPLIT = re.compile(r"\n\s*\n|(?<=[.!?])\s+(?=[A-Zऀ-ॿ])")


def _ts(s: str) -> int | None:
    m = _TS.search(s.strip())
    if not m:
        return None
    h, mi, se, frac = int(m.group(1) or 0), int(m.group(2)), int(m.group(3)), m.group(4)
    return ((h * 60 + mi) * 60 + se) * 1000 + int(frac.ljust(3, "0"))


def _round(x: float) -> int:  # JavaScript Math.round (half up), not Python's banker's rounding
    return int(x + 0.5)


def decode_text(data: bytes) -> str:
    """UTF-8 (with or without BOM). Raises UnicodeDecodeError for anything else; callers turn that into a 4xx/stage error."""
    return data.decode("utf-8-sig")


def parse_transcript_text(name: str, raw: str) -> dict:
    text = re.sub(r"\r\n?", "\n", raw).lstrip("﻿")
    warnings: list[str] = []
    timed_file = bool(re.search(r"\.(srt|vtt)$", name, re.I)) or "-->" in text
    segments: list[dict] = []
    if timed_file:
        for block in re.split(r"\n\s*\n", text):
            lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
            k = next((i for i, ln in enumerate(lines) if "-->" in ln), -1)
            if k < 0:
                continue
            parts = lines[k].split("-->")
            a, b = _ts(parts[0]), _ts(parts[1]) if len(parts) > 1 else None
            body = re.sub(r"<[^>]+>", "", " ".join(lines[k + 1:])).strip()
            if a is None or b is None or not body:
                continue
            if b <= a:
                warnings.append(f"cue at {lines[k]} has end <= start; skipped")
                continue
            segments.append({"start_ms": a, "end_ms": b, "text": body})
        segments.sort(key=lambda s: s["start_ms"])
        if not segments:
            warnings.append("no timed cues found")
    else:
        stripped = re.sub(r"^#+\s*", "", text, flags=re.M)
        paras = [re.sub(r"\s+", " ", p).strip() for p in _SPLIT.split(stripped)]
        t = 0
        for p in (p for p in paras if p):
            n = len(p.split(" "))
            d = max(1000, _round(n / ESTIMATED_WPM * 60000))
            segments.append({"start_ms": t, "end_ms": t + d, "text": p})
            t += d
        if segments:
            warnings.append(f"timeline estimated at {ESTIMATED_WPM} words per minute; every timestamp is approximate")
    words = sum(len(s["text"].split()) for s in segments)
    return {"source_name": name, "timed": timed_file and bool(segments), "segments": segments, "words": words,
            "duration_ms": max((s["end_ms"] for s in segments), default=0), "warnings": warnings,
            "timing": "subtitle_timestamps" if timed_file and segments else "estimated_150wpm"}


def parse_file(path: Path, name: str | None = None) -> dict:
    path = Path(path)
    return parse_transcript_text(name or path.name, decode_text(path.read_bytes()))
