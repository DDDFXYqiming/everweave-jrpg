"""Untrusted JSON -> bounded, allow-listed data. No scripts, URLs or file access."""
import copy
import json
import math
import re
from . import catalog as C
from .diagnostics import InvalidPatch, issue, checked, as_issues, unique_issues

def obj(v,name,allowed,required=()):
 if not isinstance(v,dict): raise InvalidPatch(f'{name}: expected object',value=v,expected='object')
 extra=set(v)-set(allowed); missing=set(required)-set(v)
 if extra or missing:
  errors=[issue(str(key),'unknown field',value=v[key],expected='one of '+', '.join(allowed)) for key in sorted(extra)]
  errors += [issue(str(key),'required field is missing',expected='a defined value') for key in sorted(missing)]
  raise InvalidPatch(issues=errors)
 return v

def text(v,name,limit=180):
 if not isinstance(v,str) or not v.strip() or len(v)>limit: raise InvalidPatch(f'{name}: expected nonempty string <= {limit}',value=v,expected=f'nonempty string, at most {limit} characters')
 if any(ord(c)<32 and c not in '\n\t' for c in v): raise InvalidPatch('control characters')
 return v.strip()

def ident(v):
 if not isinstance(v,str) or not re.fullmatch('[a-z][a-z0-9_]{0,39}',v): raise InvalidPatch(f'id {str(v)[:80]!r} must be bare lower_snake_case, <=40 characters; remove all region prefixes and colons from NEW IDs',value=v,expected='bare lower_snake_case, at most 40 characters')
 return v

def reference(v):
 v=text(v,'reference',160)
 if not re.fullmatch('[a-z][a-z0-9_:]*',v): raise InvalidPatch('invalid reference',category='reference',value=v,expected='a local or exact canonical ID')
 return v

def enum(v,choices,name):
 if not isinstance(v,str) or v not in choices: raise InvalidPatch(f'{name}: must be one of {choices}',value=v,expected=str(choices))
 return v

def arr(v,name,maximum,minimum=0):
 if not isinstance(v,list) or not minimum<=len(v)<=maximum: raise InvalidPatch(f'{name}: expected {minimum}..{maximum} items',value=v,expected=f'array with {minimum}..{maximum} items')
 return v

def number(v,name,lo,hi):
 if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v): raise InvalidPatch(f'{name}: finite number required',value=v,expected='finite number')
 return C.clamp(v,lo,hi)

def dialogue(v):
 return [checked(f'[{index}]',text,x,'dialogue',280) for index,x in enumerate(arr(v,'dialogue',4,1))]

def entity(v):
 e=obj(v,'entity',('id','kind','name','zone','appearance','role','dialogue','choices','monster','tier','move','item_id','sprite','at','solid','state','description','footprint','stats','actor_id'),('id','kind','name'))
 out=dict(id=checked('id',ident,e['id']),kind=checked('kind',enum,e['kind'],C.KINDS+('object',),'kind'),name=checked('name',text,e['name'],'name',48),zone=checked('zone',enum,e.get('zone','center'),C.ZONES,'zone'))
 if 'sprite' in e:out['sprite']=checked('sprite',ident,e['sprite'])
 if 'actor_id' in e:out['actor_id']=checked('actor_id',ident,e['actor_id'])
 if out['kind']=='npc':
  out.update(role=checked('role',enum,e.get('role','wanderer'),C.ROLES,'role'),appearance=checked('appearance',number,e.get('appearance',0),'appearance',0,7),dialogue=checked('dialogue',dialogue,e.get('dialogue',['旅人，你听见钟声了吗？'])),choices=[])
  for index,ch in enumerate(checked('choices',arr,e.get('choices',[]),'choices',3)):
   loc=f'choices[{index}]';checked(loc,obj,ch,'choice',('id','text','reply','tag'),('id','text','reply','tag'))
   out['choices'].append(dict(id=checked(loc+'.id',ident,ch['id']),text=checked(loc+'.text',text,ch['text'],'choice',65),reply=checked(loc+'.reply',text,ch['reply'],'reply',300),tag=checked(loc+'.tag',ident,ch['tag'])))
  if len({c['id'] for c in out['choices']})!=len(out['choices']): raise InvalidPatch('duplicate choice IDs')
 elif out['kind']=='enemy': out.update(monster=checked('monster',enum,e.get('monster','slime'),C.MONSTERS,'monster'),tier=checked('tier',number,e.get('tier',1),'tier',1,3),move=checked('move',enum,e.get('move','strike'),C.MOVES,'move'))
 elif out['kind']=='chest': out['item_id']=checked('item_id',reference,e.get('item_id'))
 from .content import entity_extensions
 return entity_extensions(e,out)

