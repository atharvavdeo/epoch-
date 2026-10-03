"""Reviewable rule detections. These are candidates, never automatic rewrite verdicts."""
from __future__ import annotations

import re

from pipeline.predict.model import GROUPS, WEIGHTS
from pipeline.predict.features import _cw
from pipeline.reasoning.candidates import _content_trigrams

POLICY = {
    "setup_before_substance": ("Bring the first useful point forward.", "The setup may supply necessary prerequisites."),
    "no_hook_yet": ("Consider stating the specific problem or outcome earlier.", "The detector may miss an implicit or paraphrased hook."),
    "payoff_pending": ("Give a short answer early, then expand the reasoning.", "A delayed answer may be an intentional teaching sequence."),
    "low_novelty": ("Review for a new action, comparison, example or qualification before shortening.", "Repeated vocabulary can explain a new idea; lexical novelty does not measure semantic progress."),
    "repetition": ("Keep new qualifications and shorten only duplicated wording.", "The passage may intentionally reinforce a difficult concept."),
    "long_sentences": ("Split the sentence while preserving its causal links and qualifications.", "Punctuation may be imperfect; a long sentence can remain easy to understand."),
    "fast_pace": ("Consider a pause between new concepts.", "A faster passage may contain familiar material."),
    "slow_pace": ("Review whether the slower delivery is needed before tightening.", "Slowing down may help explain a difficult concept."),
    "filler_density": ("Review the filler cluster and remove only nonessential hesitation.", "Discourse markers may support a natural speaking style."),
    "dead_air": ("Check the audio and visual context before trimming this gap.", "Silence may accompany a demonstration or intentional reading time."),
    "cta_or_sponsor": ("Consider placing the request at a useful section boundary.", "The interruption may be relevant to the viewer's task."),
    "outro": ("Keep the takeaway before the closing cue and review sign-off length.", "A closing recap may provide useful synthesis."),
}


def build_evidence(features: list[dict], segments: list[dict], duration_ms: int, info: dict) -> dict:
    findings = []
    for group, keys in GROUPS.items():
        for key in keys:
            t = 0
            while t < len(features):
                if not features[t].get(key):
                    t += 1
                    continue
                end = t + 1
                while end < len(features) and features[end].get(key):
                    end += 1
                a, b = t * 1000, min(duration_ms, end * 1000)
                if key == 'no_hook_yet' and b-a < 5000:
                    t = end
                    continue
                source = [s for s in segments if s['interval']['start_ms'] < b and s['interval']['end_ms'] > a]
                quote = ' '.join(s['text'] for s in source)
                suggestion, counter = POLICY[key]
                strength = max(features[x].get(key, 0) for x in range(t, end))
                previous = [s for s in segments if s['interval']['end_ms'] <= a]
                terms = _cw(quote)
                earlier_terms = set().union(*(_cw(s['text']) for s in previous)) if previous else set()
                tri = _content_trigrams(quote)
                matches = [(len(tri & _content_trigrams(s['text'])) / len(tri) if tri else 0, s) for s in previous]
                best = max(matches, key=lambda x: x[0]) if matches else (0, None)
                measured = {'feature_strength': round(strength, 4), 'affected_duration_s': (b-a)/1000}
                if key == 'low_novelty':
                    measured.update({'new_content_terms': sorted(terms-earlier_terms), 'content_term_count': len(terms),
                                     'passage_lexical_novelty': round(len(terms-earlier_terms)/len(terms), 4) if terms else None,
                                     'detector': '20-second rolling content-term novelty below 60% of speaker baseline for at least 10 seconds'})
                elif key == 'repetition':
                    measured.update({'best_earlier_trigram_overlap': round(best[0], 4), 'threshold': .5,
                                     'detector': 'At least two consecutive segments; low added vocabulary; explicit progress markers excluded'})
                elif key == 'long_sentences':
                    measured.update({'longest_sentence_words': max((len(x.split()) for s in source for x in re.split(r'[.!?]+', s['text'])), default=0),
                                     'threshold_words': 30})
                elif key in ('slow_pace', 'fast_pace'):
                    measured.update({'speaker_median_wpm': info.get('median_wpm'), 'relative_threshold': .8 if key == 'slow_pace' else 1.2,
                                     'detector': '20-second aligned-word window over speaking time'})
                elif key == 'filler_density':
                    measured['detector'] = 'At least two lexical filler matches in a 20-second window'
                elif key == 'dead_air':
                    measured['detector'] = 'Waveform-quiet interval with no VAD speech; not transcript absence'
                else:
                    measured['detector'] = 'Narrative structure extraction; detector interpretations require review'

                findings.append({
                    'finding_id': f'{key}:{a}:{b}', 'rule_id': key, 'cause_group': group,
                    'start_ms': a, 'end_ms': b, 'status': 'candidate',
                    'severity': 'high' if strength >= .8 else 'medium' if strength >= .4 else 'low',
                    'evidence_strength': 'provisional', 'quote': quote,
                    'source_segment_ids': [s.get('segment_id', s.get('id')) for s in source if s.get('segment_id', s.get('id'))],
                    'measurements': measured,
                    'earlier_quote': best[1]['text'] if key == 'repetition' and best[1] else None,
                    'mechanism': WEIGHTS[key][1], 'counter_explanation': counter, 'suggestion': suggestion,
                    'preserve': 'Preserve every new point, example, qualification, question and transition in this passage.',
                    'requires_reanalysis': True,
                    'acceptance': 'Review evidence and context before accepting an edit; this rule does not establish abandonment.',
                })
                t = end
    return {'findings': findings, 'timing_source': 'aligned_words' if any('aligned words' in x for x in info['sources']) else 'segment_timestamps',
            'status': 'candidate_review_required', 'risk_label': 'Heuristic transcript and delivery risk — not probability of leaving',
            'risk_bins': risk_bins(features, duration_ms),
            'coverage': {'transcript': bool(segments), 'word_timing': info.get('median_wpm') is not None,
                         'structure': any(x.startswith('narrative structure') for x in info['sources']),
                         'visuals': False},
            'scenario_basis': 'Exploratory candidate-driven scenario; no editorial findings have been accepted automatically',
            'policy': 'Candidates influence an explicitly assumed scenario; acceptance is a separate editorial review step. Related symptoms use their strongest contribution per cause group.',
            'empty_findings_mean': 'No rule candidates identified; this is not proof that the script is healthy.'}



