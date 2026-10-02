"""narrative stage (controller env): structure pass + candidate adjudication.

Calls (TRD §5): 1 structure call over all paragraphs (bounded input) and
<=12 adjudication calls of <=4 candidates each. Each call: strict JSON
schema, then local validation (ids exist, quotes are exact substrings,
options valid); at most one repair call; still invalid -> those candidates
are recorded as unadjudicated and the stage is partial. Issues, edits and
promises are then built deterministically.
"""

from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path

from contracts.common import det_uuid
from contracts.entities import P1_ISSUE_TYPES, ISSUE_TRACK
from pipeline.orchestration.io import read_json, write_json
from pipeline.orchestration.settings import REPO_ROOT
from pipeline.orchestration.stage import StageContext, StageError, StageResult, StageSpec
from pipeline.reasoning.candidates import (
    CandidateBuilder,
    EvidenceBook,
    find_pauses,
    merge_clip_windows,
    mmss,
    speech_rates,
)

PROMPT = REPO_ROOT / "prompts" / "narrative.v3.md"
MAX_CALLS, PER_CALL = 12, 4
INPUT_CHAR_BUDGET = 22_000  # ~8k tokens incl. instructions (TRD §5)
ROLES = ["cold_open", "greeting_intro", "hook", "setup", "main_content", "example_demo", "tangent", "sponsor", "cta",
         "recap", "outro"]
SPAN_KINDS = ["greeting", "cta", "sponsor", "recap", "outro", "viewer_question", "open_loop", "tangent_candidate"]


def _sections() -> dict[str, str]:
    text = PROMPT.read_text(encoding="utf-8")
    secs, cur, buf = {}, None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if cur:
                secs[cur] = "\n".join(buf).strip()
            cur, buf = line[3:].strip(), []
        elif cur:
            buf.append(line)
    secs[cur] = "\n".join(buf).strip()
    return secs


def prompt_sha() -> str:
    return hashlib.sha256(PROMPT.read_bytes()).hexdigest()


def norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s).casefold().split())


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": False}


S = {"type": "string"}
SA = {"type": "array", "items": S}
STRUCTURE_SCHEMA = _obj({
    "title_obligations": {"type": "array", "items": _obj({"obligation": S, "title_quote": S})},
    "hook": _obj({"chunk": S, "quote": S, "kind": {"type": "string", "enum": ["question", "promise", "claim", "teaser", "story", "none"]}}),
    "first_substance_chunk": S,
    "chapters": {"type": "array", "items": _obj({"start_chunk": S, "end_chunk": S, "label": S,
                                                  "role": {"type": "string", "enum": ROLES}})},
    "promise_ledger": {"type": "array", "items": _obj({"obligation_index": {"type": "integer"}, "setup_chunks": SA,
                                                        "partial_chunks": SA, "fulfilled_chunks": SA,
                                                        "status": {"type": "string", "enum": ["unaddressed", "partial", "fulfilled", "uncertain"]},
                                                        "note": S})},
    "spans": {"type": "array", "items": _obj({"chunk": S, "kind": {"type": "string", "enum": SPAN_KINDS}, "quote": S, "note": S})},
})
ADJ_SCHEMA = _obj({"decisions": {"type": "array", "items": _obj({
    "candidate": S, "verdict": {"type": "string", "enum": ["accept", "dismiss"]},
    "severity": {"type": "string", "enum": ["low", "medium", "high"]}, "evidence": SA, "quote": S,
    "explanation": S, "counter_explanation": S, "edit_option": S, "proposed_text": S, "edit_rationale": S})}})


# ----------------------------------------------------------------- structure

def paragraphs_text(chunks: list[dict]) -> tuple[str, dict[str, str]]:
    """Paragraph listing within the char budget; returns the text actually shown per chunk."""
    total = sum(len(c["text"]) for c in chunks)
    scale = min(1.0, INPUT_CHAR_BUDGET / max(1, total))
    shown, lines = {}, []
    for c in chunks:
        t = c["text"]
        if scale < 1.0:
            words = t.split()
            keep = max(25, int(len(words) * scale))
            t = " ".join(words[:keep]) + (" …" if keep < len(words) else "")
        shown[c["chunk_id"]] = t
        lines.append(f"{c['chunk_id']} [{mmss(c['start_ms'])}-{mmss(c['end_ms'])}] {t}")
    return "\n".join(lines), shown


