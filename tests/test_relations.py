from pipeline.predict.features import build_features
from pipeline.reasoning.relations import analyse, sentences
from pipeline.reasoning.transcript_signals import announced_replay


def seg(a, b, t):
    return {"interval": {"start_ms": a, "end_ms": b}, "text": t}


def test_announced_replay_is_not_repetition():
    s = [seg(342_900, 347_600, "See if you can spot them in the hook to this video. MrBeast has solved YouTube retention,")]
    assert announced_replay(s, 345_331)
    assert announced_replay([seg(0, 5000, "The data shows steady growth.")], 3000) is None


def test_question_answer_gap_and_replayed_question():
    segs = [seg(0, 4000, "Why does battery life drop in winter?"), seg(4000, 9000, "We drove for an hour first."),
            seg(70_000, 76_000, "Battery cells lose capacity when winter cold slows the chemistry."),
            seg(80_000, 84_000, "Why does battery life drop in winter?")]
    r = analyse(segs)
    assert len(r["questions"]) == 1  # the replayed question is not a new one
    q = r["questions"][0]
    assert q["answer"]["start_ms"] == 70_000 and q["kind"] == "framing" or q["kind"] == "open_loop"


def test_unpunctuated_asr_is_not_glued_into_one_sentence():
    segs = [seg(i * 5000, i * 5000 + 5000, "and then mr beast goes up the mountain with his friends") for i in range(20)]
    s = sentences(segs)
    assert len(s) == 20 and not any(x["punctuated"] for x in s)
    assert analyse(segs)["abstract_stretches"] == []  # unknown, not "abstract"


def test_setup_penalty_starts_after_the_hook():
    segs = [seg(i * 5000, i * 5000 + 5000, "Words about the topic here today") for i in range(12)]
    st = {"first_substance_ms": 30_000, "hook_ms": 7_000, "hook_end_ms": 10_000, "promises": [], "spans": []}
    F, _ = build_features(60_000, segs, [], st)
    assert "setup_before_substance" not in F[5] and F[15].get("setup_before_substance") == 1.0
