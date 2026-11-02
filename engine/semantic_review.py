"""Extract reviewable promises from normalized executable content."""
from __future__ import annotations

import copy
import logging
import threading
import time
from collections import deque


def _emitted(value):
    result=set()
    def walk(node):
        if isinstance(node,list):
            for child in node:walk(child)
        elif isinstance(node,dict):
            if node.get('op')=='emit' and isinstance(node.get('event'),str):result.add(node['event'])
            for child in node.values():walk(child)
    walk(value);return result


def _compact_definitions(region):
    fields=('id','name','kind','description','state','effect','power')
    return [{key:copy.deepcopy(value[key]) for key in fields if key in value}
            for value in region.get('entities',[])+region.get('items',[])]


def evidence(parsed,context):
    region=parsed.get('region',{});program=region.get('program',{})
    hooks=program.get('hooks',[]);objectives=program.get('objectives',[]);definitions=_compact_definitions(region)
    scenes={scene['id']:scene for scene in region.get('scenes',[])}
    units=[]
    def add(content_id,path,kind,player_text,direct_effects,when=True,blocked_hint=None,events=(),execution_context=None,costs=None):
        event_names=set(events)|_emitted(direct_effects)
        related=[copy.deepcopy(h) for h in hooks if h.get('on') in event_names|{'tick'}]
        referenced=[]
        def scene_refs(node):
            if isinstance(node,list):
                for child in node:scene_refs(child)
            elif isinstance(node,dict):
                if node.get('op')=='scene' and node.get('id') in scenes:referenced.append(copy.deepcopy(scenes[node['id']]))
                for child in node.values():scene_refs(child)
        scene_refs(direct_effects)
        units.append(dict(content_id=content_id,path=path,kind=kind,player_text=player_text,
                          blocked_hint=blocked_hint,when=copy.deepcopy(when),direct_effects=copy.deepcopy(direct_effects),
                          triggered_hooks=related,
                          referenced_scenes=referenced,execution_context=copy.deepcopy(execution_context or {}),
                          costs=copy.deepcopy(costs or {}),payment_semantics='costs 在 effects 前检查全部余额并原子扣除；不足时动作不可用，失败时全部回滚。'))
    for index,action in enumerate(program.get('actions',[])):
        add(action['id'],f'region.program.actions[{index}]','action',
            {'label':action['label'],'description':action.get('description',action['label'])},action.get('effects',[]),
            action.get('when',True),action.get('blocked_hint'),('invoke',),
            {'target':action.get('target'),'scope':action.get('scope'),'target_is_already_bound':True},action.get('costs'))
    for scene_index,scene in enumerate(region.get('scenes',[])):
        for choice_index,choice in enumerate(scene.get('choices',[])):
            add(scene['id']+':'+choice['id'],f'region.scenes[{scene_index}].choices[{choice_index}]','scene_choice',
                {'scene_lines':scene.get('lines',[]),'label':choice['label']},choice.get('effects',[]),
                choice.get('when',True),None,('choice',),costs=choice.get('costs'))
    for entity_index,entity in enumerate(region.get('entities',[])):
        for choice_index,choice in enumerate(entity.get('choices',[])):
            recorded={'record_fact':f"choice:{entity.get('id')}:{choice['id']}",'value':choice.get('tag')}
            add(entity.get('id','npc')+':'+choice['id'],f'region.entities[{entity_index}].choices[{choice_index}]','npc_choice',
                {'npc':entity.get('name'),'dialogue':entity.get('dialogue',[]),'choice':choice.get('text'),'reply':choice.get('reply')},
                [recorded],True,None,('choice',))
    return dict(region_id=context.get('target') or region.get('id'),units=units,objectives=copy.deepcopy(objectives),definitions=definitions)


def review(parsed,context,cfg):
    if not cfg.get('jev_enabled',True):return dict(stage='content_review',status='disabled',requests=0,usage={},concerns=[])
    from .jev_judgments import review_semantics
    return review_semantics(evidence(parsed,context),cfg.get('_cancel_event'),cfg.get('_task_deadline'))


class _ReviewCancellation:
    def __init__(self,deadline,current,stop_event):
        self.deadline=deadline;self.current=current;self.stop_event=stop_event;self.cancelled=threading.Event()

    def reason(self):
        if self.cancelled.is_set() or self.stop_event.is_set():return 'cancelled'
        if time.monotonic()>=self.deadline:return 'expired'
        if not self.current():return 'superseded'
        return None

    def is_set(self):
        return self.reason() is not None


class ReviewQueue:
    def __init__(self,on_report):
        self.on_report=on_report;self.condition=threading.Condition();self.pending=deque();self.active=None
        self.worker=None;self.stopped=False;self.skipped=0

    def submit(self,parsed,identity,enabled,deadline,current,stop_event):
        report=None
        with self.condition:
            if not enabled:reason='disabled'
            elif self.stopped or stop_event.is_set():reason='cancelled'
            elif deadline<=time.monotonic():reason='expired'
            elif len(self.pending)>=2:reason='queue_full'
            else:reason=None
            if reason:
                self.skipped+=1
                report=dict(stage='content_review',status='disabled' if reason=='disabled' else 'skipped',reason=reason,requests=0,usage={},concerns=[])
            else:
                cancel=_ReviewCancellation(deadline,current,stop_event)
                for job in list(self.pending)+([self.active] if self.active else []):
                    if (job[1]['epoch'],job[1]['target'])==(identity['epoch'],identity['target']):job[2].cancelled.set()
                self.pending.append((parsed,dict(identity),cancel,time.monotonic()))
                if self.worker is None:
                    self.worker=threading.Thread(target=self._loop,name='jev-observer',daemon=True);self.worker.start()
                self.condition.notify()
        if report:self.on_report(report,identity)
        return dict(status='skipped' if report else 'queued',reason=reason,pending=self.status()['pending'])

    def cancel(self):
        with self.condition:
            for job in list(self.pending)+([self.active] if self.active else []):job[2].cancelled.set()
            self.condition.notify_all()

    def stop(self):
        with self.condition:
            self.stopped=True
            self.cancel()

    def status(self):
        with self.condition:return dict(pending=len(self.pending),active=self.active is not None,capacity=2,skipped=self.skipped)

    def _loop(self):
        while True:
            with self.condition:
                while not self.pending and not self.stopped:self.condition.wait()
                if not self.pending:return
                job=self.pending.popleft();self.active=job
            parsed,identity,cancel,queued=job;started=time.monotonic()
            try:
                reason=cancel.reason()
                if reason:report=dict(status='expired' if reason in ('expired','superseded') else 'cancelled',reason=reason,requests=0,usage={},concerns=[])
                else:report=review(parsed,identity,{'jev_enabled':True,'_cancel_event':cancel,'_task_deadline':cancel.deadline})
                reason=cancel.reason()
                if reason:report.update(status='expired' if reason in ('expired','superseded') else 'cancelled',reason=reason,concerns=[],checks=[])
            except Exception as exc:
                report=dict(status='error',reason=type(exc).__name__,requests=0,usage={},concerns=[])
            finally:
                with self.condition:self.active=None
            report.update(queue_seconds=round(started-queued,3),elapsed_seconds=round(time.monotonic()-queued,3))
            try:self.on_report(report,identity)
            except Exception:logging.getLogger(__name__).exception('观测审查结果记录失败')