def validate_structure(obj: dict, chunk_ids: list[str], shown: dict[str, str], title: str) -> list[str]:
    errs = []
    ids = set(chunk_ids)

    def chk(cid, where):
        if cid not in ids:
            errs.append(f"{where}: unknown paragraph id '{cid}'")

    for i, o in enumerate(obj["title_obligations"]):
        if not o["title_quote"].strip() or norm(o["title_quote"]) not in norm(title):
            errs.append(f"title_obligations[{i}].title_quote must be copied exactly from the TITLE")
    if not obj["title_obligations"]:
        errs.append("title_obligations must contain at least one obligation")
    h = obj["hook"]
    chk(h["chunk"], "hook.chunk")
    if h["quote"] and h["chunk"] in shown and norm(h["quote"]) not in norm(shown[h["chunk"]]):
        errs.append("hook.quote is not an exact substring of its paragraph")
    chk(obj["first_substance_chunk"], "first_substance_chunk")
    for i, ch in enumerate(obj["chapters"]):
        chk(ch["start_chunk"], f"chapters[{i}].start_chunk")
        chk(ch["end_chunk"], f"chapters[{i}].end_chunk")
    for i, p in enumerate(obj["promise_ledger"]):
        if not (0 <= p["obligation_index"] < len(obj["title_obligations"])):
            errs.append(f"promise_ledger[{i}].obligation_index out of range")
        for k in ("setup_chunks", "partial_chunks", "fulfilled_chunks"):
            for cid in p[k]:
                chk(cid, f"promise_ledger[{i}].{k}")
        if p["status"] == "fulfilled" and not p["fulfilled_chunks"]:
            errs.append(f"promise_ledger[{i}] is fulfilled but cites no fulfilled_chunks")
    for i, sp in enumerate(obj["spans"]):
        chk(sp["chunk"], f"spans[{i}].chunk")
        if sp["chunk"] in shown and (not sp["quote"].strip() or norm(sp["quote"]) not in norm(shown[sp["chunk"]])):
            errs.append(f"spans[{i}].quote is not an exact substring of paragraph {sp['chunk']}")
    return errs


def locate_quote(quote: str, segs: list[dict]) -> dict | None:
    q = norm(quote)
    for s in segs:
        if q and q in norm(s["text"]):
            return s
    return None


# -------------------------------------------------------------- adjudication

def candidates_text(batch: list[tuple[str, dict]]) -> str:
    out = []
    for kid, c in batch:
        lines = [f"{kid}: type={c['type']} | time {mmss(c['interval']['start_ms'])}-{mmss(c['interval']['end_ms'])} | {c['note']}"]
        for eid_short, (_, text) in c["_ev_short"]:
            lines.append(f"   {eid_short}: {text}")
        for o in c["options"]:
            lines.append(f"   option {o['id']}: {o['operation']} - {o['desc']}")
        out.append("\n".join(lines))
    return "\n\n".join(out)


REWRITE_MIN_RETENTION = 0.4
RETENTION_ERR = "of the original passage's content words"


def content_retention(original: str, proposed: str) -> float | None:
    """Share of the original's distinct content words that survive in the rewrite (None if nothing to compare)."""
    from pipeline.reasoning.candidates import _STOP
    import re

    tok = lambda t: {w for w in re.findall(r"[^\W_]+", t.lower()) if w not in _STOP and len(w) > 2}  # noqa: E731
    o = tok(original)
    return len(o & tok(proposed)) / len(o) if len(o) >= 8 else None


