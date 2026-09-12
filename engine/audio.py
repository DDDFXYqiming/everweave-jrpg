"""Declarative music and sound, library-first with bounded original synthesis."""
import math
from .diagnostics import InvalidPatch
from .library import resolve

def scalar(value,lo,hi):
    if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:raise InvalidPatch(f'audio value must be in {lo}..{hi}',value=value)
    return value

def score(raw):
    from .schema import obj,arr,enum
    obj(raw,'score',('bpm','voices'),('bpm','voices'))
    bpm=scalar(raw['bpm'],60,180);voices=[]
    for voice in arr(raw['voices'],'score voices',2,1):
        obj(voice,'voice',('wave','notes','gain'),('wave','notes'))
        notes=[]
        for note in arr(voice['notes'],'notes',24,1):
            arr(note,'note',2,2)
            if type(note[0]) is not int or (note[0]!=0 and not 36<=note[0]<=96):raise InvalidPatch('note pitch must be MIDI 36..96, or 0 for a rest')
            notes.append([note[0],scalar(note[1],.125,4)])
        if sum(n[1] for n in notes)*60/bpm>16:raise InvalidPatch('generated score must be at most 16 seconds per voice')
        voices.append(dict(wave=enum(voice['wave'],('sine','triangle','square'),'wave'),notes=notes,gain=scalar(voice.get('gain',.15),0,.3)))
    return dict(bpm=bpm,voices=voices)

def sound(raw,track=False):
    from .schema import obj,arr,enum
    obj(raw,'audio source',('asset','asset_hash','score','synth','layers','volume','pitch','delay_ms','loop'),())
    forms=set(raw)&{'asset','score','synth','layers'}
    if len(forms)!=1:raise InvalidPatch('audio source needs exactly one asset, score, synth or layers')
    if 'asset_hash' in raw and 'asset' not in raw:raise InvalidPatch('asset_hash needs an asset reference')
    result={}
    if 'asset' in raw:
        entry=resolve(raw['asset'],('music','sfx') if track else 'sfx',raw.get('asset_hash'))
        result.update(asset=raw['asset'],asset_hash=entry['sha256'])
    elif 'score' in raw:
        result['score']=score(raw['score'])
    elif 'synth' in raw:
        if track:raise InvalidPatch('use a score for synthesized music')
        s=obj(raw['synth'],'synth',('wave','frequency','duration'),('wave','frequency','duration'))
        result['synth']=dict(wave=enum(s['wave'],('sine','triangle','square','noise'),'wave'),frequency=scalar(s['frequency'],30,4000),duration=scalar(s['duration'],.02,1))
    else:
        if track:raise InvalidPatch('layered cues are sound effects, not music')
        layers=arr(raw['layers'],'audio layers',3,1)
        if any(isinstance(v,dict) and 'layers' in v for v in layers):raise InvalidPatch('audio layers cannot nest')
        result['layers']=[sound(v) for v in layers]
    result['volume']=scalar(raw.get('volume',.65),0,1)
    result['pitch']=scalar(raw.get('pitch',1),.5,2)
    result['delay_ms']=scalar(raw.get('delay_ms',0),0,500)
    if 'loop' in raw:
        if type(raw['loop']) is not bool:raise InvalidPatch('audio loop must be boolean')
        if raw['loop'] and not track:raise InvalidPatch('looping sounds belong in ambience, not one-shot cues')
        result['loop']=raw['loop']
    return result

def validate_audio(raw,existing=None):
    from .schema import obj,ident,reference
    obj(raw,'audio',('music','cues','bindings','objects','ambience'))
    out=dict(music={},cues={},bindings={},objects={})
    for key,limit in (('music',8),('cues',16)):
        entries=raw.get(key,{})
        if not isinstance(entries,dict) or len(entries)>limit:raise InvalidPatch('too many audio entries')
        out[key]={ident(name):sound(value,track=key=='music') for name,value in entries.items()}
    if 'ambience' in raw:out['ambience']=sound(raw['ambience'],track=True)
    for key,limit in (('bindings',10),('objects',32)):
        entries=raw.get(key,{})
        if not isinstance(entries,dict) or len(entries)>limit:raise InvalidPatch('invalid sound bindings')
        for name,cue in entries.items():
            reference(name) if key=='objects' else ident(name)
            ident(cue)
            if key=='bindings' and name not in ('move','interact','pickup','combat','victory','enter','ui'):raise InvalidPatch('unknown standard sound event',value=name)
            if cue not in out['cues'] and cue not in (existing or {}).get('cues',{}):raise InvalidPatch('undefined sound cue',category='reference',value=cue)
            out[key][name]=cue
    return out
