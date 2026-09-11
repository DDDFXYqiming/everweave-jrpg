"""Explicitly paid runtime integration check. Requires --live and DEEPSEEK_API_KEY."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from engine.director import Director,ChatProvider
from engine.world import World
from engine.storage import Store
from test_runtime import walk_to

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.live or not os.environ.get('DEEPSEEK_API_KEY'):parser.error('Explicit --live and DEEPSEEK_API_KEY are required')
    args.output.mkdir(parents=True,exist_ok=True)
    path=args.output/'world.sqlite3'
    if path.exists():parser.error('Use a fresh output folder; existing worlds are not overwritten')
    w=World(Store(path));d=Director(w);records=[];responses=[]
    generate=ChatProvider.generate
    def traced(provider,context,kind,repair=''):
        started=time.monotonic()
        raw,usage=generate(provider,context,kind,repair)
        responses.append(dict(kind=kind,context=context,repair=repair,raw=raw,usage=usage,seconds=round(time.monotonic()-started,2),reasoning_effort=provider.cfg.get('reasoning_effort')))
        return raw,usage
    def record(stage,**details):
        data=dict(stage=stage,status=d.status(),**details);records.append(data)
        print(json.dumps(data,ensure_ascii=False),flush=True)
    try:
        w.start('群岛在星空中漂流，我是调查陌生信号的邮差。每一次投递都可能让新的地点和线索浮现。')
        d.configure({'offline':False,'max_calls':6});d.cfg['cooldown']=0
        with patch.object(ChatProvider,'generate',traced):
            d.step();record('initial',region=w.region()['name'] if w.region() else None,frontier=w.snapshot()['frontier'])
            assert w.region() and not d.error,d.error
            assert all(w.state['topology'][f['id']].get('outline') for f in w.snapshot()['frontier'])
            guide=next(e for e in w.region()['entities'] if e['kind']=='npc' and e.get('choices'))
            walk_to(w,guide);choice=w.state['ui']['choices'][0]
            w.action({'op':'choice','id':choice['id']});w.action({'op':'close'})
            d.step();record('reaction',choice=choice['text'],revision=w.region()['revision'],frontier=w.snapshot()['frontier'])
            assert w.region()['revision']==1 and not d.error,d.error
            d.step();record('frontier',frontier=w.snapshot()['frontier'])
            assert not d.error,d.error
            target=next(f['id'] for f in w.snapshot()['frontier'] if f['ready'])
            original=w.state['current'];tiles=w.region()['tiles']
            gate=next(e for e in w.region()['entities'] if e.get('target')==target)
            walk_to(w,gate);visited=w.region()['name']
            back=next(e for e in w.region()['entities'] if e.get('target')==original)
            walk_to(w,back);assert w.region()['tiles']==tiles
            record('travel_return',visited=visited,returned=w.region()['name'],maps=w.snapshot()['map_count'])
    finally:
        d.paused=True
        snap=w.snapshot();snap['director']=d.status()
        (args.output/'snapshot.json').write_text(json.dumps(snap,ensure_ascii=False),encoding='utf-8')
        (args.output/'trace.json').write_text(json.dumps(dict(stages=records,responses=responses),ensure_ascii=False,indent=2),encoding='utf-8')
        w.store.close()

if __name__=='__main__':main()