def item(v):
 i=obj(v,'item',('id','name','description','kind','effect','power','price','use','sprite'),('id','name','kind','effect','power'))
 kind=checked('kind',enum,i['kind'],('consumable','weapon','charm','key','tool'),'item.kind'); effect=checked('effect',enum,i['effect'],C.EFFECTS,'effect')
 allowed={'consumable':('heal','restore_mp'),'weapon':('attack','burn','drain'),'charm':('defense',),'key':C.EFFECTS,'tool':C.EFFECTS}
 if effect not in allowed[kind]: raise InvalidPatch('effect incompatible with item kind',path='effect',value=effect,expected=str(allowed[kind]))
 result=dict(id=checked('id',ident,i['id']),name=checked('name',text,i['name'],'item.name',48),description=checked('description',text,i.get('description','世界刚刚赋予它一个名字。'),'description'),kind=kind,effect=effect,power=checked('power',number,i['power'],'power',1,50 if kind=='consumable' else 8),price=checked('price',number,i.get('price',25),'price',5,120),icon={'weapon':'sword','consumable':'potion','charm':'charm','key':'key','tool':'key'}[kind])
 if 'use' in i:
  from .content import item_use
  result['use']=checked('use',item_use,i['use'])
 if 'sprite' in i:result['sprite']=checked('sprite',ident,i['sprite'])
 return result

def destination(v):
 obj(v,'destination',('id','name','description'),('id','name','description'))
 return dict(id=checked('id',ident,v['id']),name=checked('name',text,v['name'],'destination.name',48),description=checked('description',text,v['description'],'destination.description',300))

def unique_ids(values,name):
 if len({v['id'] for v in values})!=len(values): raise InvalidPatch('duplicate '+name+' IDs')

def parse_patch(raw,expected,context=None,corrections=None):
 if expected=='campaign':
  from .campaign import validate
  return dict(kind='campaign',campaign=validate(raw,not (context or {}).get('game_spec'),(context or {}).get('adventure_state')))
 if expected=='direction':
  from .adventure import validate_direction
  return dict(kind='direction',direction=validate_direction((context or {})['validation_world'],raw))
 from .normalization import normalize_patch,decode
 from .modules import expand
 expanded,module_sources=expand(decode(raw),expected)
 normalized,changes,errors=normalize_patch(expanded,expected,context)
 if corrections is not None:corrections.extend(changes)
 errors.extend(_independent_errors(normalized,expected))
 from .story_content import ability_contract_errors
 errors.extend(ability_contract_errors(normalized.get(expected) if isinstance(normalized,dict) else None,expected,context))
 if errors:raise InvalidPatch(issues=unique_issues(errors),corrections=changes)
 try:
  result=_parse_patch(normalized,expected,context)
  if module_sources:result[expected]['module_sources']=module_sources
  return result
 except InvalidPatch as exc:
  exc.corrections=changes
  raise

