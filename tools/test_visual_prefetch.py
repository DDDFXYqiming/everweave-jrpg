"""Opt-in paid art + whole-frontier test, with a fresh isolated world."""
import argparse,hashlib,json,os,sys,time
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from engine.world import World
from engine.storage import Store
from engine.director import Director,ChatProvider,ProviderError
from test_runtime import walk_to

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--live',action='store_true')
parser.add_argument('--setting',required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--root-only',action='store_true')
parser.add_argument('--resume',action='store_true')
args=parser.parse_args()
if not args.live or not os.environ.get('DEEPSEEK_API_KEY'):parser.error('--live and DEEPSEEK_API_KEY required')
args.output.mkdir(parents=True,exist_ok=True)
path=args.output/'world.sqlite3'
if path.exists() and not args.resume:parser.error('Use a fresh output folder or explicitly --resume')
w=World(Store(path));d=Director(w);responses=[];original=ChatProvider.generate
if args.resume and (args.output/'trace.json').exists():responses=json.loads((args.output/'trace.json').read_text(encoding='utf-8'))
def trace(provider,context,kind,repair=''):
    started=time.monotonic()
    try:raw,usage=original(provider,context,kind,repair)
    except ProviderError as exc:
        responses.append(dict(target=context['target'],kind=kind,repair=repair,error=str(exc),usage=exc.usage,finish_reason=exc.finish_reason,seconds=round(time.monotonic()-started,2)))
        raise
    responses.append(dict(target=context['target'],kind=kind,repair=repair,raw=raw,usage=usage,seconds=round(time.monotonic()-started,2)))
    return raw,usage
def snapshot():
    s=w.snapshot();s['director']=d.status()
    (args.output/'snapshot.json').write_text(json.dumps(s,ensure_ascii=False),encoding='utf-8')
try:
    if not args.resume:w.start(args.setting)
    d.configure({'offline':False,'reasoning_effort':'low','max_calls':16});d.cfg['cooldown']=0
    with patch.object(ChatProvider,'generate',trace):
        with ThreadPoolExecutor(max_workers=2) as pool:
            for step in range(16):
                futures=[pool.submit(d.step) for _ in range(1 if args.root_only else 2)]
                if not any([f.result() for f in futures]):break
                print(json.dumps(d.status(),ensure_ascii=False),flush=True)
                snapshot()
                if args.root_only:break
                if d.failed:raise RuntimeError(d.error)
                horizon=w.prefetch_targets()
                if w.region() and all(w.state['topology'][rid]['ready'] for rid,_ in horizon):break
    assert w.region() and w.region().get('visuals'),d.error
    v=w.region()['visuals']
    print(json.dumps({'style':v['style'],'terrain':v['terrain'],'sprite_count':len(v['sprites']),'geometry_sha256':hashlib.sha256(json.dumps(v['sprites'],sort_keys=True).encode()).hexdigest()},ensure_ascii=False),flush=True)
    if not args.root_only:
        assert w.state['steps']==0
        assert all(w.state['topology'][rid]['ready'] for rid,_ in w.prefetch_targets())
        calls=d.calls;home=w.state['current'];targets=[x['id'] for x in w.snapshot()['frontier']]
        for target in targets:
            gate=next(e for e in w.region()['entities'] if e.get('target')==target);walk_to(w,gate)
            assert all(x['ready'] for x in w.snapshot()['frontier'])
            back=next(e for e in w.region()['entities'] if e.get('target')==home);walk_to(w,back)
        assert d.calls==calls
        print('PREFETCH_BEFORE_MOVEMENT_OK all_branches=true extra_travel_calls=0',flush=True)
finally:
    d.paused=True;snapshot()
    (args.output/'trace.json').write_text(json.dumps(responses,ensure_ascii=False,indent=2),encoding='utf-8');w.store.close()
