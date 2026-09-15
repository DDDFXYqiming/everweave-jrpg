"""One instrumented Luna/high request on a copied save. No other provider."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine.world import World
from engine.storage import Store
from engine.director import Director,ChatProvider,ProviderError
from engine.audit import AuditLog


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true');parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--timeout-seconds',type=int,default=660)
    args=parser.parse_args()
    if not args.live or not 60<=args.timeout_seconds<=900:parser.error('--live and a bounded timeout of 60..900 seconds are required')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);db=out/'world.sqlite3'
    if db.exists():parser.error('use a fresh diagnostic output directory')
    source=sqlite3.connect(args.source.resolve().as_uri()+'?mode=ro',uri=True);dest=sqlite3.connect(db)
    try:source.backup(dest)
    finally:source.close();dest.close()
    w=World(Store(db));d=Director(w);audit=AuditLog(out/'logs');d.audit=audit
    d.configure(dict(provider='codex_subscription',model='gpt-5.6-luna',reasoning_effort='high',offline=False,max_calls=1))
    d.cfg.update(codex_timeout_seconds=args.timeout_seconds,_codex_partial_dir=str(out/'partial'))
    # Print only counters and stages. The reasoning text never enters these logs.
    def progress(p):print(json.dumps({k:p[k] for k in ('stage','elapsed_seconds','last_event_age','reasoning_chars','output_chars','errors','retries')},ensure_ascii=False),flush=True)
    original=ChatProvider.generate;traces=[]
    def write(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
    def generate(provider,ctx,kind,repair=''):
        assert provider.cfg['provider']=='codex_subscription' and provider.cfg['reasoning_effort']=='high'
        provider.cfg['_codex_progress']=progress
        record=dict(kind=kind,context=ctx,repair=repair);start=time.monotonic()
        try:
            raw,usage=original(provider,ctx,kind,repair);record.update(raw=raw,usage=usage);return raw,usage
        except ProviderError as exc:
            record.update(error=str(exc),usage=exc.usage,diagnostics=exc.diagnostics);raise
        finally:
            record['seconds']=round(time.monotonic()-start,3);traces.append(record);write('trace.json',traces)
    try:
        with patch.object(ChatProvider,'generate',generate):d.step()
        result=dict(provider='codex_subscription',model='gpt-5.6-luna',effort='high',calls=d.calls,accepted=d.accepted,
            failed_tasks=d.status()['failed_tasks'],task_history=d.task_history,ready=bool(w.region()),input_tokens=d.tokens_in,output_tokens=d.tokens_out)
        write('result.json',result);write('snapshot.json',dict(w.snapshot(),director=d.status()))
        print(json.dumps(result,ensure_ascii=False),flush=True)
        if d.failed:raise SystemExit(1)
    finally:d.paused=True;audit.close();w.store.close()


if __name__=='__main__':main()
