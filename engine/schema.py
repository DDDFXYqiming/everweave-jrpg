"""Untrusted JSON -> bounded, allow-listed data. No scripts, URLs or file access."""
import copy
import json
import math
import re
from . import catalog as C
class InvalidPatch(ValueError): pass

def obj(v,name,allowed,required=()):
 if not isinstance(v,dict): raise InvalidPatch(f'{name}: expected object')
 extra=set(v)-set(allowed); missing=set(required)-set(v)
 if extra or missing: raise InvalidPatch(f'{name}: unknown fields {sorted(extra)}, missing fields {sorted(missing)}')
 return v

def text(v,name,limit=180):
 if not isinstance(v,str) or not v.strip() or len(v)>limit: raise InvalidPatch(f'{name}: expected nonempty string <= {limit}')
 if any(ord(c)<32 and c not in '\n\t' for c in v): raise InvalidPatch('control characters')
 return v.strip()

def ident(v):
 if not isinstance(v,str) or not re.fullmatch('[a-z][a-z0-9_]{0,39}',v): raise InvalidPatch(f'id {str(v)[:80]!r} must be bare lower_snake_case, <=40 characters; remove all region prefixes and colons from NEW IDs')
 return v

def reference(v):
 v=text(v,'reference',160)
 if not re.fullmatch('[a-z][a-z0-9_:]*',v): raise InvalidPatch('invalid reference')
 return v

def enum(v,choices,name):
 if not isinstance(v,str) or v not in choices: raise InvalidPatch(f'{name}: must be one of {choices}')
 return v

def arr(v,name,maximum,minimum=0):
 if not isinstance(v,list) or not minimum<=len(v)<=maximum: raise InvalidPatch(f'{name}: expected {minimum}..{maximum} items')
 return v

def number(v,name,lo,hi):
 if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v): raise InvalidPatch(f'{name}: finite number required')
 return C.clamp(v,lo,hi)

def dialogue(v):
 return [text(x,'dialogue',280) for x in arr(v,'dialogue',4,1)]

def entity(v):
 e=obj(v,'entity',('id','kind','name','zone','appearance','role','dialogue','choices','monster','tier','move','item_id','sprite','at','solid','state','description','footprint','stats'),('id','kind','name'))
 out=dict(id=ident(e['id']),kind=enum(e['kind'],C.KINDS+('object',),'kind'),name=text(e['name'],'name',48),zone=enum(e.get('zone','center'),C.ZONES,'zone'))
 if 'sprite' in e:out['sprite']=ident(e['sprite'])
 if out['kind']=='npc':
  out.update(role=enum(e.get('role','wanderer'),C.ROLES,'role'),appearance=number(e.get('appearance',0),'appearance',0,7),dialogue=dialogue(e.get('dialogue',['旅人，你听见钟声了吗？'])),choices=[])
  for ch in arr(e.get('choices',[]),'choices',3):
   obj(ch,'choice',('id','text','reply','tag'),('id','text','reply','tag'))
   out['choices'].append(dict(id=ident(ch['id']),text=text(ch['text'],'choice',65),reply=text(ch['reply'],'reply',300),tag=ident(ch['tag'])))
  if len({c['id'] for c in out['choices']})!=len(out['choices']): raise InvalidPatch('duplicate choice IDs')
 elif out['kind']=='enemy': out.update(monster=enum(e.get('monster','slime'),C.MONSTERS,'monster'),tier=number(e.get('tier',1),'tier',1,3),move=enum(e.get('move','strike'),C.MOVES,'move'))
 elif out['kind']=='chest': out['item_id']=reference(e.get('item_id','potion'))
 from .content import entity_extensions
 return entity_extensions(e,out)