def validate_adjudication(obj: dict, batch: list[tuple[str, dict]]) -> list[str]:
    errs = []
    by = {k: c for k, c in batch}
    seen = set()
    for i, d in enumerate(obj["decisions"]):
        c = by.get(d["candidate"])
        if c is None:
            errs.append(f"decisions[{i}].candidate '{d['candidate']}' is not one of {list(by)}")
            continue
        seen.add(d["candidate"])
        short = {s for s, _ in c["_ev_short"]}
        bad = [e for e in d["evidence"] if e not in short]
        if bad:
            errs.append(f"{d['candidate']}: evidence {bad} not listed for this candidate")
        if not d["evidence"]:
            errs.append(f"{d['candidate']}: cite at least one evidence id")
        if d["quote"].strip():
            texts = [c["_ev_text"][e] for e in d["evidence"] if e in c["_ev_text"]]
            if not any(norm(d["quote"]) in norm(t) for t in texts):
                errs.append(f"{d['candidate']}: quote is not an exact substring of a cited evidence item")
        opts = {o["id"]: o for o in c["options"]}
        if d["edit_option"] not in opts:
            errs.append(f"{d['candidate']}: edit_option must be one of {list(opts)}")
        elif opts[d["edit_option"]]["operation"] in ("rewrite",) and d["verdict"] == "accept" and not d["proposed_text"].strip():
            errs.append(f"{d['candidate']}: rewrite option needs proposed_text")
        if (d["verdict"] == "accept" and d["edit_option"] in opts and opts[d["edit_option"]]["operation"] == "rewrite"
                and d["proposed_text"].strip()):
            kept = content_retention(c.get("_opt_text", {}).get(d["edit_option"], ""), d["proposed_text"])
            if kept is not None and kept < REWRITE_MIN_RETENTION:
                errs.append(f"{d['candidate']}: proposed_text keeps only {kept:.0%} of the original passage's content words; "
                            "a rewrite may remove repetition or filler but must keep every point, example and question")
        if d["verdict"] == "accept" and (not d["explanation"].strip() or not d["counter_explanation"].strip()):
            errs.append(f"{d['candidate']}: explanation and counter_explanation are required")
    missing = set(by) - seen
    if missing:
        errs.append(f"missing decisions for {sorted(missing)}")
    return errs


RATE_WAIT = {"max_single_s": 120.0, "max_total_s": 300.0}


class PacedLLM:
    """Waits out provider rate limits (HTTP 429 + Retry-After) at stage level.

    The per-call 45 s deadline stays as specified; a 429 is the provider saying
    when to come back, not a failed answer. Waits are bounded per call and in
    total, and every wait is logged.
    """

    def __init__(self, llm, log, limits: dict = RATE_WAIT, sleep=None):
        import time

        self.llm, self.log, self.limits, self.waited = llm, log, limits, 0.0
        self._sleep = sleep or time.sleep

    def json_call(self, *a, **kw):
        from pipeline.reasoning.llm import LLMError

        while True:
            try:
                return self.llm.json_call(*a, **kw)
            except LLMError as exc:
                w = getattr(exc, "retry_after", None)
                if (exc.code != "rate_limited" or w is None or w > self.limits["max_single_s"]
                        or self.waited + w > self.limits["max_total_s"]):
                    raise
                self.log(f"rate limited by provider; waiting {w:.0f}s as instructed (total waited {self.waited + w:.0f}s)")
                self._sleep(w + 1)
                self.waited += w

    def __getattr__(self, name):
        return getattr(self.llm, name)


def call_with_repair(llm, secs: dict, user: str, name: str, schema: dict, validator, budget: dict,
                     max_tokens: int) -> tuple[dict | None, list[str], bool, dict | None]:
    """Returns (valid object | None, errors, repaired, last object received even if invalid)."""
    from pipeline.reasoning.llm import LLMError

    try:
        obj = llm.json_call(secs["SYSTEM"], user, name, schema, max_tokens=max_tokens)
    except LLMError as exc:
        return None, [f"{exc.code}: {exc}"], False, None
    errs = validator(obj)
    if not errs:
        return obj, [], False, obj
    if budget["repairs"] <= 0:
        return None, errs, False, obj
    budget["repairs"] -= 1
    rep = user + "\n\n" + secs["REPAIR"].replace("{errors}", "\n".join(f"- {e}" for e in errs[:10]))
    try:
        obj2 = llm.json_call(secs["SYSTEM"], rep, name, schema, max_tokens=max_tokens)
    except LLMError as exc:
        return None, errs + [f"repair failed: {exc.code}"], True, obj
    errs2 = validator(obj2)
    return (obj2, [], True, obj2) if not errs2 else (None, errs2, True, obj2)


def salvage_decisions(obj: dict | None, batch: list[tuple[str, dict]]) -> dict:
    """Keep decisions that pass the full validator on their own, so one bad quote doesn't
    discard the other candidates in its batch."""
    if not obj:
        return {}
    out = {}
    for d in obj["decisions"]:
        k = d["candidate"]
        single = [(kk, c) for kk, c in batch if kk == k]
        if not single or k in out:
            continue
        errs = validate_adjudication({"decisions": [d]}, single)
        if not errs:
            out[k] = d
        elif all(RETENTION_ERR in e for e in errs):
            # diagnosis is valid, the edit is not: keep the finding, drop the destructive edit
            out[k] = {**d, "_unsafe_edit": True}
    return out


