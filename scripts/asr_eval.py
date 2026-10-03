"""Compare our transcript with a reference transcript (word error rate + where the two disagree).

The reference may itself be machine-made (YouTube auto-captions are): then WER measures AGREEMENT, and the
disagreement list has to be judged by a person. Reference formats: YouTube's "Show transcript" paste
(timestamp line, text line, chapter titles), SRT/VTT, or plain text.

  .venvs/media/Scripts/python.exe scripts/asr_eval.py <ours: transcript.json | api transcript json> <reference.txt> [--out report.json]
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter

NUM = {w: str(i) for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())}
NUM.update({"twenty": "20", "thirty": "30", "forty": "40", "fifty": "50", "hundred": "100"})


def norm_words(text: str) -> list[str]:
    t = text.lower().replace("%", " ").replace("mr.", "mr")
    t = re.sub(r"\[(music|applause|laughter)\]", " ", t)
    t = re.sub(r"\bmr\s+(beast|b|beasts|beast's|b's)\b", lambda m: "mrbeast" + ("s" if m.group(1).endswith("s") else ""), t)
    t = re.sub(r"\bmrbeast's\b", "mrbeasts", t)
    t = re.sub(r"(\d),(\d)", r"\1\2", t)
    words = re.findall(r"[a-z0-9']+", t.replace("-", " "))
    t = re.sub(r"\$(\d+),?000\b", lambda m: m.group(1) + " thousand dollars", t)
    return [NUM.get(w, w).replace("'", "") for w in words]


def merge_names(ws: list[str], ts: list[int]) -> tuple[list[str], list[int]]:
    """'mr' + 'beast'/'b' split across caption lines -> 'mrbeast' (the name, not a word error)."""
    out, ot, k = [], [], 0
    while k < len(ws):
        if ws[k] == "mr" and k + 1 < len(ws) and ws[k + 1] in ("beast", "b", "beasts", "bs"):
            out.append("mrbeasts" if ws[k + 1].endswith("s") else "mrbeast"); ot.append(ts[k]); k += 2
        else:
            out.append(ws[k]); ot.append(ts[k]); k += 1
    return out, ot


def parse_reference(raw: str) -> list[tuple[int, str]]:
    """[(start_ms, text)] from a YouTube transcript paste; chapter-title lines (no timestamp before them) are dropped."""
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    out, cur = [], None
    for l in lines:
        m = re.fullmatch(r"(?:(\d+):)?(\d+):(\d{2})", l)
        if m:
            cur = ((int(m.group(1) or 0) * 60 + int(m.group(2))) * 60 + int(m.group(3))) * 1000
            continue
        if cur is not None:
            out.append((cur, l))
            cur = None  # a second text line without its own timestamp is a chapter title
    return out


def align(ref: list[str], hyp: list[str]):
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
    ops, i, j = [], n, m
    while i or j:
        if i and j and d[i][j] == d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            ops.append(("ok" if ref[i - 1] == hyp[j - 1] else "sub", i - 1, j - 1)); i -= 1; j -= 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            ops.append(("del", i - 1, None)); i -= 1
        else:
            ops.append(("ins", None, j - 1)); j -= 1
    return ops[::-1]


def main() -> None:
    ours = json.load(open(sys.argv[1], encoding="utf-8"))
    segs = sorted(ours["segments"], key=lambda s: s["interval"]["start_ms"])
    ref_lines = parse_reference(open(sys.argv[2], encoding="utf-8").read())
    ref, ref_t = [], []
    for t, text in ref_lines:
        for w in norm_words(text):
            ref.append(w); ref_t.append(t)
    hyp, hyp_t = [], []
    for s in segs:
        for w in norm_words(s["text"]):
            hyp.append(w); hyp_t.append(s["interval"]["start_ms"])
    ref, ref_t = merge_names(ref, ref_t)
    hyp, hyp_t = merge_names(hyp, hyp_t)
    ops = align(ref, hyp)
    c = Counter(o[0] for o in ops)
    wer = (c["sub"] + c["del"] + c["ins"]) / max(1, len(ref))
    print(f"reference words {len(ref)}, ours {len(hyp)}")
    print(f"disagreement (WER vs reference) {wer:.1%}: {c['sub']} substitutions, {c['del']} missing in ours, {c['ins']} extra in ours")
    # per minute (by reference time)
    per = {}
    for o, i, j in ops:
        t = ref_t[i] if i is not None else (hyp_t[j] if j is not None else 0)
        k = t // 60000
        a = per.setdefault(k, Counter())
        a["n"] += i is not None
        a["err"] += o != "ok"
    print("per minute (ref words, disagreement):", " ".join(f"{k}:{v['err'] / max(1, v['n']):.0%}" for k, v in sorted(per.items())))
    # disagreement spans, with context, for human judgement
    spans, cur = [], None
    for k, (o, i, j) in enumerate(ops):
        if o != "ok":
            if cur is None:
                cur = [k, k]
            else:
                cur[1] = k
        elif cur is not None and k - cur[1] > 1:
            spans.append(cur); cur = None
    if cur:
        spans.append(cur)
    report = []
    for a, b in spans:
        r = " ".join(ref[i] for o, i, j in ops[a:b + 1] if i is not None)
        h = " ".join(hyp[j] for o, i, j in ops[a:b + 1] if j is not None)
        i0 = next((i for o, i, j in ops[a:b + 1] if i is not None), None)
        j0 = next((j for o, i, j in ops[a:b + 1] if j is not None), None)
        t = ref_t[i0] if i0 is not None else hyp_t[j0]
        report.append({"t_ms": t, "reference": r, "ours": h})
    for x in report:
        print(f"  {x['t_ms'] // 60000}:{x['t_ms'] // 1000 % 60:02d}  ref: {x['reference']!r:45} ours: {x['ours']!r}")
    if "--out" in sys.argv:
        json.dump({"wer_vs_reference": wer, "counts": dict(c), "ref_words": len(ref), "spans": report},
                  open(sys.argv[sys.argv.index("--out") + 1], "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
