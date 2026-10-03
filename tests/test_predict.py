import math

import pytest

from pipeline.predict.features import build_features
from pipeline.predict.model import Anchors, drop_moments, predict


def test_neutral_video_hits_the_anchors_exactly():
    p = predict([{} for _ in range(300)], Anchors(0.8, 0.45))
    curve = [1.0] + [s["retention"] for s in p["per_second"]]
    assert math.isclose(curve[30], 0.8, abs_tol=1e-4) and math.isclose(curve[300], 0.45, abs_tol=1e-4)
    assert p["summary"]["excess_loss_by_feature"] == {} and p["calibrated"] is False


def test_survival_is_monotone_and_band_contains_central():
    F = [{"setup_before_substance": 1.0} if t < 40 else {"open_loop": 0.5} if t < 100 else {} for t in range(300)]
    ps = predict(F)["per_second"]
    assert all(b["retention"] <= a["retention"] + 1e-12 for a, b in zip(ps, ps[1:]))
    assert all(s["lower"] - 1e-9 <= s["retention"] <= s["upper"] + 1e-9 for s in ps)


def test_feature_directions_and_attribution():
    base = predict([{} for _ in range(200)])["summary"]["avd_s"]["central"]
    worse = predict([{"repetition": 1.0} if 50 <= t < 80 else {} for t in range(200)])
    better = predict([{"open_loop": 1.0} if 50 <= t < 80 else {} for t in range(200)])
    assert worse["summary"]["avd_s"]["central"] < base < better["summary"]["avd_s"]["central"]
    # all excess loss in the repeated window is attributed to repetition
    s = worse["per_second"][60]
    assert s["contributions"] == {"repetition": s["excess_loss"]} and s["excess_loss"] > 0
    m = drop_moments(worse)
    assert m and m[0]["reasons"][0]["feature"] == "repetition" and 45 <= m[0]["start_s"] <= 80


def test_invalid_anchors_rejected():
    with pytest.raises(ValueError):
        predict([{} for _ in range(100)], Anchors(0.4, 0.6))


def test_features_from_transcript_and_structure():
    segs = [{"interval": {"start_ms": i * 5000, "end_ms": i * 5000 + 5000}, "text": t} for i, t in enumerate(
        ["Hi everyone welcome back to the channel today", "So in this video we will look at something",
         "The battery lasted 9 hours and 12 minutes in our test", "For example the screen used 40 percent"] * 5)]
    st = {"first_substance_ms": 10_000, "hook_ms": 6_000, "promises": [],
          "spans": [{"kind": "cta", "interval": {"start_ms": 30_000, "end_ms": 35_000}}]}
    F, info = build_features(100_000, segs, [], st)
    assert F[3].get("setup_before_substance") == 1.0 and "setup_before_substance" not in F[12]
    assert F[11].get("concrete") == 1.0 and F[32].get("cta_or_sponsor") == 1.0
    assert "no word timing: pace features off" in info["sources"]


def test_fractional_final_bin_and_exact_continuous_watchtime():
    p = predict([{} for _ in range(11)], Anchors(.8, .45), duration_ms=10_250)
    assert p['summary']['duration_s'] == 10.25
    assert p['per_second'][-1]['duration_s'] == .25
    assert p['per_second'][-1]['end_s'] == 10.25
    assert p['summary']['end_pct']['central'] == 45
    hazard = -math.log(.45) / 10.25
    assert p['summary']['avd_s']['central'] == round((1-.45)/hazard, 2)


def test_related_symptoms_are_not_double_counted_or_cancelled_by_question():
    a = predict([{'repetition': 1} for _ in range(100)])
    b = predict([{'repetition': 1, 'low_novelty': 1, 'open_loop': 1} for _ in range(100)])
    assert a['summary']['avd_s'] == b['summary']['avd_s']
    assert b['per_second'][0]['contributions'].keys() == {'repetition'}


def test_excess_loss_is_actual_same_audience_baseline_difference():
    p = predict([{'repetition': 1} for _ in range(100)])['per_second'][0]
    expected = math.exp(-p['baseline_hazard_per_s']) - math.exp(-p['hazard_per_s'])
    assert p['excess_loss'] == pytest.approx(expected, abs=1e-6)
    assert p['conditional_loss'] == pytest.approx(1-math.exp(-p['hazard_per_s']), abs=1e-6)


def test_missing_structure_is_unknown_and_evidence_is_reviewable():
    from pipeline.predict.evidence import build_evidence
    text = ' '.join(['concept'] * 36) + '.'
    segs = [{'segment_id': 's1', 'interval': {'start_ms': 250, 'end_ms': 10_250}, 'text': text}]
    F, info = build_features(10_250, segs, [], None)
    assert all('no_hook_yet' not in f for f in F)
    assert F[0]['long_sentences'] == pytest.approx(.3 * .75)
    finding = build_evidence(F, segs, 10_250, info)['findings'][0]
    assert finding['quote'] == text
    assert finding['source_segment_ids'] == ['s1']
    assert finding['measurements']['longest_sentence_words'] == 36
    assert finding['status'] == 'candidate' and finding['counter_explanation']
    assert finding['preserve'] and finding['requires_reanalysis']


