"""Bounded waveform pitch measurements, not emotion or speaker judgments."""
from __future__ import annotations
import wave
from pathlib import Path
import numpy as np
from pipeline.orchestration.io import read_json, write_json
from pipeline.orchestration.stage import StageSpec, StageResult


def pitch_frames(samples, rate):
    """Normalized autocorrelation on 40ms frames, 20ms hop; 70–400Hz range."""
    n, hop = int(rate*.04), int(rate*.02)
    lo, hi = int(rate/400), int(rate/70)
    result = []
    for i in range(0, max(0,len(samples)-n+1), hop):
        x = samples[i:i+n].astype(float)
        x -= x.mean()
        power = float(np.mean(x*x))
        hz, confidence = None, 0.0
        if power > 1e-6:
            fft = np.fft.rfft(x, n=2*n)
            ac = np.fft.irfft(fft*np.conj(fft))[:n]
            # Normalize each lag by overlapping signal energy.
            energy = np.cumsum(x*x)
            lags = np.arange(lo,hi+1)
            denom = np.sqrt(energy[n-lags-1]*(energy[-1]-energy[lags-1]))
            corr = ac[lags]/np.maximum(denom,1e-12)
            peaks = [j for j in range(1,len(corr)-1) if corr[j]>=corr[j-1] and corr[j]>corr[j+1]]
            if peaks:
                best = max(peaks,key=lambda j: corr[j])
                # Earliest strong peak avoids counting multiple periods.
                best = next((j for j in peaks if corr[j]>=max(.6,float(corr[best])*.9)),best)
                confidence = float(corr[best])
                if confidence>=.6:
                    hz = round(rate/float(lags[best]),2)
        result.append((int(i*1000/rate),hz,confidence))
    return result


def analyse_voice(wav: Path, words: list[dict], duration_ms: int, vad=None):
    with wave.open(str(wav),'rb') as w:
        if w.getsampwidth()!=2 or w.getnchannels()!=1:
            return {'status':'unknown','reason':'requires mono PCM16 WAV','windows':[]}
        rate=w.getframerate()
        x=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)/32768
    frames=pitch_frames(x,rate)
    onsets=[w.get('interval',w).get('start_ms') for w in words]
    onsets=[t0 for t0 in onsets if isinstance(t0,(int,float))]
    def speech(t):
        return vad is None or any(v['start_ms']<=t<v['end_ms'] for v in vad)
    windows=[]
    for start in range(0,duration_ms,10000):
        end=min(duration_ms,start+10000)
        f=[p for p in frames if start<=p[0]<end and speech(p[0])]
        hz=[p[1] for p in f if p[1] is not None]
        # unaligned words have start_ms None (common in Hindi/mixed): they cannot be placed in a window
        count=sum(1 for t0 in onsets if start<=t0<end)
        windows.append({'start_ms':start,'end_ms':end,'wpm':round(count*60000/(end-start),1),
                        'pitch_hz':round(float(np.median(hz)),2) if hz else None,
                        'pitch_std_hz':round(float(np.std(hz)),2) if hz else None,
                        'voiced_fraction':round(len(hz)/max(1,len(f)),3),'words':count})
    hz=[p[1] for p in frames if p[1] is not None and speech(p[0])]
    return {'status':'complete','windows':windows,'summary':{'median_pitch_hz':round(float(np.median(hz)),2) if hz else None,
            'pitch_std_hz':round(float(np.std(hz)),2) if hz else None,'words':len(words),
            'overall_wpm':round(len(words)*60000/duration_ms,1),'aligned_words':len(onsets)},
            'method':'PCM waveform normalized autocorrelation, 40ms frames / 20ms hop, 70–400Hz, correlation >=0.6; 10s summaries',
            'limitations':['Music, multiple speakers and octave errors can distort pitch.','Pitch variation does not establish emotion, vocal monotony, or attention.','WPM uses aligned word onsets and elapsed window duration, including pauses.']}


def voice_spec():
    return StageSpec(name='voice',version='2',deps=('audio','align','probe'),optional_deps=('asr',),config={'pitch_range_hz':[70,400],'window_ms':10000,'correlation_min':.6})


def voice_stage(source):
    def fn(ctx):
        audio=read_json(ctx.dep('audio').path('audio.json'))
        T=read_json(ctx.dep('probe').path('probe.json'))['duration_ms']
        tr=read_json(ctx.dep('align').path('transcript.json'))
        vad=read_json(ctx.deps['asr'].path('vad.json')).get('speech') if 'asr' in ctx.deps else None
        wav=ctx.dep('audio').path('audio16k.wav')
        voice=analyse_voice(wav,tr.get('words',[]),T,vad) if wav.exists() else {'status':'unknown','windows':[],'reason':'no waveform'}
        sil=audio.get('silence',[])
        audio['summary']={'silence_s':round(sum(s['end_ms']-s['start_ms'] for s in sil)/1000,2),'silence_intervals':len(sil),'clipping_windows':len(audio.get('clipping_windows',[]))}
        out={'duration_ms':T,'voice':voice,'audio':audio,'overview':{'title':source['project']['title'],'measured_duration_s':T/1000,'visual_status':'not inspected'}}
        write_json(ctx.out/'deepdive.json',out)
        return StageResult('complete' if voice['status']=='complete' else 'partial',{'windows':len(voice['windows'])})
    return fn
