"""Bounded transport diagnostics. Never stores prompts or reasoning text."""
from collections import Counter
import hashlib
from pathlib import Path
import time
import uuid
from .audit import NullAudit


def failure_category(error):
    info=(error or {}).get('codexErrorInfo')
    if isinstance(info,str):return info,None
    if isinstance(info,dict) and info:
        key=next(iter(info));value=info[key]
        return key,value.get('httpStatusCode') if isinstance(value,dict) else None
    return 'unknown',None


class CodexTelemetry:
    def __init__(self,cfg,system,user):
        self.audit=cfg.get('_audit') or NullAudit();self.notify=cfg.get('_codex_progress')
        self.request_id=uuid.uuid4().hex;self.meta=cfg.get('_request_meta',{})
        self.start=time.monotonic();self.last_event=self.start;self.last_progress=self.start
        self.first_reasoning=None;self.first_output=None;self.stage='starting';self.methods=Counter()
        self.reasoning_chars=0;self.output_chars=0;self.output_items=0;self.errors=0;self.retries=0
        self.usage_reported=False;self.last_method='';self.last_log=self.start;self.passed_old_deadline=False;self.model_context_window=None
        self.partial={};self.phases={};self.partial_dir=cfg.get('_codex_partial_dir')
        self.emit('codex.request.started',model=cfg.get('model'),effort=cfg.get('reasoning_effort'),
            system_chars=len(system),input_chars=len(user),prompt_sha256=hashlib.sha256((system+'\0'+user).encode()).hexdigest(),
            hard_timeout_seconds=cfg.get('codex_timeout_seconds',900),idle_timeout_seconds=cfg.get('codex_idle_timeout_seconds',180))

    def snapshot(self):
        now=time.monotonic()
        return dict(request_id=self.request_id,stage=self.stage,elapsed_seconds=round(now-self.start,3),
            last_event_age=round(now-self.last_event,3),last_progress_age=round(now-self.last_progress,3),
            first_reasoning_seconds=self.first_reasoning,first_output_seconds=self.first_output,
            reasoning_chars=self.reasoning_chars,output_chars=self.output_chars,output_items=self.output_items,
            errors=self.errors,retries=self.retries,last_method=self.last_method,usage_reported=self.usage_reported,
            model_context_window=self.model_context_window)

    def emit(self,event,**data):
        self.audit.emit(event,**self.meta,**self.snapshot(),**data)

    def phase(self,stage):
        self.stage=stage;self.emit('codex.stage')

    def observe(self,message):
        self.last_event=time.monotonic();method=message.get('method','rpc.response');self.last_method=method;self.methods[method]+=1
        params=message.get('params') or {};item=params.get('item') or {}
        if 'reasoning' in method.lower() and isinstance(params.get('delta'),str):
            self.reasoning_chars+=len(params['delta']);self.last_progress=self.last_event;self.stage='reasoning'
            if self.first_reasoning is None:
                self.first_reasoning=round(self.last_event-self.start,3);self.emit('codex.reasoning.started')
        if method=='item/agentMessage/delta':
            delta=params.get('delta','');self.output_chars+=len(delta);self.last_progress=self.last_event;self.stage='output'
            if self.first_output is None:self.first_output=round(self.last_event-self.start,3);self.emit('codex.output.started')
            if self.partial_dir and sum(map(len,self.partial.values()))<128000:
                key=params.get('itemId','unknown');self.partial[key]=(self.partial.get(key,'')+delta)[:128000]
        if method in ('item/started','item/completed'):
            if item.get('id'):self.phases[item['id']]=item.get('phase')
            if item.get('type')=='agentMessage' and method=='item/completed':self.output_items+=1
            if item.get('type') in ('reasoning','agentMessage'):self.last_progress=self.last_event
        if method=='thread/tokenUsage/updated':
            self.usage_reported=True;self.model_context_window=(params.get('tokenUsage') or {}).get('modelContextWindow')
        if method=='error':
            self.errors+=1;self.retries+=int(bool(params.get('willRetry')))
            category,status=failure_category(params.get('error'))
            self.emit('codex.upstream.error',category=category,http_status=status,will_retry=bool(params.get('willRetry')))
        if method in ('model/safetyBuffering/updated','model/rerouted','model/verification'):
            self.emit('codex.model.event',method=method,from_model=params.get('fromModel'),to_model=params.get('toModel'),buffering=params.get('showBufferingUi'))
        if method=='turn/completed':
            self.stage='completed';turn=params.get('turn',{});category,status=failure_category(turn.get('error'))
            self.emit('codex.turn.completed',status=turn.get('status'),error_category=category,http_status=status)
        self.heartbeat()

    def stderr(self,line):
        # Record classification/hash, not raw stderr which can contain credentials.
        low=line.lower();category=next((k for k in ('401','403','429','timeout','reconnect','retry','websocket','transport','config','error') if k in low),'diagnostic')
        self.audit.emit('codex.stderr',request_id=self.request_id,category=category,chars=len(line),sha256=hashlib.sha256(line.encode()).hexdigest())

    def heartbeat(self):
        now=time.monotonic()
        if now-self.start>=300 and not self.passed_old_deadline:
            self.passed_old_deadline=True;self.emit('codex.previous_deadline.reached')
        if now-self.last_log>=15:
            self.last_log=now;self.emit('codex.progress')
            if self.notify:self.notify(self.snapshot())

    def finish(self,status):
        self.emit('codex.request.finished',status=status,event_counts=dict(self.methods))
        if status!='completed' and self.partial_dir and self.partial:
            path=Path(self.partial_dir);path.mkdir(parents=True,exist_ok=True)
            # Only assistant game-output fragments, never reasoning events.
            text='\n'.join(v for k,v in self.partial.items() if self.phases.get(k)!='commentary')
            artifact=path/(self.request_id+'.partial.txt');artifact.write_text(text,encoding='utf8')
            self.emit('codex.partial.saved',file=artifact.name,chars=len(text))