# --------------------------------------------------------------------- stage

def narrative_spec(source: dict) -> StageSpec:
    return StageSpec(name="narrative", version="9", deps=("align", "embed", "probe", "video_scan", "audio"),
                     optional_deps=("asr", "visual"),
                     config={"max_calls": MAX_CALLS, "per_call": PER_CALL, "char_budget": INPUT_CHAR_BUDGET,
                             "thresholds": {"intro_ms": 20000, "payoff_ms": 60000, "pause_ms": 2000, "static_shot_ms": 15000,
                                            "rushed": "wpm > max(190, 1.25*median)"}},
                     extra={"title": source["project"]["title"], "category": source["project"]["category"],
                            "language": source["project"]["declared_language"], "prompt_sha256": prompt_sha(),
                            "llm_preference": ["gpt-oss-120b", "qwen-3.8-27b"]})


def narrative_stage(source: dict, llm_factory=None):
    def fn(ctx: StageContext) -> StageResult:
        from pipeline.reasoning.llm import CerebrasClient, LLMError

        secs = _sections()
        title, cat, lang = (source["project"][k] for k in ("title", "category", "declared_language"))
        probe = read_json(ctx.dep("probe").path("probe.json"))
        T = probe["duration_ms"]
        tr = read_json(ctx.dep("align").path("transcript.json"))
        segments = tr["segments"]
        emb = read_json(ctx.dep("embed").path("chunks.json"))
        chunks, pairs = emb["chunks"], emb["pairs"]
        if not chunks:
            raise StageError("no_transcript", "transcript is empty; narrative analysis needs speech")
        chunk_by_id = {c["chunk_id"]: c for c in chunks}
        seg_by_id = {s["segment_id"]: s for s in segments}
        vs = ctx.dep("video_scan")
        shots, filters = read_json(vs.path("shots.json")), read_json(vs.path("filters.json"))
        audio = read_json(ctx.dep("audio").path("audio.json"))
        vad = read_json(ctx.deps["asr"].path("vad.json"))["speech"] if "asr" in ctx.deps else None
        visual = read_json(ctx.deps["visual"].path("visual.json")) if "visual" in ctx.deps else None

        llm = PacedLLM(llm_factory() if llm_factory else CerebrasClient.from_env(), ctx.log)
        try:
            probe_info = llm.probe()
        except LLMError as exc:
            raise StageError(exc.code, str(exc), retryable=exc.retryable,
                             recommended_action="check CEREBRAS_API_KEY / network; extraction results stay valid") from exc
        ctx.log(f"LLM {probe_info['model']} ({probe_info['structured_outputs']})")
        budget = {"repairs": 8}

        # ---- structure pass
        para_text, shown = paragraphs_text(chunks)
        cuts_per_min = round(len(shots) / (T / 60000), 1)
        measured = (f"{len(shots)} shots ({cuts_per_min}/min); speech present "
                    f"{'unknown' if vad is None else str(round(100 * sum(v['end_ms'] - v['start_ms'] for v in vad) / T)) + '%'}; "
                    f"visual analysis {'available' if visual else 'not available'}")
        user = (secs["STRUCTURE"].replace("{title}", title).replace("{category}", cat).replace("{language}", lang)
                .replace("{duration}", mmss(T)).replace("{measured}", measured).replace("{paragraphs}", para_text))
        validate_s = lambda o: validate_structure(o, [c["chunk_id"] for c in chunks], shown, title)  # noqa: E731
        structure, s_errs, s_rep, s_last = call_with_repair(llm, secs, user, "structure", STRUCTURE_SCHEMA, validate_s,
                                                            budget, 6000)
        dropped_spans = []
        if structure is None and s_last is not None and s_errs and all(e.startswith("spans[") for e in s_errs):
            # spans are optional annotations: drop the ones with unverifiable quotes instead of failing the stage
            bad = {int(e[len("spans["):e.index("]")]) for e in s_errs}
            dropped_spans = [sp for i, sp in enumerate(s_last["spans"]) if i in bad]
            candidate = {**s_last, "spans": [sp for i, sp in enumerate(s_last["spans"]) if i not in bad]}
            if not validate_s(candidate):
                structure = candidate
                ctx.log(f"structure: dropped {len(dropped_spans)} span(s) whose quotes were not exact")
        if structure is None:
            raise StageError("structure_invalid", f"structure pass failed validation: {s_errs[:3]}")
        st = derive_structure(structure, chunk_by_id, seg_by_id, T)
        ctx.log(f"structure: {len(st['promises'])} title obligations, substance at "
                f"{mmss(st['first_substance_ms']) if st['first_substance_ms'] is not None else '?'}, {len(st['spans'])} spans")

        # ---- candidates
        book = EvidenceBook(source["asset_id"])
        obs = (visual or {}).get("observations", [])
        obs_ev = {}
        for e in (visual or {}).get("evidence", []):
            if e["kind"] == "observation":
                obs_ev[e["ref_id"]] = e["evidence_id"]
        rates = speech_rates(chunks, {}, seg_by_id)
        rushed = sorted([r for r in rates if r["wpm"] > max(190, 1.25 * r["median"])], key=lambda r: -r["wpm"])
        long_static = [s for s in shots if s["end_ms"] - s["start_ms"] >= 15_000 and (s["metrics"].get("motion_mean") or 0) < 0.02]
        builder = CandidateBuilder({
            "book": book, "segments": segments, "chunk_by_id": chunk_by_id, "seg_by_id": seg_by_id, "duration_ms": T,
            "structure": st, "pairs": pairs, "pauses": find_pauses(vad, audio.get("silence", []), T, audio.get("rms")), "rushed": rushed, "words": tr.get("words", []),
            "clip_windows": merge_clip_windows(audio.get("clipping_windows", [])),
            "true_peak": (audio.get("loudness") or {}).get("true_peak_dbfs"), "black": filters["black"],
            "observations": obs, "obs_ev": obs_ev, "long_static_shots": long_static,
            "last_chunk_iv": {"start_ms": chunks[-1]["start_ms"], "end_ms": chunks[-1]["end_ms"]},
        })
        cands = [c for c in builder.build() if c["type"] in P1_ISSUE_TYPES][: MAX_CALLS * PER_CALL]
        for i, c in enumerate(cands):
            c["kid"] = f"K{i + 1:02d}"
            c["_ev_short"] = [(f"E{j + 1:02d}", ev) for j, ev in enumerate(c["evidence"])]
            c["_ev_text"] = {s: ev[1] for s, ev in c["_ev_short"]}
            c["_opt_text"] = {o["id"]: " ".join(sg["text"] for sg in segments if o.get("interval")
                                                and sg["interval"]["end_ms"] > o["interval"]["start_ms"]
                                                and sg["interval"]["start_ms"] < o["interval"]["end_ms"])
                              for o in c["options"]}
        obs_by_ev = {v: k for k, v in obs_ev.items()}
        ctx.log(f"{len(cands)} candidates: " + ", ".join(f"{t}={sum(c['type'] == t for c in cands)}"
                                                       for t in sorted({c['type'] for c in cands})))

        # ---- adjudication
        decisions, unadjudicated = {}, []
        struct_summary = (f"title obligations: {[p['obligation'] for p in st['promises']]}; hook at "
                          f"{mmss(st['hook_ms']) if st['hook_ms'] is not None else 'none'}; substance starts "
                          f"{mmss(st['first_substance_ms']) if st['first_substance_ms'] is not None else '?'}; chapters: "
                          + "; ".join(f"{c['label']} ({c['role']}) {mmss(c['start_ms'])}" for c in st["chapters"][:12]))
        for b in range(0, len(cands), PER_CALL):
            batch = [(c["kid"], c) for c in cands[b:b + PER_CALL]]
            user = (secs["ADJUDICATE"].replace("{title}", title).replace("{category}", cat).replace("{duration}", mmss(T))
                    .replace("{structure}", struct_summary).replace("{candidates}", candidates_text(batch)))
            obj, errs, _, last = call_with_repair(llm, secs, user, "adjudication", ADJ_SCHEMA,
                                                  lambda o, batch=batch: validate_adjudication(o, batch), budget, 4000)
            if obj is None:
                kept = salvage_decisions(last, batch)
                decisions.update(kept)
                unadjudicated += [{"candidate": k, "type": c["type"],
                                   "errors": [e for e in errs if e.startswith(f"{k}:")][:3] or errs[:3]}
                                  for k, c in batch if k not in kept]
                continue
            for d in obj["decisions"]:
                decisions[d["candidate"]] = d

        issues, suggestions, dismissed = build_issues(cands, decisions, book, obs_by_ev, source, segments)
        promises = build_promises(st, chunk_by_id, seg_by_id, book)
        signals = narrative_signals(st, pairs, chunk_by_id, rates, book)
        evidence = [{k: v for k, v in e.items() if not k.startswith("_")} for e in book.records.values()]
        write_json(ctx.out / "narrative.json", {
            "structure_raw": structure, "structure_dropped_spans": dropped_spans, "structure": st, "issues": issues, "suggestions": suggestions,
            "promises": promises, "signals": signals, "evidence": evidence, "dismissed": dismissed,
            "unadjudicated": unadjudicated, "candidates": [{k: v for k, v in c.items() if not k.startswith("_")} for c in cands],
            "llm": {**llm.usage(), "probe": probe_info, "prompt_sha256": prompt_sha(), "repairs_used": 8 - budget["repairs"],
                    "structure_repaired": s_rep}})
        ctx.log(f"issues accepted {len(issues)}, dismissed {len(dismissed)}, unadjudicated {len(unadjudicated)}; "
                f"LLM {llm.usage()}")
        return StageResult("partial" if unadjudicated else "complete",
                           {"issues": len(issues), "dismissed": len(dismissed), "unadjudicated": len(unadjudicated)})

    return fn


