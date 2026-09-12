"""Opt-in live generation against an isolated copy of an existing save.

Never overwrites the source save or enables a background director. Each real
request, including a failed response or one bounded repair, consumes the budget.
"""
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
from engine.director import ChatProvider, Director, ProviderError
from engine.storage import Store
from engine.world import World


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--from-save',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-calls',type=int,default=4)
    parser.add_argument('--retry-from',type=Path,help='Repair a recorded failed response for the same saved world')
    parser.add_argument('--regions-only',action='store_true',help='Isolate region generation from optional world reactions in this test copy')
    args=parser.parse_args()
    if not args.live or not os.environ.get('DEEPSEEK_API_KEY'):
        parser.error('--live and DEEPSEEK_API_KEY are required')
    if not 1<=args.max_calls<=8:parser.error('live test budget is 1..8 requests')
    source=args.from_save.resolve();output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    database=output/'world.sqlite3'
    if database.exists() or database==source:parser.error('Use a fresh isolated output directory')
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as original:
        with sqlite3.connect(database) as copied:original.backup(copied)
    w=World(Store(database));d=Director(w);responses=[]
    provider_generate=ChatProvider.generate
    def write(name,data):
        (output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    def traced(provider,context,kind,repair=''):
        print(json.dumps(dict(event='request',kind=kind,target=context['target'],repair=bool(repair)),ensure_ascii=False),flush=True)
        started=time.monotonic()
        try:raw,usage=provider_generate(provider,context,kind,repair)
        except ProviderError as exc:
            responses.append(dict(kind=kind,context=context,repair=repair,error=str(exc),usage=exc.usage,seconds=round(time.monotonic()-started,2)))
            write('trace.json',responses)
            raise
        responses.append(dict(kind=kind,context=context,repair=repair,raw=raw,usage=usage,seconds=round(time.monotonic()-started,2)))
        write('trace.json',responses)
        print(json.dumps(dict(event='response',seconds=responses[-1]['seconds'],usage=usage)),flush=True)
        return raw,usage
    try:
        if not w.state:raise RuntimeError('The source save has no world')
        before={key for key,node in w.state['topology'].items() if node['ready']}
        pending=[key for key,_ in w.prefetch_targets() if not w.state['topology'][key]['ready']]
        if not pending:raise RuntimeError('No pending nearby region to test')
        target=pending[0]
        d.configure(dict(offline=False,reasoning_effort='low',max_calls=args.max_calls))
        d.cfg['cooldown']=0
        if args.retry_from:
            recorded=json.loads(args.retry_from.read_text(encoding='utf-8'))[-1]
            context=w.context(target)
            if not all(recorded['context'].get(k)==context.get(k) for k in ('epoch','story_revision','target','kind')):
                raise RuntimeError('Recorded failure is stale or belongs to a different generation task')
            from engine.schema import InvalidPatch
            try:w.validate_patch(recorded['raw'],context)
            except InvalidPatch as exc:
                d._failure(exc,context,recorded['raw']);d.retry(target,'region')
            else:raise RuntimeError('Recorded response already validates; no paid repair is needed')
        with patch.object(ChatProvider,'generate',traced):
            while d.calls<args.max_calls and not w.state['topology'][target]['ready']:
                if args.regions_only:w.reaction_needed=False
                if not d.step():break
                if ('region',target) in d.failed:break
        status=d.status()
        summary=dict(source_save=str(source),target=target,target_ready=w.state['topology'][target]['ready'],
                     new_ready=[key for key,node in w.state['topology'].items() if node['ready'] and key not in before],
                     calls=d.calls,repair_calls=d.repair_calls,accepted=d.accepted,normalization_count=d.normalization_count,
                     input_tokens=d.tokens_in,output_tokens=d.tokens_out,failed_tasks=status['failed_tasks'])
        write('result.json',summary)
        print(json.dumps(summary,ensure_ascii=False),flush=True)
        assert summary['target_ready'],d.error
        print('LIVE_PROTOCOL_OK next_region_ready=true source_save_untouched=true',flush=True)
    finally:
        d.paused=True
        snapshot=w.snapshot();snapshot['director']=d.status()
        write('snapshot.json',snapshot);write('trace.json',responses)
        w.store.close()


if __name__=='__main__':main()
