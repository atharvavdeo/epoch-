"""Transcript relations (stdlib only, deterministic): how the parts of the narration relate to each other.

Measured from the transcript text and timing, never from an LLM:
- question -> answer gaps: when a question is asked and where its answer starts (or that it never comes);
- abstract vs concrete: per-sentence concreteness, and long abstract stretches with no example;
- term dependency: a named idea used before it is explained;
- cognitive load: long sentences and new-term density per minute;
- structural rhythm: sentence and section lengths, and where the rhythm goes flat.

Every item carries times and the quoted sentences, so the UI can jump to it and a reviewer can check it.
"""

from __future__ import annotations

import re
import statistics

_STOP = set("""a an the and or but if then so of to in on at by for with from as is are was were be been being it its
this that these those there here i you he she we they me him her us them my your his our their what which who whom
whose when where why how not no do does did have has had will would can could should may might must just also very
really than too into out up down over about after before more most some any all each every other such only own same
people person getting want wants need needs look looks time times lot video videos also something anything everything
again once both few many much well even still yet because while until let lets let's i'm you're it's that's don't
going get got make made one two like know think thing things way right now ok okay yeah gonna wanna say said see""".split())

ABSTRACT = set("""concept strategy framework idea principle value approach element process system method factor aspect
quality structure theory mindset psychology importance key level element elements essence pattern dynamic dynamics
nature context potential impact effect effects goal goals purpose sense feeling emotion emotions engagement retention
attention interest experience expectation expectations perception bias trust curiosity""".split())

CONCRETE_PAT = re.compile(r"\b(\d[\d,.]*\s*(%|percent|seconds?|minutes?|hours?|days?|weeks?|years?|million|billion|"
                          r"thousand|k|m|x|times|dollars?|views?|subscribers?)?|\$\d+|for example|for instance|"
                          r"such as|imagine|picture this|let'?s say|here'?s an example|in this video|in his video|"
                          r"like when|like (?:a|an|the)\s+[a-z]+|like how|look at this|take (a look|this))\b", re.I)
QUESTION_START = re.compile(r"^(so |and |but |now )?(how|why|what|which|who|where|when|is|are|does|do|did|can|could|"
                            r"would|should|will)\b", re.I)
DEFINE_PAT = re.compile(r"\b(?:called|known as|referred to as|this is|i call (?:it|this)|which is|that'?s)\s+"
                        r"(?:the |a |an )?[\"“']?([a-z][a-z' -]{3,40}?)[\"”']?(?:[,.;:]|\s+(?:and|which|where|is|it))",
                        re.I)