def derive_structure(s: dict, chunk_by_id: dict, seg_by_id: dict, T: int) -> dict:
    def start(cid):
        return chunk_by_id[cid]["start_ms"] if cid in chunk_by_id else None

    def span_iv(cids):
        cs = [chunk_by_id[c] for c in cids if c in chunk_by_id]
        return {"start_ms": min(c["start_ms"] for c in cs), "end_ms": max(c["end_ms"] for c in cs)} if cs else None

    def quote_iv(cid, quote):
        ch = chunk_by_id.get(cid)
        if not ch:
            return None
        segs = [seg_by_id[x] for x in ch["segment_ids"]]
        seg = locate_quote(quote, segs) if quote else None
        return dict(seg["interval"]) if seg else {"start_ms": ch["start_ms"], "end_ms": ch["end_ms"]}

    hook_ms = hook_end_ms = None
    if s["hook"]["kind"] != "none":
        iv = quote_iv(s["hook"]["chunk"], s["hook"]["quote"])
        hook_ms = iv["start_ms"] if iv else None
        hook_end_ms = iv["end_ms"] if iv else None
    first_sub = start(s["first_substance_chunk"])
    promises = []
    for i, o in enumerate(s["title_obligations"]):
        led = next((p for p in s["promise_ledger"] if p["obligation_index"] == i), None)
        status = led["status"] if led else "uncertain"
        f_iv = span_iv(led["fulfilled_chunks"][:1]) if led and led["fulfilled_chunks"] else None
        p_iv = span_iv(led["partial_chunks"]) if led and led["partial_chunks"] else None
        # Payoff timing = the first paragraph that delivers on the promise at all (partial or full).
        # A video that delivers progressively and summarises at the end has no delayed payoff.
        delivering = sorted((c for c in (led["partial_chunks"] + led["fulfilled_chunks"] if led else []) if c in chunk_by_id),
                            key=start)
        d_iv = span_iv(delivering[:1])
        first_fulfil = d_iv["start_ms"] if d_iv and status in ("fulfilled", "partial") else None
        promises.append({"index": i, "obligation": o["obligation"], "title_quote": o["title_quote"], "status": status,
                         "setup_chunks": led["setup_chunks"] if led else [], "partial_chunks": led["partial_chunks"] if led else [],
                         "fulfilled_chunks": led["fulfilled_chunks"] if led else [], "note": led["note"] if led else "",
                         "setup_ms": start(led["setup_chunks"][0]) if led and led["setup_chunks"] else None,
                         "first_fulfil_ms": first_fulfil, "first_delivery_interval": d_iv,
                         "fulfil_interval": f_iv or p_iv, "partial_interval": p_iv})
    chapters = []
    for c in s["chapters"]:
        iv = span_iv([c["start_chunk"], c["end_chunk"]])
        if iv:
            chapters.append({"label": c["label"], "role": c["role"], **iv})
    spans = []
    for sp in s["spans"]:
        iv = quote_iv(sp["chunk"], sp["quote"])
        if iv:
            spans.append({"kind": sp["kind"], "quote": sp["quote"], "note": sp["note"], "chunk": sp["chunk"], "interval": iv})
    greet = [sp for sp in spans if sp["kind"] == "greeting"]
    return {"hook_ms": hook_ms, "hook_end_ms": hook_end_ms, "hook": s["hook"], "first_substance_ms": first_sub, "promises": promises,
            "chapters": chapters, "spans": spans, "intro_cut_start_ms": 0 if not greet else 0}


