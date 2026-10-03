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


def test_repetition_needs_repeated_wording_and_edits_only_those_sentences():
    from pipeline.reasoning.candidates import repeated_run
    seg = {
        "e1": {"text": "MrBeast has solved YouTube retention, hitting the golden benchmark of 70% retention"},
        "e2": {"text": "But how does MrBeast reach this magic number? To find out I spent a week studying"},
        # later paragraph: a framing line, two replayed sentences, then a NEW transition that must survive
        "l1": {"text": "See if you can spot them in the hook to this video."},
        "l2": {"text": "MrBeast has solved YouTube retention, hitting the golden benchmark of 70% retention"},
        "l3": {"text": "But how does MrBeast reach this magic number? To find out I spent a week studying"},
        "l4": {"text": "As it turns out, it's not one secret, it's three, and it starts with visual variety."},
        # same topic, new wording (the 6:44 case): must not be a repetition at all
        "t1": {"text": "MrBeast starts the body of his video no later than 20 seconds in"},
        "t2": {"text": "the sooner the retention curve levels off the better for him"},
    }
    earlier = {"segment_ids": ["e1", "e2"]}
    assert repeated_run(earlier, {"segment_ids": ["l1", "l2", "l3", "l4"]}, seg) == ["l2", "l3"]
    assert repeated_run(earlier, {"segment_ids": ["t1", "t2"]}, seg) is None


def test_gutting_rewrite_is_rejected():
    from pipeline.reasoning.narrative import REWRITE_MIN_RETENTION, content_retention
    original = ("For MrBeast, jumping into the action usually means starting the first challenge or experience. For a "
                "video like mine, it could mean jumping into the first point. Regardless, MrBeast starts the body of his "
                "video no later than 20 seconds in, because he knows that the sooner the retention curve starts to level "
                "off, the better. The question then becomes, how do you keep the retention curve level? As it turns out, "
                "it's not one secret, it's three, and it starts with visual variety.")
    bad = "Crucially, launch the main content within the first 20 seconds to keep viewers hooked and the retention curve flat."
    assert content_retention(original, bad) < REWRITE_MIN_RETENTION


def test_edit_boundaries_snap_to_sentences():
    words = [{"text": t, "start_ms": i * 100, "end_ms": i * 100 + 90} for i, t in enumerate(
        "See the hook. MrBeast has solved retention, hitting seventy. But how? Next point".split())]
    b = CandidateBuilder({"book": None, "words": words})
    # raw segment boundary: starts at "hitting" (mid-sentence), ends at "But" (mid-sentence)
    iv = b.snap_to_sentences({"start_ms": 700, "end_ms": 950})
    assert iv == {"start_ms": 300, "end_ms": 1090}  # "MrBeast ... seventy. But how?"


def test_word_based_speech_rate_excludes_pauses():
    from pipeline.reasoning.transcript_signals import word_speech_rates
    # 20 words of 200 ms with 100 ms gaps, then a 5 s pause, then 20 more: speaking time 2*(20*200+19*100) = 11.8 s
    words, t = [], 0
    for k in range(40):
        words.append({"segment_id": "s1", "text": "w", "start_ms": t, "end_ms": t + 200})
        t += 300 if k != 19 else 5200
    seg = {"s1": {"text": "w " * 40, "interval": {"start_ms": 0, "end_ms": t}}}
    r = word_speech_rates([{"chunk_id": "P01", "segment_ids": ["s1"]}], words, seg)[0]
    assert r["precision"] == "word" and r["wpm"] == round(40 / (11_800 / 60_000))


def test_fillers_skip_meaningful_words_and_hindi_discourse():
    from pipeline.reasoning.transcript_signals import filler_counts
    seg = {"a": {"text": "Um, you know, I like this. So basically it works.", "interval": {"start_ms": 0, "end_ms": 60_000}},
           "b": {"text": "toh matlab yeh hai", "interval": {"start_ms": 0, "end_ms": 60_000}}}
    en = filler_counts([{"chunk_id": "P1", "segment_ids": ["a"]}], seg)[0]
    assert en["terms"] == {"um": 1, "you know": 1, "basically": 1}
    hi = filler_counts([{"chunk_id": "P2", "segment_ids": ["b"], "language": "hi"}], seg)[0]
    assert hi["count"] == 0


