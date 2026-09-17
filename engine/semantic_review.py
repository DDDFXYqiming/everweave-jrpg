"""Extract reviewable promises from normalized executable content."""
from __future__ import annotations

import copy


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
    def add(content_id,path,kind,player_text,direct_effects,when=True,blocked_hint=None,events=(),execution_context=None):
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
                          triggered_hooks=related,objectives=copy.deepcopy(objectives),definitions=definitions,
                          referenced_scenes=referenced,execution_context=copy.deepcopy(execution_context or {})))
    for index,action in enumerate(program.get('actions',[])):
        add(action['id'],f'region.program.actions[{index}]','action',
            {'label':action['label'],'description':action.get('description',action['label'])},action.get('effects',[]),
            action.get('when',True),action.get('blocked_hint'),('invoke',),
            {'target':action.get('target'),'scope':action.get('scope'),'target_is_already_bound':True})
    for scene_index,scene in enumerate(region.get('scenes',[])):
        for choice_index,choice in enumerate(scene.get('choices',[])):
            add(scene['id']+':'+choice['id'],f'region.scenes[{scene_index}].choices[{choice_index}]','scene_choice',
                {'scene_lines':scene.get('lines',[]),'label':choice['label']},choice.get('effects',[]),
                choice.get('when',True),None,('choice',))
    for entity_index,entity in enumerate(region.get('entities',[])):
        for choice_index,choice in enumerate(entity.get('choices',[])):
            recorded={'record_fact':f"choice:{entity.get('id')}:{choice['id']}",'value':choice.get('tag')}
            add(entity.get('id','npc')+':'+choice['id'],f'region.entities[{entity_index}].choices[{choice_index}]','npc_choice',
                {'npc':entity.get('name'),'dialogue':entity.get('dialogue',[]),'choice':choice.get('text'),'reply':choice.get('reply')},
                [recorded],True,None,('choice',))
    return dict(region_id=context.get('target') or region.get('id'),units=units)


def review(parsed,context,cfg):
    if not cfg.get('jev_enabled',True):return dict(stage='content_review',status='disabled',requests=0,usage={},concerns=[])
    from .jev_judgments import review_semantics
    return review_semantics(evidence(parsed,context),cfg.get('_cancel_event'))