def risk_bins(features: list[dict], duration_ms: int) -> list[dict]:
    """Five-second weighted exposure, retaining a fractional final bin."""
    bins = []
    for a in range(0, duration_ms, 5000):
        b = min(duration_ms, a + 5000)
        groups = {}
        for group, keys in GROUPS.items():
            total = 0.0
            for t in range(a // 1000, min(len(features), (b + 999) // 1000)):
                dt = max(0, min(b, (t+1)*1000) - max(a, t*1000))
                total += dt * max((features[t].get(k, 0) for k in keys), default=0)
            groups[group] = round(total / (b-a), 4)
        bins.append({'start_ms': a, 'end_ms': b, 'duration_s': (b-a)/1000,
                     'groups': groups, 'score': round(100*sum(groups.values())/len(GROUPS), 3),
                     'label': 'Heuristic risk; equal cause-group weights; provisional candidates'})
    return bins


def relation_evidence(segments: list[dict], duration_ms: int, structure: dict | None = None) -> dict:
    """Broader text review candidates; never fed into hazard weights automatically."""
    from pipeline.reasoning.relations import analyse
    relations = analyse(segments)
    findings = []

    def add(rule, group, a, b, mechanism, measurement, counter, suggestion, *, earlier=None, later=None):
        a, b = max(0, a), min(duration_ms, b)
        source = [s for s in segments if s['interval']['start_ms'] < b and s['interval']['end_ms'] > a]
        findings.append({'finding_id': f'{rule}:{a}:{b}:{len(findings)}', 'rule_id': rule,
                         'cause_group': group, 'start_ms': a, 'end_ms': b, 'status': 'candidate',
                         'severity': 'medium', 'evidence_strength': 'provisional',
                         'quote': ' '.join(s['text'] for s in source),
                         'source_segment_ids': [s.get('segment_id', s.get('id')) for s in source if s.get('segment_id', s.get('id'))],
                         'measurements': measurement, 'mechanism': mechanism,
                         'earlier_quote': earlier, 'later_answer_candidates': later or [],
                         'counter_explanation': counter, 'suggestion': suggestion,
                         'preserve': 'Preserve new points, prerequisites, examples, qualifications, questions and transitions.',
                         'requires_reanalysis': True, 'scored_in_scenario': False,
                         'acceptance': 'Review candidate manually; lexical rules do not establish semantic defects or abandonment.'})

    for item in relations['abstract_stretches']:
        add('extended_abstraction', 'comprehension', item['start_ms'], item['end_ms'],
            'No concrete marker was detected throughout an extended explanation.',
            {'duration_s': (item['end_ms']-item['start_ms'])/1000, 'threshold_s': 40,
             'abstract_term_matches': item['abstract_terms'], 'sentences': item['sentences'],
             'concrete_marker_matches': 0},
            'A visual demonstration or familiar context may make this passage concrete; phrase detection cannot judge example usefulness.',
            'Consider a worked example using the concepts already introduced, if the intended audience needs one.')
    for item in relations['term_dependencies']:
        used, explained = item['used_at'], item['explained_at']
        add('term_used_before_explanation', 'comprehension', used['start_ms'], used['end_ms'],
            f"The named phrase '{item['term']}' occurs before a candidate definition.",
            {'term': item['term'], 'first_use_ms': used['start_ms'], 'definition_candidate_ms': explained['start_ms'],
             'gap_s': item['gap_ms']/1000, 'definition_detection': 'Named-phrase pattern, not semantic definition verification'},
            'The audience may already know the term; a paraphrased definition may occur earlier.',
            'If this term is unfamiliar to the intended audience, move the existing definition earlier or add a brief definition at first use.',
            later=[{'start_ms': explained['start_ms'], 'end_ms': explained['end_ms'], 'quote': explained['text'], 'status': 'definition_candidate'}])
    for item in relations['questions']:
        question, answer = item['question'], item['answer']
        if item['kind'] == 'framing' or item['rhetorical_form']:
            continue
        if answer is not None and (item['gap_ms'] or 0) <= 60_000:
            continue
        add('question_without_callback' if answer is None else 'delayed_question_callback', 'questions_payoff',
            question['start_ms'], question['end_ms'],
            'No later lexical callback identified for this substantial question.' if answer is None else 'A lexical callback arrives more than 60 seconds after this question.',
            {'shared_words': item['shared_words'], 'callback_gap_s': item['gap_ms']/1000 if item['gap_ms'] is not None else None,
             'search_horizon_s': 600, 'question_kind': item['kind'], 'rhetorical_form': item['rhetorical_form']},
            'This may be rhetorical or an opening frame; paraphrased answers can be missed and shared vocabulary does not prove an answer.',
            'Confirm whether the question is answered. If needed, answer it explicitly or connect the question to its later payoff.',
            later=[{'start_ms': answer['start_ms'], 'end_ms': answer['end_ms'], 'quote': answer['text'], 'status': 'lexical_callback_candidate'}] if answer else [])
    ledger = []
    for index, promise in enumerate((structure or {}).get('promises', [])):
        first = promise.get('first_fulfil_ms')
        entry = {**promise, 'first_partial_payoff_ms': first,
                 'first_payoff_relative_position': round(first/duration_ms, 4) if first is not None and duration_ms else None,
                 'timing_status': 'narrative_candidate_requires_confirmation',
                 'payoff_quote': ' '.join(s['text'] for s in segments if first is not None and s['interval']['start_ms'] <= first < s['interval']['end_ms'])}
        ledger.append(entry)
        if promise.get('status') in ('unaddressed', 'uncertain'):
            add('unconfirmed_title_promise', 'opening_promise', 0, min(30_000, duration_ms),
                'Narrative extraction has not confirmed fulfilment of a title obligation.',
                {'promise_index': index, 'promise': promise, 'status': promise.get('status')},
                'The extraction may miss a paraphrased or implicit fulfilment; uncertainty is not proof of a broken promise.',
                'Review the title obligation against the full transcript and confirm fulfilment before changing the script.')
    return {'findings': findings, 'promise_ledger': ledger,
            'relation_method': relations['method'], 'scoring_policy': 'Additional semantic-risk candidates are review-only and do not automatically affect the retention scenario.'}