def test_quote_repair_moves_to_neighbouring_paragraph():
    from pipeline.reasoning.narrative import repair_quotes
    shown = {"P1": "there's actually one more secret element that MrBeast applies to every one of his hooks.",
             "P2": "visual variety keeps the curve flat"}
    obj = {"hook": {"kind": "none", "chunk": "P1", "quote": ""},
           "spans": [{"chunk": "P2", "kind": "open_loop", "quote": "theres actually one more secret element that MrBeast "
                      "applies to every one of his hooks", "note": ""},
                     {"chunk": "P2", "kind": "recap", "quote": "a sentence nobody said", "note": ""}]}
    fixes = repair_quotes(obj, ["P1", "P2"], shown)
    assert obj["spans"][0]["chunk"] == "P1" and obj["spans"][0]["quote"] in shown["P1"]
    assert obj["spans"][1]["quote"] == "a sentence nobody said" and len(fixes) == 1  # paraphrase not "repaired"


def test_truncated_vlm_answer_gets_a_shorten_request_not_a_resend():
    from epoch_vlm.prompting import load_template, shorten_messages
    tpl = load_template("prompts/visual_observation.v2.md")
    msgs = [{"role": "user", "content": [{"type": "text", "text": "frames..."}]}]
    out = shorten_messages(msgs, "c000", tpl)
    last = out[-1]["content"][0]["text"]
    assert "cut off" in last and "c000" in last and "{clip_id}" not in last
    assert all(m["role"] != "assistant" for m in out)  # the truncated text is not fed back
    assert "single line" in tpl["SYSTEM"] and "15 words" in tpl["TASK"]


def test_shown_frames_get_contiguous_labels_and_answers_map_back():
    from epoch_vlm.runner import relabel, remap_labels
    shown = [{"ref": "F05", "at_ms": 1}, {"ref": "F07", "at_ms": 2}, {"ref": "F12", "at_ms": 3}]
    disp = relabel(shown)
    assert [f["ref"] for f in disp] == ["F01", "F02", "F03"] and shown[0]["ref"] == "F05"  # originals untouched
    to_pool = {d["ref"]: f["ref"] for d, f in zip(disp, shown)}
    ans = {"segments": [{"frames": ["F01", "F03"], "visible_content": "F02 is not a label here"}],
           "information_flow": {"evidence_frames": ["F02"]}, "text_legibility": [{"frame": "F03", "text": "x"}]}
    out = remap_labels(ans, to_pool)
    assert out["segments"][0]["frames"] == ["F05", "F12"] and out["segments"][0]["visible_content"] == "F02 is not a label here"
    assert out["information_flow"]["evidence_frames"] == ["F07"] and out["text_legibility"][0]["frame"] == "F12"


def test_repair_recovers_paragraph_id_when_model_puts_text_in_the_id_field():
    from pipeline.reasoning.narrative import repair_quotes
    shown = {"P01": "MrBeast has solved YouTube retention. But how does MrBeast reach this magic number?",
             "P02": "Here is how he approaches the first five seconds."}
    obj = {"hook": {"chunk": shown["P01"], "quote": "But how does MrBeast reach this magic number?", "kind": "question"}, "spans": []}
    fixes = repair_quotes(obj, ["P01", "P02"], shown)
    assert obj["hook"]["chunk"] == "P01" and fixes and fixes[0]["to"]["chunk"] == "P01"
    bad = {"hook": {"chunk": "something never said", "quote": "", "kind": "claim"}, "spans": []}
    repair_quotes(bad, ["P01", "P02"], shown)
    assert bad["hook"]["chunk"] == "something never said"  # no match: stays invalid, validation will reject it
