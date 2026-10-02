"""Measured transcript signals (stdlib only): F40 speech rate from aligned word
times, F52 filler density, F47 language switches, and exact-quote snapping.

All of these are measurements over the aligned transcript, not LLM opinions.
"""

from __future__ import annotations

import difflib
import re

PAUSE_GAP_MS = 500  # gaps >= this between aligned words count as pauses, not speaking time

# English fillers that are fillers in (almost) every use. "like", "so", "right", "actually" are left out:
# they are usually meaningful, and counting them would turn style into a defect.
EN_FILLERS = ("um", "uh", "erm", "uhm", "ah", "hmm", "you know", "i mean", "kind of", "sort of", "basically",
              "literally")
# Hindi discourse words (toh, matlab, yaani, ...) are NOT counted: they usually carry meaning (prompt rule).
HI_FILLERS = ("umm", "hmm", "uh")


def _norm(t: str) -> str:
    return re.sub(r"[^\w\s']", " ", t.lower())


def word_speech_rates(chunks: list[dict], words: list[dict], seg_by_id: dict) -> list[dict]:
    """WPM per paragraph over speaking time only (aligned word spans plus gaps < 500 ms).

    Falls back to segment time when fewer than 90 % of a paragraph's words are aligned (precision 'segment').
    """
    by_seg: dict[str, list[dict]] = {}
    for w in words:
        by_seg.setdefault(w["segment_id"], []).append(w)
    rates = []
    for ch in chunks:
        ws = [w for s in ch["segment_ids"] for w in by_seg.get(s, [])]
        timed = sorted((w for w in ws if w.get("start_ms") is not None), key=lambda w: w["start_ms"])
        if ws and len(timed) / len(ws) >= 0.9 and len(timed) >= 10:
            speak = 0
            for i, w in enumerate(timed):
                speak += w["end_ms"] - w["start_ms"]
                if i + 1 < len(timed):
                    gap = timed[i + 1]["start_ms"] - w["end_ms"]
                    if 0 < gap < PAUSE_GAP_MS:
                        speak += gap
            minutes, n, precision = speak / 60000, len(timed), "word"
        else:
            segs = [seg_by_id[s] for s in ch["segment_ids"]]
            n = sum(len(s["text"].split()) for s in segs)
            minutes = sum(s["interval"]["end_ms"] - s["interval"]["start_ms"] for s in segs) / 60000
            precision = "segment"
        if minutes > 0.15:
            rates.append({"chunk_id": ch["chunk_id"], "wpm": round(n / minutes), "precision": precision})
    if rates:
        med = sorted(r["wpm"] for r in rates)[len(rates) // 2]
        for r in rates:
            r["median"] = med
    return rates


def filler_counts(chunks: list[dict], seg_by_id: dict) -> list[dict]:
    """Lexicon filler occurrences per paragraph and per spoken minute."""
    out = []
    for ch in chunks:
        segs = [seg_by_id[s] for s in ch["segment_ids"]]
        text = " " + " ".join(_norm(s["text"]) for s in segs) + " "
        lex = HI_FILLERS if ch.get("language") in ("hi",) else EN_FILLERS
        found = {f: len(re.findall(rf"(?<=\s){re.escape(f)}(?=\s)", text)) for f in lex}
        found = {k: v for k, v in found.items() if v}
        minutes = sum(s["interval"]["end_ms"] - s["interval"]["start_ms"] for s in segs) / 60000
        total = sum(found.values())
        out.append({"chunk_id": ch["chunk_id"], "count": total, "per_min": round(total / minutes, 2) if minutes else 0.0,
                    "terms": found})
    return out


def language_switches(segments: list[dict]) -> list[dict]:
    """Points where the per-segment language hint changes between consecutive segments (en/hi/mixed)."""
    out = []
    prev = None
    for s in segments:
        lang = s.get("language")
        if lang in ("en", "hi", "mixed") and prev is not None and lang != prev["language"]:
            out.append({"at_ms": s["interval"]["start_ms"], "from": prev["language"], "to": lang})
        if lang in ("en", "hi", "mixed"):
            prev = s
    return out


def snap_quote(quote: str, text: str, min_ratio: float = 0.85) -> str | None:
    """The exact substring of `text` that best matches `quote` word-for-word, if similar enough.

    LLMs often return near-exact quotes (dropped comma, changed casing). Instead of discarding the span,
    replace the quote with the real words from the transcript; never accept a loose paraphrase.
    """
    tw = text.split()
    qn = _norm(quote).split()
    if not qn or not tw:
        return None
    tn = [_norm(w).strip() for w in tw]
    best, best_r = None, 0.0
    L = len(qn)
    for size in {max(1, L - 2), L - 1, L, L + 1, L + 2} - {0}:
        for i in range(0, max(1, len(tw) - size + 1)):
            r = difflib.SequenceMatcher(None, qn, tn[i:i + size], autojunk=False).ratio()
            if r > best_r:
                best, best_r = " ".join(tw[i:i + size]), r
    return best if best_r >= min_ratio else None
