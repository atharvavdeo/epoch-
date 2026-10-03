import json
import math
import wave
import numpy as np
import pytest
from pipeline.media.voice import analyse_voice
from pipeline.reasoning.jev import validate_answer, judge_chunks


def test_waveform_pitch_and_fractional_last_window(tmp_path):
    rate=16000
    t=np.arange(int(10.5*rate))/rate
    signal=(.2*np.sin(2*np.pi*180*t)*32767).astype('<i2')
    p=tmp_path/'voice.wav'
    with wave.open(str(p),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(signal.tobytes())
    result=analyse_voice(p,[{'start_ms':10200}],10500)
    assert abs(result['summary']['median_pitch_hz']-180)<4
    assert result['windows'][-1]['wpm']==120
    assert result['windows'][-1]['end_ms']==10500


def test_silence_does_not_become_pitch(tmp_path):
    p=tmp_path/'silence.wav'
    with wave.open(str(p),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(bytes(32000))
    result=analyse_voice(p,[],1000)
    assert result['summary']['median_pitch_hz'] is None


def test_jev_rejects_invalid_probability_and_wrong_choice():
    with pytest.raises(ValueError): validate_answer({'type':'choice','choice':'rewrite','confidence':.8,'probabilities':{'keep':.8,'rewrite':.1,'shorten':.05,'needs_review':.05}})
    with pytest.raises(ValueError): validate_answer({'type':'choice','choice':'keep','confidence':float('nan'),'probabilities':{'keep':1,'rewrite':0,'shorten':0,'needs_review':0}})


def test_jev_shared_context_and_low_confidence_routes_review(monkeypatch):
    import httpx
    import pipeline.reasoning.jev as j
    monkeypatch.setattr(j,'setting',lambda name:'test')
    calls=[]
    def respond(req):
        body=json.loads(req.content);calls.append(body)
        assert len(body['state']['passages'])==2
        a={k:{'type':'choice','choice':'keep','probabilities':{'keep':.4,'rewrite':.3,'shorten':.2,'needs_review':.1},'confidence':.2} for k in body['questions']}
        return httpx.Response(200,json={'model':'jev-1.13.0','answers':a,'usage':{}})
    ch=[{'chunk_id':f'P{i}','text':'A useful passage','start_ms':i*1000,'end_ms':(i+1)*1000} for i in range(2)]
    result=judge_chunks('title',ch,httpx.MockTransport(respond))
    assert len(calls)==1 and all(d['decision']=='needs_review' for d in result['decisions'])


def test_shorten_requires_earlier_evidence(monkeypatch):
    from pipeline.reasoning.jev import explain_decisions
    from pipeline.reasoning.llm import CerebrasClient
    class MockClient:
        def probe(self): return {}
        def usage(self): return {}
        def json_call(self,*args,**kwargs):
            return {'recommendations':[{'chunk_id':'P02','explanation':'This repeats earlier content.','suggested_rewrite':'Thanks.','preserve':'gratitude','counter_explanation':'Intentional outro','support_quote':'Invented earlier gratitude sentence','support_chunk_id':'P01'}]}
    monkeypatch.setattr(CerebrasClient,'from_env',classmethod(lambda cls:MockClient()))
    result={'decisions':[{'chunk_id':'P02','start_ms':2000,'decision':'shorten','quote':'Thank you for your support.'}]}
    out=explain_decisions(result,[{'chunk_id':'P01','start_ms':0,'text':'Metadata describes data.'}])
    assert out['decisions'][0]['decision']=='needs_review'
    assert 'suggested_rewrite' not in out['decisions'][0]


def test_announced_replay_is_never_shortened_by_a_second_opinion():
    from pipeline.reasoning.jev import guard_announced_replays
    chunks = [{"chunk_id": "P10", "start_ms": 330000, "end_ms": 342000, "text": "The other elements aren't exclusive either. See if you can spot them in the hook to this video."},
              {"chunk_id": "P11", "start_ms": 342000, "end_ms": 371000, "text": "MrBeast has solved YouTube retention, hitting the golden benchmark."},
              {"chunk_id": "P12", "start_ms": 371000, "end_ms": 400000, "text": "Each of his intros is always no longer than 20 seconds long."}]
    res = {"decisions": [{"chunk_id": "P11", "decision": "shorten", "raw_choice": "shorten", "quote": chunks[1]["text"]},
                         {"chunk_id": "P12", "decision": "shorten", "raw_choice": "shorten", "quote": chunks[2]["text"]}]}
    guard_announced_replays(res, chunks)
    assert res["decisions"][0]["decision"] == "needs_review" and "replay" in res["decisions"][0]["reason"]
    assert res["decisions"][1]["decision"] == "shorten"