def test_missing_punctuation_does_not_establish_long_sentences():
    segs = [{'interval': {'start_ms': 0, 'end_ms': 10_000}, 'text': ' '.join(['word']*40)}]
    F, _ = build_features(10_000, segs, [], None)
    assert all('long_sentences' not in f for f in F)


def test_five_second_risk_exposure_has_short_final_bin_and_group_max():
    from pipeline.predict.evidence import risk_bins
    bins = risk_bins([{'repetition': 1, 'low_novelty': 1}]*11, 10_250)
    assert [b['duration_s'] for b in bins] == [5, 5, .25]
    assert all(b['score'] == 20 for b in bins)
    assert bins[-1]['end_ms'] == 10_250


def test_relation_candidates_quote_context_and_never_auto_score():
    from pipeline.predict.evidence import relation_evidence
    segs = [
        {'segment_id':'q','interval':{'start_ms':80_000,'end_ms':85_000},'text':'How can battery overheating harm power circuits?'},
        {'segment_id':'u','interval':{'start_ms':5_000,'end_ms':10_000},'text':'Input bias shapes the framework.'},
        {'segment_id':'a','interval':{'start_ms':10_000,'end_ms':60_000},'text':'The framework has an important structure and purpose.'},
        {'segment_id':'d','interval':{'start_ms':60_000,'end_ms':70_000},'text':'This is input bias, and it affects the result.'},
        {'segment_id':'c','interval':{'start_ms':70_000,'end_ms':80_000},'text':'For example, consider 3 cases.'},
    ]
    out = relation_evidence(segs, 85_000, {'promises':[{'status':'fulfilled','first_fulfil_ms':60_000}]})
    by_rule = {x['rule_id']:x for x in out['findings']}
    assert {'question_without_callback','term_used_before_explanation','extended_abstraction'} <= by_rule.keys()
    assert by_rule['question_without_callback']['quote'] == segs[0]['text']
    assert by_rule['term_used_before_explanation']['later_answer_candidates'][0]['quote'] == segs[3]['text']
    assert by_rule['term_used_before_explanation']['measurements']['gap_s'] == 55
    assert all(x['scored_in_scenario'] is False and x['status']=='candidate' for x in out['findings'])
    assert out['promise_ledger'][0]['payoff_quote'] == segs[3]['text']
    assert out['promise_ledger'][0]['first_payoff_relative_position'] == round(60_000/85_000, 4)


def test_lexical_callback_is_candidate_not_semantic_answer():
    from pipeline.predict.evidence import relation_evidence
    segs = [{'interval':{'start_ms':60_000,'end_ms':65_000},'text':'How can battery overheating harm power circuits?'},
            {'interval':{'start_ms':130_000,'end_ms':140_000},'text':'Battery overheating affects power circuits.'}]
    out = relation_evidence(segs, 140_000)
    finding = next(x for x in out['findings'] if x['rule_id']=='delayed_question_callback')
    assert finding['later_answer_candidates'][0]['status']=='lexical_callback_candidate'
    assert finding['measurements']['callback_gap_s']==65
    assert 'does not prove an answer' in finding['counter_explanation']


def test_noisy_question_and_abstract_detectors_suppress_obvious_counterevidence():
    from pipeline.predict.evidence import relation_evidence, build_evidence
    def seg(a, b, text):
        return {'interval': {'start_ms': a, 'end_ms': b}, 'text': text}
    for answer in ('Yes, that will be better.', 'Metadata is a description of data.', 'Exactly, it supplies context.'):
        out = relation_evidence([seg(60_000,65_000,'Will reasoning become more effective?'),seg(65_000,70_000,answer)],70_000)
        assert not any(x['rule_id'].startswith('question_') for x in out['findings'])
    framing = relation_evidence([seg(0,5000,'Could you clarify the difference?')], 10_000)
    assert not framing['findings']
    for text in ('This framework is like a map of the territory.', "The approach is like a person's name.", 'The structure is like how VIP customers interact.'):
        out = relation_evidence([seg(0,50_000,text)],50_000)
        assert not any(x['rule_id']=='extended_abstraction' for x in out['findings'])
    out = relation_evidence([seg(0,50_000,'Apples taste delicious and bananas taste delicious.')],50_000)
    assert not any(x['rule_id']=='extended_abstraction' for x in out['findings'])
    evidence = build_evidence([{'no_hook_yet':1}]+[{}]*9,[seg(1000,10_000,'Start the explanation.')],10_000,{'sources':[]})
    assert not evidence['findings']