def item(v):
 i=obj(v,'item',('id','name','description','kind','effect','power','price','use','sprite'),('id','name','kind','effect','power'))
 kind=enum(i['kind'],('consumable','weapon','charm','key','tool'),'item.kind'); effect=enum(i['effect'],C.EFFECTS,'effect')
 allowed={'consumable':('heal','restore_mp'),'weapon':('attack','burn','drain'),'charm':('defense',),'key':C.EFFECTS,'tool':C.EFFECTS}
 if effect not in allowed[kind]: raise InvalidPatch('effect incompatible with item kind')
 result=dict(id=ident(i['id']),name=text(i['name'],'item.name',48),description=text(i.get('description','世界刚刚赋予它一个名字。'),'description'),kind=kind,effect=effect,power=number(i['power'],'power',1,50 if kind=='consumable' else 8),price=number(i.get('price',25),'price',5,120),icon={'weapon':'sword','consumable':'potion','charm':'charm','key':'key','tool':'key'}[kind])
 if 'use' in i:
  from .content import item_use
  result['use']=item_use(i['use'])
 if 'sprite' in i:result['sprite']=ident(i['sprite'])
 return result

def destination(v):
 obj(v,'destination',('id','name','description'),('id','name','description'))
 return dict(id=ident(v['id']),name=text(v['name'],'destination.name',48),description=text(v['description'],'destination.description',300))

def unique_ids(values,name):
 if len({v['id'] for v in values})!=len(values): raise InvalidPatch('duplicate '+name+' IDs')

