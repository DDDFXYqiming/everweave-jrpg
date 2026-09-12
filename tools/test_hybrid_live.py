"""Bounded live first-region measurement in a fresh isolated save; no auto-prefetch."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine.world import World
from engine.storage import Store
from engine.director import Director,ChatProvider,ProviderError
from engine.content_prompt import prompt,model_context
from engine.library import used_assets

SCENES={
 'town':'一座森林边的邮局小镇。我是送信人，来取一封误送的信。镇上有两间木屋、树木、水井和可以买补给的柜台；通向旧桥的门闩需要操作机关。一盏会眨眼的铜灯提供线索。',
 'dungeon':'废弃矿山下的回声档案馆。我是寻找矿工日志的修理员，地下石厅有旧书架、升降台和一扇机关门。守卫机械会被噪声唤醒，我可以战斗或寻找别的路径；警报响起时，音乐也应发生变化。'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--scene',choices=SCENES,default='town')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline',action='store_true')
    parser.add_argument('--max-calls',type=int,default=2)
    parser.add_argument('--retry-from',type=Path,help='Repair the last recorded response for the same opening premise')
    args=parser.parse_args()
    if not args.live or not os.environ.get('DEEPSEEK_API_KEY'):parser.error('--live and an existing DEEPSEEK_API_KEY are required')
    if not 1<=args.max_calls<=4:parser.error('budget must be 1..4 calls')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    db=out/'world.sqlite3'
    if db.exists():parser.error('Use a fresh output directory')
    w=World(Store(db));w.start(SCENES[args.scene],authored=True);d=Director(w)
    d.configure(dict(offline=False,hybrid_content=not args.baseline,max_calls=args.max_calls,reasoning_effort='low'))
    d.cfg['cooldown']=0
    if args.retry_from:
        from engine.schema import InvalidPatch
        recorded=json.loads(args.retry_from.read_text(encoding='utf-8'))[-1]
        if recorded['context']['setting']!=SCENES[args.scene] or recorded['context']['target']!='r0':parser.error('Recorded response has a different premise/target')
        try:w.validate_patch(recorded['raw'],w.context())
        except InvalidPatch as exc:
            d._failure(exc,w.context(),recorded['raw']);d.retry('r0','region')
        else:parser.error('Recorded response already validates; no paid repair is needed')
    original=ChatProvider.generate;traces=[]
    def write(name,data):(out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    def generate(provider,context,kind,repair=''):
        print(json.dumps(dict(event='request',scene=args.scene,baseline=args.baseline,repair=bool(repair))),flush=True)
        started=time.monotonic();record=dict(context=context,kind=kind,repair=repair)
        try:
            raw,usage=original(provider,context,kind,repair)
            record.update(raw=raw,usage=usage)
            return raw,usage
        except ProviderError as exc:
            record.update(error=str(exc),usage=exc.usage);raise
        finally:
            record['seconds']=round(time.monotonic()-started,3);traces.append(record);write('trace.json',traces)
            print(json.dumps({k:record[k] for k in ('seconds','usage','error') if k in record}),flush=True)
    started=time.monotonic()
    try:
        with patch.object(ChatProvider,'generate',generate):d.step()
        region=w.region() or {};sprites=region.get('visuals',{}).get('sprites',{})
        referenced=sum('asset' in s or 'parts' in s for s in sprites.values())
        mixed=sum(('asset' in s or 'parts' in s) and ('layers' in s or 'parts' in s) for s in sprites.values())
        materials=sum('material' in s for s in sprites.values())
        summary=dict(scene=args.scene,baseline=args.baseline,ready=bool(region),seconds=round(time.monotonic()-started,3),
            calls=d.calls,repair_calls=d.repair_calls,input_tokens=d.tokens_in,output_tokens=d.tokens_out,reasoning_tokens=d.tokens_reasoning,
            sprites=len(sprites),library_sprites=referenced,composed_sprites=mixed,material_sprites=materials,original_sprites=len(sprites)-referenced-materials,
            modules=len(region.get('module_sources',[])),used_assets=used_assets(region.get('plan',{})),
            failed_tasks=d.status()['failed_tasks'],task_history=d.task_history)
        write('result.json',summary)
        snapshot=w.snapshot();snapshot['director']=d.status();write('snapshot.json',snapshot)
        print(json.dumps(summary,ensure_ascii=False),flush=True)
        if not region:raise SystemExit(1)
        print('LIVE_HYBRID_OK' if referenced else 'LIVE_BASELINE_OK',flush=True)
    finally:d.paused=True;w.store.close()

if __name__=='__main__':main()