def _words(t: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", t.lower())


def _cw(t: str) -> set[str]:
    return {w for w in _words(t) if w not in _STOP and len(w) > 2}


def sentences(segments: list[dict]) -> list[dict]:
    """Split segments into sentences, spreading each segment's time over its sentences by word count."""
    out = []
    for s in sorted(segments, key=lambda x: x["interval"]["start_ms"]):
        a, b = s["interval"]["start_ms"], s["interval"]["end_ms"]
        parts = [p.strip() for p in re.split(r"(?<=[.?!])\s+", s["text"].strip()) if p.strip()]
        n = sum(len(p.split()) for p in parts) or 1
        # Whisper sometimes drops casing and punctuation for whole stretches; sentence-based measures are unreliable there
        punct = bool(re.search(r"[.?!A-Z]", s["text"]))
        t = a
        for p in parts:
            d = (b - a) * len(p.split()) / n
            out.append({"start_ms": int(t), "end_ms": int(t + d), "text": p, "punctuated": punct})
            t += d
    # glue sentence fragments that ASR split mid-sentence ("70%, that's what" + "you need.")
    glued: list[dict] = []
    for s in out:
        # unpunctuated ASR output (lower-case runs) stays one sentence per segment: gluing it would merge minutes
        if glued and not re.search(r"[.?!]$", glued[-1]["text"]) and re.search(r"[.?!]", s["text"])                 and len(glued[-1]["text"].split()) + len(s["text"].split()) <= 40:
            glued[-1] = {**glued[-1], "end_ms": s["end_ms"], "text": glued[-1]["text"] + " " + s["text"]}
        else:
            glued.append(s)
    return glued


ANSWER_OPENER = re.compile(r"(?i)^(well|simple|easy|because|here's|the answer|it's simple|basically|so the answer)\b")


def question_answers(sents: list[dict], max_gap_ms: int = 600_000) -> list[dict]:
    """Questions the narrator asks and where the answer starts.

    The answer is the first later sentence (not a question) that shares >= 2 content words with the question,
    or >= 50 % of them for short questions. A gap > 60 s is an open loop: it holds viewers if paid off, and is a
    broken promise if never answered.
    """
    out, asked = [], set()
    seen_before = [" ".join(_words(x["text"])) for x in sents]
    for i, s in enumerate(sents):
        if not s["text"].endswith("?") or len(s["text"].split()) < 4:
            continue
        key = " ".join(_words(s["text"]))
        if key in asked:  # the same question replayed (an intro replay) is not a new question
            continue
        asked.add(key)
        q = _cw(s["text"])
        if len(q) < 2:
            continue
        ans = None
        for j in range(i + 1, len(sents)):
            t = sents[j]
            if t["start_ms"] - s["end_ms"] > max_gap_ms:
                break
            if t["text"].endswith("?"):
                continue
            if seen_before[j] in seen_before[:j]:  # a replayed sentence (intro replay) is not an answer
                continue
            shared = q & _cw(t["text"])
            if len(shared) >= 2 or (len(q) <= 3 and len(shared) >= max(1, len(q) // 2 + 1)):
                ans = (t, sorted(shared))
                break
        # Adjacent answers often paraphrase the question completely ("Yes", or a definition).
        # Retain them as answer candidates, never semantic proof.
        cue = None
        for candidate in sents[i + 1:i + 4]:
            if candidate["start_ms"] - s["end_ms"] > 10_000:
                break
            if candidate["text"].endswith("?"):
                continue
            if re.search(r"^(?:yes|no|exactly|correct|certainly|absolutely|sure)\b|\b(?:means|refers to|defined as|is (?:a|an|the)|are (?:a|an|the))\b", candidate["text"], re.I):
                cue = candidate
                break
        if cue is not None and (ans is None or ans[0]["start_ms"] > cue["start_ms"]):
            ans = (cue, [])
        rhetorical = bool(QUESTION_START.match(s["text"])) is False
        # A statement starting within 3 s of a wh-question is the speaker answering it ("…dull moments? Simple. He'll…"),
        # even when it shares no words with the question.
        nxt = sents[i + 1] if i + 1 < len(sents) else None
        if (ans is None or ans[0]["start_ms"] - s["end_ms"] > 10_000) and nxt is not None and not nxt["text"].endswith("?") \
                and nxt["start_ms"] - s["end_ms"] <= 3_000 and QUESTION_START.match(s["text"]) \
                and (len(nxt["text"].split()) <= 3 or ANSWER_OPENER.match(nxt["text"])):
            ans, cue = (nxt, []), nxt
        gap = (ans[0]["start_ms"] - s["end_ms"]) if ans else None
        if s["start_ms"] < 60_000:  # opening questions frame the whole video; the promise ledger tracks their payoff
            kind = "framing"
        else:
            kind = "no_callback" if ans is None else "immediate" if gap <= 10_000 else "short" if gap <= 60_000 else "open_loop"
        out.append({"question": s, "answer": ans[0] if ans else None, "shared_words": ans[1] if ans else [],
                    "gap_ms": gap, "kind": kind, "rhetorical_form": rhetorical,
                    "answer_detection": "adjacent_answer_cue" if cue is not None and ans and ans[0] is cue else "lexical_overlap" if ans else None})
    return out


def concreteness(sents: list[dict]) -> list[dict]:
    """Per-sentence concreteness in [-1, 1]: concrete markers (numbers, examples, named things) minus abstract nouns."""
    out = []
    for i, s in enumerate(sents):
        w = _words(s["text"])
        if not w:
            continue
        conc = len(CONCRETE_PAT.findall(s["text"]))
        # names mid-sentence (capitalised, not the first word) are concrete referents
        conc += 0 if not s["punctuated"] else len([m for m in re.findall(r"(?<!^)(?<![.?!]\s)\b[A-Z][a-z]+", s["text"]) if m.lower() not in _STOP])
        abst = sum(1 for x in w if x in ABSTRACT)
        score = max(-1.0, min(1.0, (conc - abst) / max(3, len(w) / 6)))
        out.append({**s, "score": round(score, 2), "concrete_markers": conc, "abstract_terms": abst})
    return out


def abstract_stretches(conc: list[dict], min_ms: int = 40_000) -> list[dict]:
    """Runs of sentences with no concrete marker lasting >= 40 s: where a viewer is asked to hold an idea with no example."""
    out, run = [], []
    for s in conc + [{"start_ms": 10 ** 12, "end_ms": 10 ** 12, "concrete_markers": 99, "abstract_terms": 0, "text": ""}]:
        if s["concrete_markers"] == 0 and s.get("punctuated", True):
            run.append(s)
            continue
        if run and run[-1]["end_ms"] - run[0]["start_ms"] >= min_ms and any(x["abstract_terms"] > 0 for x in run):
            out.append({"start_ms": run[0]["start_ms"], "end_ms": run[-1]["end_ms"], "sentences": len(run),
                        "abstract_terms": sum(x["abstract_terms"] for x in run),
                        "quote": " ".join(x["text"] for x in run)[:400]})
        run = []
    return out


def term_dependencies(sents: list[dict]) -> list[dict]:
    """Named ideas ("input bias", "the golden benchmark") used before the sentence that explains them."""
    out = []
    full = [s["text"] for s in sents]
    for i, s in enumerate(sents):
        for m in DEFINE_PAT.finditer(s["text"]):
            term = m.group(1).strip().lower()
            tw = term.split()
            if not 2 <= len(tw) <= 4 or tw[0] in _STOP or all(x in _STOP for x in tw):
                continue
            first_use = next((j for j in range(i) if re.search(rf"\b{re.escape(term)}\b", full[j].lower())), None)
            if first_use is not None:
                out.append({"term": term, "used_at": sents[first_use], "explained_at": s,
                            "gap_ms": s["start_ms"] - sents[first_use]["start_ms"]})
    return out


def cognitive_load(sents: list[dict], words_per_min: float | None = None, window_ms: int = 60_000) -> dict:
    """Long sentences (> 30 words) and new content words per minute, per 60 s window."""
    long_s = [{**s, "words": len(s["text"].split())} for s in sents if len(s["text"].split()) > 30]
    if not sents:
        return {"long_sentences": [], "windows": []}
    end = sents[-1]["end_ms"]
    seen: set[str] = set()
    wins = []
    for a in range(0, end, window_ms):
        inside = [s for s in sents if a <= s["start_ms"] < a + window_ms]
        new = set()
        for s in inside:
            new |= _cw(s["text"]) - seen
        for s in inside:
            seen |= _cw(s["text"])
        lens = [len(s["text"].split()) for s in inside]
        wins.append({"start_ms": a, "end_ms": min(end, a + window_ms), "new_terms": len(new),
                     "mean_sentence_words": round(statistics.mean(lens), 1) if lens else 0.0,
                     "sentences": len(inside)})
    vals = [w["new_terms"] for w in wins if w["sentences"]]
    med = statistics.median(vals) if vals else 0
    for k, w in enumerate(wins):  # the first minute is all new words by definition: never "high"
        w["load"] = "normal" if k == 0 else "high" if med and w["new_terms"] > 1.5 * med else "low" if med and w["new_terms"] < 0.5 * med else "normal"
    return {"long_sentences": long_s, "windows": wins, "median_new_terms_per_min": med}


def rhythm(sents: list[dict], chapters: list[dict] | None = None) -> dict:
    """Sentence-length variation per 30 s window; flat stretches (very even sentence lengths) read as monotone."""
    if not sents:
        return {"windows": [], "flat": []}
    end = sents[-1]["end_ms"]
    wins = []
    for a in range(0, end, 30_000):
        lens = [len(s["text"].split()) for s in sents if a <= s["start_ms"] < a + 30_000 and s["punctuated"]]
        cv = (statistics.pstdev(lens) / statistics.mean(lens)) if len(lens) >= 3 and statistics.mean(lens) else None
        wins.append({"start_ms": a, "end_ms": min(end, a + 30_000), "sentences": len(lens),
                     "variation": round(cv, 2) if cv is not None else None})
    flat = [w for w in wins if w["variation"] is not None and w["variation"] < 0.25]
    sections = []
    for c in chapters or []:
        sections.append({"label": c.get("label", ""), "start_ms": c["start_ms"], "end_ms": c["end_ms"],
                         "duration_s": round((c["end_ms"] - c["start_ms"]) / 1000, 1)})
    return {"windows": wins, "flat": flat, "sections": sections}


def analyse(segments: list[dict], chapters: list[dict] | None = None) -> dict:
    sents = sentences(segments)
    conc = concreteness(sents)
    qa = question_answers(sents)
    return {
        "method": "deterministic text measurements over the transcript; no model, no audience data. An 'answer' is the "
                  "a later lexical callback or an adjacent affirmative/definition cue - an answer candidate, not proof "
                  "that the question was answered well.",
        "sentences": len(sents),
        "questions": qa,
        "concreteness": [{k: c[k] for k in ("start_ms", "end_ms", "score")} for c in conc],
        "abstract_stretches": abstract_stretches(conc),
        "term_dependencies": term_dependencies(sents),
        "cognitive_load": cognitive_load(sents),
        "rhythm": rhythm(sents, chapters),
        "unpunctuated_ms": sum(s["end_ms"] - s["start_ms"] for s in sents if not s["punctuated"]),
        "summary": {
            "questions": len(qa), "answered_immediately": sum(q["kind"] == "immediate" for q in qa),
            "open_loops": sum(q["kind"] == "open_loop" for q in qa), "no_callback": sum(q["kind"] == "no_callback" for q in qa),
            "concrete_share": round(sum(c["concrete_markers"] > 0 for c in conc) / max(1, len(conc)), 2),
        },
    }