def _parse_patch(raw,expected,context=None):
 p=obj(raw,'patch',('kind','world_title','region','reaction','lore','threads'),('kind',))
 if p['kind']!=expected: raise InvalidPatch(f'expected kind={expected}',path='kind',value=p['kind'],expected=expected)
 out=dict(kind=expected,lore=[],threads=[])
 if 'world_title' in p: out['world_title']=checked('world_title',text,p['world_title'],'world title',48)
 for index,f in enumerate(checked('lore',arr,p.get('lore',[]),'lore',4)):
  loc=f'lore[{index}]';checked(loc,obj,f,'lore',('id','text'),('id','text')); out['lore'].append(dict(id=checked(loc+'.id',ident,f['id']),text=checked(loc+'.text',text,f['text'],'lore',250)))
 for index,f in enumerate(checked('threads',arr,p.get('threads',[]),'threads',3)):
  loc=f'threads[{index}]';checked(loc,obj,f,'thread',('id','title','note'),('id','title','note')); out['threads'].append(dict(id=checked(loc+'.id',ident,f['id']),title=checked(loc+'.title',text,f['title'],'thread',64),note=checked(loc+'.note',text,f['note'],'note')))
 if expected=='region':
  if 'reaction' in p: raise InvalidPatch('region cannot also react')
  r=obj(p.get('region'),'region',('name','biome','layout','weather','rule','description','landmarks','entities','items','quests','destinations','visuals','scene','program','starting_loadout','audio','abilities','scenes'),('name','description','entities'))
  reg=dict(name=text(r['name'],'region name',48),biome=text(r.get('biome','dream'),'biome',48) if 'scene' in r else enum(r['biome'],C.BIOMES,'biome'),layout=text(r.get('layout','authored'),'layout',48) if 'scene' in r else enum(r['layout'],C.LAYOUTS,'layout'),weather=enum(r.get('weather','clear'),C.WEATHERS,'weather'),rule=enum(r.get('rule','normal'),C.RULES,'rule'),description=text(r['description'],'description',450),entities=[entity(e) for e in arr(r['entities'],'entities',32,1)],items=[item(i) for i in arr(r.get('items',[]),'items',8)],landmarks=[],quests=[])
  for lm in arr(r.get('landmarks',[]),'landmarks',24):
   obj(lm,'landmark',('type','zone','sprite','id','at','solid','footprint'),('type','zone')); landmark=dict(type=enum(lm['type'],C.LANDMARKS,'type'),zone=enum(lm['zone'],C.ZONES,'zone'))
   if 'sprite' in lm:landmark['sprite']=ident(lm['sprite'])
   from .content import entity_extensions
   entity_extensions(lm,landmark)
   if 'id' in lm:landmark['id']=ident(lm['id'])
   reg['landmarks'].append(landmark)
  ids=[e['id'] for e in reg['entities']]; items=[i['id'] for i in reg['items']]
  if len(ids)!=len(set(ids)) or len(items)!=len(set(items)) or ((context or {}).get('item_policy')!='authored' and set(items)&set(C.BASE_ITEMS)): raise InvalidPatch('duplicate or reserved ID')
  known_items={i['id'] for i in (context or {}).get('available_items',[])+(context or {}).get('validation_items',[]) if isinstance(i,dict) and 'id' in i}
  reference_errors=[]
  for index,e in enumerate(reg['entities']):
   if e['kind']=='chest' and e['item_id'] not in set(items)|set(C.BASE_ITEMS)|known_items:
    reference_errors.append(issue(f'region.entities[{index}].item_id','undefined chest item reference',category='reference',value=e['item_id'],expected='a declared local item or an existing canonical item ID'))
  for index,q in enumerate(arr(r.get('quests',[]),'quests',3)):
   checked(f'region.quests[{index}]',obj,q,'quest',('id','name','description','goal','target'),('id','name','goal','target'))
   goal=checked(f'region.quests[{index}].goal',enum,q['goal'],('defeat','talk','collect'),'goal'); target=checked(f'region.quests[{index}].target',reference,q['target'])
   if goal=='collect': valid=any(e['kind']=='chest' and e['item_id']==target for e in reg['entities'])
   else: valid=any(e['id']==target and e['kind']==('enemy' if goal=='defeat' else 'npc') for e in reg['entities'])
   if not valid: reference_errors.append(issue(f'region.quests[{index}].target','quest target is absent or wrong kind',category='reference',value=target,expected='a matching local entity or collectible item'))
   reg['quests'].append(dict(id=ident(q['id']),name=text(q['name'],'quest name',64),description=text(q.get('description',q['name']),'quest description'),goal=goal,target=target))
  if len({q['id'] for q in reg['quests']})!=len(reg['quests']): raise InvalidPatch('duplicate quest IDs')
  if reference_errors:raise InvalidPatch(issues=reference_errors)
  if 'destinations' in r:
   reg['destinations']=[destination(v) for v in arr(r['destinations'],'destinations',2,1)]
   unique_ids(reg['destinations'],'destination')
  if 'visuals' in r:
   from .visuals import validate_visuals,resolve_sprite
   reg['visuals']=validate_visuals(r['visuals'])
   bindings=reg['visuals'].setdefault('bindings',{})
   for lm in reg['landmarks']:
    if lm.get('sprite'): bindings.setdefault('building' if lm['type'] in ('house','tower','camp') else 'object',lm['sprite'])
   for e in reg['entities']:
    if e['kind'] in ('chest','shrine') and e.get('sprite'):bindings.setdefault('object',e['sprite'])
   if reg['visuals']['scenery']:bindings.setdefault('vegetation',reg['visuals']['scenery'][0])
   if not bindings:reg['visuals'].pop('bindings')
   sprite_errors=[]
   for group in ('entities','landmarks','items'):
    for index,entry in enumerate(reg[group]):
     if entry.get('sprite'):
      try:entry['sprite']=checked(f'region.{group}[{index}].sprite',resolve_sprite,entry['sprite'],reg['visuals'])
      except InvalidPatch as exc:sprite_errors.extend(exc.issues)
   if sprite_errors:raise InvalidPatch(issues=sprite_errors)
   from .library import resolve as library_asset
   for group in ('entities','landmarks'):
    for entry,raw_entry in zip(reg[group],r.get(group,[])):
     visual=reg['visuals']['sprites'].get(entry.get('sprite'),{})
     if 'footprint' not in raw_entry and visual.get('asset'):
      entry['footprint']=library_asset(visual['asset'],'image',visual.get('asset_hash'))['footprint']
  from .content import scene,program
  if 'scene' in r:reg['scene']=scene(r['scene'])
  if 'program' in r:reg['program']=program(r['program'])
  if 'starting_loadout' in r:
   from .loadout import parse
   reg['starting_loadout']=checked('region.starting_loadout',parse,r['starting_loadout'])
  if 'audio' in r:
   from .audio import validate_audio
   reg['audio']=checked('region.audio',validate_audio,r['audio'])
  from .story_content import parse_abilities,parse_scenes
  if 'abilities' in r:reg['abilities']=parse_abilities(r['abilities'])
  if 'scenes' in r:reg['scenes']=parse_scenes(r['scenes'])
  out['region']=reg
 elif expected=='reaction':
  if 'region' in p: raise InvalidPatch('reaction cannot replace visited maps')
  r=obj(p.get('reaction'),'reaction',('text','weather','rule','npc_lines','spawns','items','quests','locations','visuals','paint','program','object_updates','future_updates','audio','abilities','scenes'),('text',)); out['reaction']=dict(text=text(r['text'],'reaction text',450),npc_lines=[],spawns=[],items=[],quests=[],locations=[])
  from .story_content import parse_abilities,parse_scenes
  if 'abilities' in r:out['reaction']['abilities']=parse_abilities(r['abilities'])
  if 'scenes' in r:out['reaction']['scenes']=parse_scenes(r['scenes'])
  if 'audio' in r:
   from .audio import validate_audio
   out['reaction']['audio']=checked('reaction.audio',validate_audio,r['audio'],(context or {}).get('current_audio'))
  for key,choices in (('weather',C.WEATHERS),('rule',C.RULES)):
   if key in r: out['reaction'][key]=enum(r[key],choices,key)
  for update in arr(r.get('npc_lines',[]),'npc_lines',3):
   obj(update,'npc update',('id','dialogue'),('id','dialogue')); out['reaction']['npc_lines'].append(dict(id=text(update['id'],'npc ID',100),dialogue=dialogue(update['dialogue'])))
  out['reaction']['spawns']=[entity(e) for e in arr(r.get('spawns',[]),'spawns',2)]
  out['reaction']['items']=[item(i) for i in arr(r.get('items',[]),'items',2)]
  out['reaction']['locations']=[destination(v) for v in arr(r.get('locations',[]),'locations',2)]
  for key in ('spawns','items','locations'): unique_ids(out['reaction'][key],key)
  if (context or {}).get('item_policy')!='authored' and any(i['id'] in C.BASE_ITEMS for i in out['reaction']['items']): raise InvalidPatch('reserved item ID')
  for q in arr(r.get('quests',[]),'quests',2):
   obj(q,'quest',('id','name','description','goal','target'),('id','name','goal','target'))
   target=text(q['target'],'quest target',160)
   if not re.fullmatch('[a-z][a-z0-9_:]*',target): raise InvalidPatch('invalid quest target')
   out['reaction']['quests'].append(dict(id=ident(q['id']),name=text(q['name'],'quest name',64),description=text(q.get('description',q['name']),'quest description'),goal=enum(q['goal'],('defeat','talk','collect'),'goal'),target=target))
  unique_ids(out['reaction']['quests'],'quest')
  from .content import program,entity_extensions,boolean
  if 'program' in r:out['reaction']['program']=program(r['program'])
  if 'visuals' in r:
   from .visuals import validate_visuals
   out['reaction']['visuals']=validate_visuals(r['visuals'])
  if 'paint' in r:
   # Coordinates are checked against the actual current map at application time.
   from .content import paint_commands
   out['reaction']['paint']=paint_commands(r['paint'],96,72)
  out['reaction']['object_updates']=[]
  for u in arr(r.get('object_updates',[]),'object updates',12):
   obj(u,'object update',('id','sprite','at','solid','remove'),('id',))
   up=dict(id=reference(u['id']))
   if 'sprite' in u:up['sprite']=ident(u['sprite'])
   entity_extensions(u,up)
   if 'remove' in u:up['remove']=boolean(u['remove'])
   out['reaction']['object_updates'].append(up)
  out['reaction']['future_updates']=[]
  for index,update in enumerate(checked('reaction.future_updates',arr,r.get('future_updates',[]),'future updates',2)):
   loc=f'reaction.future_updates[{index}]'
   checked(loc,obj,update,'future update',('id','name','description'),('id','description'))
   entry=dict(id=checked(loc+'.id',reference,update['id']),description=checked(loc+'.description',text,update['description'],'future description',300))
   if 'name' in update:entry['name']=checked(loc+'.name',text,update['name'],'future name',48)
   out['reaction']['future_updates'].append(entry)
 else: raise InvalidPatch('unsupported kind')
 return out

