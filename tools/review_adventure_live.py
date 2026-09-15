"""Bounded director/worker verification on a consistent copy of a played save."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine.world import World
from engine.storage import Store
from engine.director import Director,ChatProvider

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true');parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--steps',type=int,default=1);parser.add_argument('--max-calls',type=int,default=2)
    parser.add_argument('--repair-from',type=Path,help='Reuse the last rejected output from a compatible trace; validate it before requesting repair')
    args=parser.parse_args()
    if not args.live or not os.environ.get('DEEPSEEK_API_KEY'):parser.error('--live and an existing DEEPSEEK_API_KEY are required')
    if not 1<=args.steps<=3 or not 1<=args.max_calls<=6:parser.error('bounded steps/call count required')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);db=out/'world.sqlite3'
    if db.exists():parser.error('output database must not exist')
    source=sqlite3.connect(args.source.resolve().as_uri()+'?mode=ro',uri=True);dest=sqlite3.connect(db)
    try:source.backup(dest)
    finally:source.close();dest.close()
    w=World(Store(db));d=Director(w);d.configure(dict(offline=False,max_calls=args.max_calls,reasoning_effort='low'));d.cfg['cooldown']=0
    if args.repair_from:
        from engine.schema import InvalidPatch
        previous=json.loads(args.repair_from.read_text(encoding='utf8'))[-1];ctx=previous['context'];raw=previous['raw']
        if ctx['kind']=='region':ctx['require_overworld_threats']=True
        if not w.context_is_current(ctx):raise ValueError('repair trace context no longer matches source world')
        try:w.validate_patch(raw,ctx)
        except InvalidPatch as error:
            d.failed_payloads[(ctx['kind'],ctx['target'])]=dict(raw=raw,context=ctx,error=error,generation=d.generation)
        else:raise ValueError('trace already validates; no paid repair is needed')
    traces=[];original=ChatProvider.generate
    def write(name,data):(out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    def generate(provider,ctx,kind,repair=''):
        print(json.dumps(dict(kind=kind,target=ctx['target'],repair=bool(repair))),flush=True)
        start=time.monotonic();raw,usage=original(provider,ctx,kind,repair)
        traces.append(dict(context=ctx,kind=kind,repair=repair,raw=raw,usage=usage,seconds=round(time.monotonic()-start,3)));write('trace.json',traces)
        return raw,usage
    try:
        with patch.object(ChatProvider,'generate',generate):
            for _ in range(args.steps):
                if not d.step() or d.failed:break
        result=dict(source=str(args.source),calls=d.calls,accepted=d.accepted,failed_tasks=d.status()['failed_tasks'],task_history=d.task_history,input_tokens=d.tokens_in,output_tokens=d.tokens_out)
        write('result.json',result);write('snapshot.json',dict(w.snapshot(),director=d.status()))
        print(json.dumps(result,ensure_ascii=False),flush=True)
        if d.failed:raise SystemExit(1)
    finally:d.paused=True;w.store.close()

if __name__=='__main__':main()