def parse_patch(raw,expected):
 if isinstance(raw,str):
  if len(raw.encode())>128000: raise InvalidPatch('response too large')
  raw=raw.strip()
  if raw.startswith('```') and raw.endswith('```'): raw=raw.split('\n',1)[-1].rsplit('```',1)[0]
  try: raw=json.loads(raw,parse_constant=lambda v: (_ for _ in ()).throw(InvalidPatch('nonfinite JSON')))
  except (ValueError,TypeError) as exc: raise InvalidPatch('invalid JSON') from exc
 raw=copy.deepcopy(raw)
 if isinstance(raw,dict) and raw.get('kind')==expected and expected in ('region','reaction') and 'visuals' in raw:
  # Some models emit the art block beside its region/reaction. Its destination
  # is unambiguous only for a single correctly typed envelope. All art still
  # passes the usual validation below; conflicting copies must be rejected.
  other='reaction' if expected=='region' else 'region'
  body=raw.get(expected)
  if isinstance(body,dict) and other not in raw:
   if 'visuals' in body and body['visuals']!=raw['visuals']:
    raise InvalidPatch('conflicting top-level and '+expected+'.visuals')
   body['visuals']=raw.pop('visuals')
 if isinstance(raw,dict) and isinstance(raw.get('region'),dict):
  # Harmless envelope differences can be normalized without another paid call.
  # Region identity is always allocated from the engine's request context.
  region=raw['region']
  if 'id' in region:reference(region.pop('id'))
  for field in ('lore','threads'):
   if field in region:
    if field in raw and raw[field]!=region[field]:raise InvalidPatch('conflicting nested and top-level '+field)
    raw[field]=region.pop(field)
 p=obj(raw,'patch',('kind','world_title','region','reaction','lore','threads'),('kind',))
 if p['kind']!=expected: raise InvalidPatch(f'expected kind={expected}')
 out=dict(kind=expected,lore=[],threads=[])
 if 'world_title' in p: out['world_title']=text(p['world_title'],'world title',48)
 for f in arr(p.get('lore',[]),'lore',4):
  obj(f,'lore',('id','text'),('id','text')); out['lore'].append(dict(id=ident(f['id']),text=text(f['text'],'lore',250)))
 for f in arr(p.get('threads',[]),'threads',3):
  obj(f,'thread',('id','title','note'),('id','title','note')); out['threads'].append(dict(id=ident(f['id']),title=text(f['title'],'thread',64),note=text(f['note'],'note')))
 if expected=='region':
  if 'reaction' in p: raise InvalidPatch('region cannot also react')
  r=obj(p.get('region'),'region',('name','biome','layout','weather','rule','description','landmarks','entities','items','quests','destinations','visuals','scene','program'),('name','description','entities'))
  reg=dict(name=text(r['name'],'region name',48),biome=text(r.get('biome','dream'),'biome',48) if 'scene' in r else enum(r['biome'],C.BIOMES,'biome'),layout=text(r.get('layout','authored'),'layout',48) if 'scene' in r else enum(r['layout'],C.LAYOUTS,'layout'),weather=enum(r.get('weather','clear'),C.WEATHERS,'weather'),rule=enum(r.get('rule','normal'),C.RULES,'rule'),description=text(r['description'],'description',450),entities=[entity(e) for e in arr(r['entities'],'entities',32,1)],items=[item(i) for i in arr(r.get('items',[]),'items',8)],landmarks=[],quests=[])
  for lm in arr(r.get('landmarks',[]),'landmarks',24):
   obj(lm,'landmark',('type','zone','sprite','id','at','solid','footprint'),('type','zone')); landmark=dict(type=enum(lm['type'],C.LANDMARKS,'type'),zone=enum(lm['zone'],C.ZONES,'zone'))
   if 'sprite' in lm:landmark['sprite']=ident(lm['sprite'])
   from .content import entity_extensions
   entity_extensions(lm,landmark)
   if 'id' in lm:landmark['id']=ident(lm['id'])
   reg['landmarks'].append(landmark)
  ids=[e['id'] for e in reg['entities']]; items=[i['id'] for i in reg['items']]
  if len(ids)!=len(set(ids)) or len(items)!=len(set(items)) or set(items)&set(C.BASE_ITEMS): raise InvalidPatch('duplicate or reserved ID')
  for e in reg['entities']:
   if e['kind']=='chest' and e['item_id'] not in set(items)|set(C.BASE_ITEMS): raise InvalidPatch('chest item missing')
  for q in arr(r.get('quests',[]),'quests',3):
   obj(q,'quest',('id','name','description','goal','target'),('id','name','goal','target')); goal=enum(q['goal'],('defeat','talk','collect'),'goal'); target=ident(q['target'])
   if goal=='collect': valid=any(e['kind']=='chest' and e['item_id']==target for e in reg['entities'])
   else: valid=any(e['id']==target and e['kind']==('enemy' if goal=='defeat' else 'npc') for e in reg['entities'])
   if not valid: raise InvalidPatch('quest target is absent or wrong kind')
   reg['quests'].append(dict(id=ident(q['id']),name=text(q['name'],'quest name',64),description=text(q.get('description',q['name']),'quest description'),goal=goal,target=target))
  if len({q['id'] for q in reg['quests']})!=len(reg['quests']): raise InvalidPatch('duplicate quest IDs')
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
   for entry in reg['entities']+reg['landmarks']:
    if entry.get('sprite'):entry['sprite']=resolve_sprite(entry['sprite'],reg['visuals'])
  from .content import scene,program
  if 'scene' in r:reg['scene']=scene(r['scene'])
  if 'program' in r:reg['program']=program(r['program'])
  out['region']=reg
 elif expected=='reaction':
  if 'region' in p: raise InvalidPatch('reaction cannot replace visited maps')
  r=obj(p.get('reaction'),'reaction',('text','weather','rule','npc_lines','spawns','items','quests','locations','visuals','paint','program','object_updates'),('text',)); out['reaction']=dict(text=text(r['text'],'reaction text',450),npc_lines=[],spawns=[],items=[],quests=[],locations=[])
  for key,choices in (('weather',C.WEATHERS),('rule',C.RULES)):
   if key in r: out['reaction'][key]=enum(r[key],choices,key)
  for update in arr(r.get('npc_lines',[]),'npc_lines',3):
   obj(update,'npc update',('id','dialogue'),('id','dialogue')); out['reaction']['npc_lines'].append(dict(id=text(update['id'],'npc ID',100),dialogue=dialogue(update['dialogue'])))
  out['reaction']['spawns']=[entity(e) for e in arr(r.get('spawns',[]),'spawns',2)]
  out['reaction']['items']=[item(i) for i in arr(r.get('items',[]),'items',2)]
  out['reaction']['locations']=[destination(v) for v in arr(r.get('locations',[]),'locations',2)]
  for key in ('spawns','items','locations'): unique_ids(out['reaction'][key],key)
  if any(i['id'] in C.BASE_ITEMS for i in out['reaction']['items']): raise InvalidPatch('reserved item ID')
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
 else: raise InvalidPatch('unsupported kind')
 return out