def _independent_errors(raw,expected):
 """Collect independent component failures without executing any content."""
 if not isinstance(raw,dict) or not isinstance(raw.get(expected),dict):return []
 from .content import program,scene,state_values,expression,effects,item_use
 from .visuals import validate_visuals
 body=raw[expected];errors=[]
 def probe(path,function,*args):
  try:function(*args)
  except InvalidPatch as exc:errors.extend(as_issues(exc,path))
 for group,validator in (('entities',entity),('spawns',entity),('items',item),('destinations',destination),('locations',destination)):
  if isinstance(body.get(group),list):
   for index,value in enumerate(body[group]):probe(f'{expected}.{group}[{index}]',validator,value)
 if 'scene' in body:probe(expected+'.scene',scene,body['scene'])
 art=body.get('visuals')
 if isinstance(art,dict) and isinstance(art.get('sprites'),dict):
  probe(expected+'.visuals',validate_visuals,art)
  for key,recipe in art['sprites'].items():
   specimen=dict(art,style='sprite validation',terrain='grass',palette={k:'#000000' for k in ('ground','path','water','wall','accent','shadow')},sprites={key:recipe},bindings={},scenery=[])
   probe(expected+'.visuals.sprites.'+key,validate_visuals,specimen)
 elif 'visuals' in body:probe(expected+'.visuals',validate_visuals,art)
 spec=body.get('program')
 if isinstance(spec,dict):
  if 'vars' in spec:probe(expected+'.program.vars',state_values,spec['vars'])
  for group in ('actions','hooks','objectives'):
   if not isinstance(spec.get(group),list):continue
   for index,value in enumerate(spec[group]):
    location=f'{expected}.program.{group}[{index}]'
    probe(location,program,{group:[value]})
    if not isinstance(value,dict):continue
    for field in ('when','fail_when'):
     if field in value:probe(location+'.'+field,expression,value[field])
    for field in ('effects','reward'):
     if field in value:probe(location+'.'+field,effects,value[field])
 elif 'program' in body:probe(expected+'.program',program,spec)
 return unique_issues(errors)
