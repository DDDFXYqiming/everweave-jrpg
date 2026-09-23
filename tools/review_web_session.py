"""汇总一局真实试玩的计时与错误；不读取规则来代替玩家解谜。"""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import statistics


def summarize(folder):
    rows=[]
    for file in (folder/'logs').glob('engine.jsonl*'):
        for line in file.read_text(encoding='utf-8').splitlines():
            try:rows.append(json.loads(line))
            except ValueError:pass
    rows.sort(key=lambda row:row['time'])
    requests=[r for r in rows if r['event']=='chatgpt.request.finished']
    tasks=[r for r in rows if r['event']=='generation.finished']
    actions=[r for r in rows if r['event']=='action.completed']
    starts=[r for r in rows if r['event']=='generation.started' and r['data']['kind']=='campaign']
    ready=[r for r in rows if r['event']=='generation.applied' and r['data']['kind']=='region' and r['data']['target']=='r0']
    milliseconds=sorted(r['data']['milliseconds'] for r in actions)
    successful=[r['data'] for r in requests if r['data']['status']=='completed']
    return dict(
        first_log=rows[0]['time'] if rows else None,last_log=rows[-1]['time'] if rows else None,
        model_requests_started=sum(r['event']=='model.request' for r in rows),
        transport_results=dict(Counter(r['data']['status'] for r in requests)),
        component_requests=dict(Counter(r['data'].get('component') or r['data'].get('kind') for r in requests)),
        time_to_first_region_seconds=round((datetime.fromisoformat(ready[0]['time'])-datetime.fromisoformat(starts[0]['time'])).total_seconds(),3) if starts and ready else None,
        tokens={key:sum(r.get('usage',{}).get(key,0) for r in successful) for key in ('input_tokens','output_tokens','reasoning_tokens','cached_input_tokens')},
        requests=[dict(time=r['time'],**{k:v for k,v in r['data'].items() if k in ('call','kind','target','component','status','seconds','first_output_seconds','response_chars','usage','category','usage_unknown')}) for r in requests],
        reasoning_efforts=dict(Counter(r['data'].get('usage',{}).get('reported_effort') or r['data'].get('usage',{}).get('effort','unknown') for r in requests)),
        tasks=[dict(time=r['time'],**{k:v for k,v in r['data'].items() if k in ('kind','target','status','elapsed_seconds','request_seconds','validation_seconds','attempts','pipeline_requests')}) for r in tasks],
        actions=dict(count=len(actions),operations=dict(Counter(r['data']['action'].get('op') for r in actions)),
            p50_ms=statistics.median(milliseconds) if milliseconds else None,
            p95_ms=milliseconds[min(len(milliseconds)-1,int(len(milliseconds)*.95))] if milliseconds else None),
        errors=[dict(time=r['time'],event=r['event'],**{k:v for k,v in r['data'].items() if k in ('kind','target','action','message','error','issues')}) for r in rows if r['event'] in ('generation.rejected','generation.failed','action.rejected','action.error','director.error')])


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('data_dir',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=summarize(args.data_dir)
    if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('requests','tasks','errors')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