def _mechanism(op: str, iv: dict, dest: int | None) -> str:
    d = (iv["end_ms"] - iv["start_ms"]) / 1000
    if op == "cut":
        return f"Removes {d:.1f} s ({mmss(iv['start_ms'])}-{mmss(iv['end_ms'])})."
    if op == "move" and dest is not None:
        delta = (iv["start_ms"] - dest) / 1000
        return (f"Brings {mmss(iv['start_ms'])}-{mmss(iv['end_ms'])} {abs(delta):.1f} s "
                + ("earlier." if delta > 0 else "later."))
    return "Effect on retention unknown until the edited video is reanalysed."


def build_issues(cands, decisions, book, obs_by_ev, source, segments):
    issues, suggestions, dismissed = [], [], []
    for c in cands:
        d = decisions.get(c["kid"])
        if d is None:
            continue
        if d["verdict"] == "dismiss":
            dismissed.append({"candidate": c["kid"], "type": c["type"], "interval": c["interval"], "reason": d["explanation"],
                              "counter_explanation": d["counter_explanation"]})
            continue
        eids = [c["_ev_short"][int(e[1:]) - 1][1][0] for e in d["evidence"]]
        kinds = {book.records[e]["kind"] if e in book.records else "observation" for e in eids}
        modal = set()
        for e in eids:
            rec = book.records.get(e)
            if rec is None:
                modal.add("visual")
            elif rec["kind"] == "transcript":
                modal.add("speech")
            elif rec["provenance_stage_id"] == "audio":
                modal.add("audio")
            else:
                modal.add("visual")
        # quote recorded on the transcript evidence it came from (must equal a source substring)
        if d["quote"].strip():
            for e in eids:
                rec = book.records.get(e)
                # Evidence.quote must be a literal source substring; otherwise it stays only in the explanation.
                if rec and rec["kind"] == "transcript" and d["quote"] in rec["_text"]:
                    rec["quote"] = d["quote"]
                    break
        precise = any((book.records.get(e) or {}).get("kind") in ("transcript", "signal") for e in eids)
        status = "provisional" if (c["absence"] or not precise or source["kind"] == "script") else "supported"
        iid = det_uuid("issue", source["sha256"], c["type"], c["interval"]["start_ms"], c["interval"]["end_ms"])
        opt = next(o for o in c["options"] if o["id"] == d["edit_option"])
        sid = None if d.get("_unsafe_edit") else det_uuid("suggestion", iid, opt["id"])
        op = opt["operation"]
        dest = opt.get("destination_ms")
        src_iv = opt.get("interval")
        if op == "insert_visual" and dest is None:
            dest = src_iv["start_ms"]
        if sid is not None:
            suggestions.append({"suggestion_id": sid, "issue_ids": [iid], "operation": op, "source_interval": src_iv,
                                "destination_ms": dest if op in ("move", "insert_visual") else None,
                                "proposed_text": d["proposed_text"].strip() or None if op in ("rewrite", "insert_visual") else None,
                                "rationale": (_mechanism(op, src_iv, dest) + " " + d["edit_rationale"]).strip()[:2000],
                                "prerequisites": [], "requires_reanalysis": op != "cut"})
        issues.append({"issue_id": iid, "type": c["type"], "affected_interval": c["interval"],
                       "modality_tags": sorted(modal) or ["speech"], "risk_track": ISSUE_TRACK[c["type"]],
                       "severity": d["severity"], "evidence_status": status, "evidence_ids": eids,
                       "explanation": d["explanation"][:2000], "counter_explanation": d["counter_explanation"][:2000],
                       "suggested_edit_ids": [sid] if sid else [], "review_status": "open",
                       "cause_group_id": det_uuid("cause", c["type"], c["interval"]["start_ms"], c["interval"]["end_ms"]),
                       "comparison_intervals": [c["comparison"]] if c.get("comparison") else None, "review_reason": None,
                       "_kinds": sorted(kinds), "_candidate": c["kid"]})
    # same type + overlapping intervals share one cause group (aggregation takes the max, never the sum)
    issues.sort(key=lambda i: (i["type"], i["affected_interval"]["start_ms"]))
    merged: list[dict] = []
    for i in issues:
        m = merged[-1] if merged else None
        if m and m["type"] == i["type"] and i["affected_interval"]["start_ms"] < m["affected_interval"]["end_ms"]:
            i["cause_group_id"] = m["cause_group_id"]
        merged.append(i)
    return merged, suggestions, dismissed


