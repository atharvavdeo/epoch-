"""Regression tests for faults found on the first real Cerebras run (2026-10-03)."""

from pipeline.reasoning.candidates import CandidateBuilder
from pipeline.reasoning.llm import LLMError
from pipeline.reasoning.narrative import PacedLLM, derive_structure, salvage_decisions


def _chunks(n=5, size=60_000):
    return {f"P{i + 1:02d}": {"chunk_id": f"P{i + 1:02d}", "start_ms": i * size, "end_ms": (i + 1) * size, "segment_ids": []}
            for i in range(n)}


def test_payoff_time_is_first_delivery_not_final_summary():
    s = {"title_obligations": [{"obligation": "explain X", "title_quote": "X"}],
         "hook": {"kind": "none", "chunk": "P01", "quote": ""}, "first_substance_chunk": "P01", "chapters": [],
         "promise_ledger": [{"obligation_index": 0, "setup_chunks": ["P01"], "partial_chunks": ["P04", "P02"],
                             "fulfilled_chunks": ["P05"], "status": "fulfilled", "note": ""}],
         "spans": []}
    st = derive_structure(s, _chunks(), {}, 300_000)
    p = st["promises"][0]
    assert p["first_fulfil_ms"] == 60_000                      # P02 starts delivering, not P05's summary
    assert p["first_delivery_interval"] == {"start_ms": 60_000, "end_ms": 120_000}
    assert p["fulfil_interval"] == {"start_ms": 240_000, "end_ms": 300_000}  # UI marker keeps full fulfilment


def test_same_type_same_interval_candidates_merge():
    b = CandidateBuilder({"duration_ms": 100_000, "book": None})
    b.add("delayed_payoff", 0, 50_000, [("ev_a", "a")], [], "promise 1")
    b.add("delayed_payoff", 0, 50_000, [("ev_a", "a"), ("ev_b", "b")], [], "promise 2")
    b.add("delayed_payoff", 0, 40_000, [("ev_c", "c")], [], "promise 3")
    assert len(b.items) == 2
    assert [e[0] for e in b.items[0]["evidence"]] == ["ev_a", "ev_b"] and "promise 2" in b.items[0]["note"]


def _cand(kid):
    return (kid, {"type": "dead_air", "options": [{"id": "O1", "operation": "cut"}],
                  "_ev_short": [("E01", "x")], "_ev_text": {"E01": "the exact words here"}})


def _dec(kid, quote):
    return {"candidate": kid, "verdict": "accept", "severity": "low", "evidence": ["E01"], "quote": quote,
            "explanation": "e", "counter_explanation": "c", "edit_option": "O1", "proposed_text": "", "edit_rationale": "r"}


def test_one_bad_quote_does_not_discard_batch_mates():
    batch = [_cand("K01"), _cand("K02")]
    kept = salvage_decisions({"decisions": [_dec("K01", "exact words"), _dec("K02", "invented words")]}, batch)
    assert list(kept) == ["K01"]


class _RateLimited:
    def __init__(self, fails, wait):
        self.fails, self.wait, self.calls = fails, wait, 0

    def json_call(self, *a, **kw):
        self.calls += 1
        if self.calls <= self.fails:
            raise LLMError("rate_limited", "HTTP 429", retryable=True, retry_after=self.wait)
        return {"ok": True}


def test_paced_llm_waits_out_retry_after_within_bounds():
    slept, logs = [], []
    llm = PacedLLM(_RateLimited(2, 52.0), logs.append, sleep=slept.append)
    assert llm.json_call() == {"ok": True} and len(slept) == 2 and len(logs) == 2


def test_paced_llm_gives_up_past_total_budget():
    llm = PacedLLM(_RateLimited(10, 100.0), lambda m: None, limits={"max_single_s": 120, "max_total_s": 250},
                   sleep=lambda s: None)
    try:
        llm.json_call()
        raise AssertionError("expected LLMError")
    except LLMError as exc:
        assert exc.code == "rate_limited"


def test_loud_non_speech_gap_is_not_dead_air():
    from pipeline.reasoning.candidates import find_pauses
    vad = [{"start_ms": 0, "end_ms": 10_000}, {"start_ms": 20_000, "end_ms": 30_000}, {"start_ms": 40_000, "end_ms": 50_000}]
    t = list(range(0, 50_000, 500))
    # speech at -18 dBFS; 10-20 s is music at -18 dBFS; 30-40 s is quiet at -60 dBFS
    db = [-60.0 if 30_000 <= x < 40_000 else -18.0 for x in t]
    gaps = find_pauses(vad, [], 50_000, {"t_ms": t, "dbfs": db})
    assert [(g["start_ms"], g["end_ms"]) for g in gaps] == [(30_000, 40_000)]
    # without an envelope the gap is unknown loudness: kept, labelled VAD-only
    assert len(find_pauses(vad, [], 50_000, None)) == 2


def test_structure_with_bad_span_is_salvaged_not_failed(monkeypatch):
    from pipeline.reasoning.narrative import validate_structure
    obj = {"title_obligations": [{"obligation": "explain X", "title_quote": "X"}],
           "hook": {"kind": "none", "chunk": "P01", "quote": ""}, "first_substance_chunk": "P01",
           "chapters": [{"start_chunk": "P01", "end_chunk": "P01", "label": "a", "role": "main_content"}],
           "promise_ledger": [], "spans": [{"chunk": "P01", "kind": "cta", "quote": "subscribe now", "note": ""},
                                           {"chunk": "P01", "kind": "recap", "quote": "invented text", "note": ""}]}
    errs = validate_structure(obj, ["P01"], {"P01": "please subscribe now"}, "About X")
    assert errs == ["spans[1].quote is not an exact substring of paragraph P01"]