def build_promises(st, chunk_by_id, seg_by_id, book):
    out = []
    for p in st["promises"]:
        def evs(cids):
            return [book.transcript(seg_by_id[s]) for c in cids if c in chunk_by_id for s in chunk_by_id[c]["segment_ids"][:2]]

        status = p["status"]
        fulfil_ev = evs(p["fulfilled_chunks"][:1]) if status == "fulfilled" else evs(p["fulfilled_chunks"][:1] + p["partial_chunks"][:1])
        if status == "fulfilled" and not fulfil_ev:
            status = "uncertain"
        out.append({"promise_id": det_uuid("promise", p["obligation"], p["index"]), "title_quote": p["title_quote"],
                    "obligation": p["obligation"][:600], "setup_evidence_ids": evs(p["setup_chunks"][:1]),
                    "fulfilment_evidence_ids": fulfil_ev, "status": status,
                    # for a fulfilled promise, partial_interval marks where delivery begins (when before completion)
                    "partial_interval": p["partial_interval"] if status == "partial" else (
                        p["first_delivery_interval"] if status == "fulfilled" and p.get("first_delivery_interval")
                        and p["first_delivery_interval"]["start_ms"] < p["fulfil_interval"]["start_ms"] else None),
                    "fulfilled_interval": p["fulfil_interval"] if status == "fulfilled" else None})
    return out


def narrative_signals(st, pairs, chunk_by_id, rates, book):
    sig = []

    def add(feature, name, iv, value, unit="label", validity="estimated", method="llm_structure_pass"):
        sig.append({"signal_id": det_uuid("signal", feature, name, iv["start_ms"], iv["end_ms"], str(value)[:40]),
                    "feature_id": feature, "interval": iv, "modality": "speech", "name": name, "value": value,
                    "unit": unit, "method": method, "evidence_ids": [], "validity": validity, "unknown_reason": None})

    for c in st["chapters"]:
        add("F61", "chapter", {"start_ms": c["start_ms"], "end_ms": c["end_ms"]}, {"label": c["label"], "role": c["role"]})
    kind_feature = {"greeting": "F59", "cta": "F55", "sponsor": "F62", "recap": "F63", "outro": "F64",
                    "viewer_question": "F53", "open_loop": "F54", "tangent_candidate": "F51"}
    for sp in st["spans"]:
        add(kind_feature[sp["kind"]], sp["kind"], sp["interval"], {"quote": sp["quote"][:300], "note": sp["note"][:300]})
    if st["hook_ms"] is not None:
        add("F48", "hook", {"start_ms": st["hook_ms"], "end_ms": st["hook_ms"] + 1000}, {"kind": st["hook"]["kind"],
                                                                                          "quote": st["hook"]["quote"][:300]})
    if st["first_substance_ms"] is not None:
        add("F59", "time_to_substance", {"start_ms": 0, "end_ms": max(1, st["first_substance_ms"])},
            st["first_substance_ms"], unit="ms")
    for p in pairs:
        e, l = chunk_by_id[p["earlier"]], chunk_by_id[p["later"]]
        add("F50", "similar_passage", {"start_ms": l["start_ms"], "end_ms": l["end_ms"]},
            {"cosine": p["cosine"], "earlier": {"start_ms": e["start_ms"], "end_ms": e["end_ms"]}}, unit="cosine",
            validity="measured", method="multilingual-e5-base passage embeddings")
    for r in rates:
        ch = chunk_by_id[r["chunk_id"]]
        add("F40", "speech_rate", {"start_ms": ch["start_ms"], "end_ms": ch["end_ms"]}, r["wpm"], unit="words/min",
            validity="measured" if r["precision"] == "word" else "estimated", method="asr words / segment speech time")
    return sig
