"""Authoritative JRPG state machine. The model proposes content, never outcomes."""
import copy
import random
import threading
import uuid
from collections import OrderedDict,deque
from . import catalog as C
from .pcg import build_region,reachable
from .schema import InvalidPatch,parse_patch
from .visuals import freeze_sprite
from . import gameplay
from .runtime import Runtime, install
from .scene import solid_at, cells_for

class GameError(ValueError): pass

class World:
 def __init__(self,store):
  self.store=store; self.lock=threading.RLock(); self.state=store.load_state(); self.cache=OrderedDict(); self.reaction_needed=bool(self.state and self.state.get("director_reaction_pending",False))
 def start(self,setting):
  if not isinstance(setting,str) or not 3<=len(setting.strip())<=600: raise GameError('世界设定需要 3～600 个字符。')
  self.cache.clear(); self.reaction_needed=False
  self.state=dict(schema_version=2,director_reaction_pending=False,epoch=uuid.uuid4().hex,version=1,story_revision=0,setting=setting.strip(),title='未写之境 · Everweave',current='r0',time=480,steps=0,
   player=dict(x=26,y=31,facing=[0,-1],hp=90,max_hp=90,mp=24,max_mp=24,level=1,xp=0,gold=35,inventory=dict(potion=3,ether=1,wayfarer_blade=1),weapon='wayfarer_blade',charm=''),
   topology={'r0':dict(parent=None,depth=0,ready=False,visited=False,name='最初的落脚处',children=[])},items=copy.deepcopy(C.BASE_ITEMS),quests={},lore={},threads={},facts={},battle=None,ui={},journal=['你的一句话，正在成为一个可以走进去的世界。'])
  self.store.commit(self.state,reset=True)
 def region(self,rid=None):
  rid=rid or self.state['current']
  if rid in self.cache: self.cache.move_to_end(rid); return self.cache[rid]
  r=self.store.load_region(rid)
  if r:
   self.cache[rid]=r
   while len(self.cache)>6: self.cache.popitem(last=False)
  return r
 def persist(self,*regions,event=None,delete=()):
  self.state['version']+=1
  if getattr(self,'_batch',None) is not None:
   self._batch['regions'].update({r['id']:r for r in regions})
   self._batch['events'].extend([event] if event else [])
   self._batch['delete'].update(delete)
  else:self.store.commit(self.state,regions,[event] if event else [],delete_regions=delete)
  for r in regions: self.cache[r['id']]=r; self.cache.move_to_end(r['id'])
  while len(self.cache)>6: self.cache.popitem(last=False)
 def note(self,t):
  self.state['journal'].append(t); self.state['journal']=self.state['journal'][-80:]
 def story(self,kind,text,data=None):
  s=self.state; s['story_revision']+=1; self.reaction_needed=True; s['director_reaction_pending']=True; self.note(text); discarded=[]
  for rid in s['topology'][s['current']]['children']:
   n=s['topology'][rid]
   if n['ready'] and not n['visited']: n['needs_refresh']=True
  return dict(type=kind,text=text,data=data or {},region=s['current'],revision=s['story_revision'],time=s['time']),discarded
 def prefetch_targets(self,depth=2):
  if not self.state: return []
  s=self.state; seen={s['current']}; queue=deque([(s['current'],0)]); targets=[]
  while queue:
   rid,distance=queue.popleft()
   if distance>=depth: continue
   node=s['topology'][rid]
   for neighbor in node['children']+([node['parent']] if node['parent'] else []):
    if neighbor in seen or neighbor not in s['topology']: continue
    seen.add(neighbor); queue.append((neighbor,distance+1))
    if not s['topology'][neighbor]['visited']: targets.append((neighbor,distance+1))
  return targets
 def context(self,target=None,kind='region'):
  s=self.state; rid=target or s['current']; r=self.region(); n=s['topology'][rid]
  parent=self.region(n['parent']) if n['parent'] else None
  art=(parent or r or {}).get('visuals',{})
  return dict(content_version=2,design_history=s.get('design_history',[])[-12:],hero_visual=s.get('hero_visual'),current_program=(r or {}).get('program',{}),current_runtime=(r or {}).get('runtime',{}),current_scene=(r or {}).get('scene',{}),known_sprites=list((r or {}).get('visuals',{}).get('sprites',{})),epoch=s['epoch'],kind=kind,setting=s['setting'],world_title=s['title'],target=rid,target_depth=n['depth'],destination=n.get('outline'),refresh=bool(n.get('needs_refresh')),existing_destinations=[s['topology'][ch].get('outline') for ch in n['children'] if s['topology'][ch].get('outline')],visual_identity={k:art[k] for k in ('style','terrain','palette') if k in art},planned_parent={k:parent[k] for k in ('id','name','description','biome','rule')} if parent else None,story_revision=s['story_revision'],
   player={k:s['player'][k] for k in ('level','hp','gold')},current_region={k:r[k] for k in ('id','name','description','biome','rule','entities')} if r else {},
   available_items=[i for k,i in s['items'].items() if k in C.BASE_ITEMS or k.startswith(s['current']+':') or k in s['player']['inventory']],
   frontier=[dict(id=k,name=s['topology'][k]['name'],outline=s['topology'][k].get('outline'),visited=s['topology'][k]['visited']) for k in s['topology'][s['current']]['children']],
   known_locations=[dict(id=k,name=v['name'],visited=v['visited']) for k,v in list(s['topology'].items())[-18:]],
   facts=dict(list(s['facts'].items())[-35:]),lore=list(s['lore'].values())[-16:],threads=list(s['threads'].values())[-10:],quests=list(s['quests'].values())[-10:],recent_events=self.store.recent_events(12))
 def _merge_lore(self,lore,threads):
  for f in lore: self.state['lore'].setdefault(f['id'],f)
  for t in threads: self.state['threads'].setdefault(t['id'],t)
 def _register_destination(self,parent,spec):
  s=self.state; rid='r_'+format(C.stable_seed(parent,spec['id']),'016x')
  if rid not in s['topology']:
   s['topology'][rid]=dict(parent=parent,depth=s['topology'][parent]['depth']+1,ready=False,visited=False,name=spec['name'],outline=copy.deepcopy(spec),children=[])
  elif not s['topology'][rid]['visited']:
   s['topology'][rid]['outline']=copy.deepcopy(spec)
  return rid
 def _enter_content(self,r):
  s=self.state; rid=r['id']
  if not s['topology'][rid]['visited']:
   for raw in r['plan'].get('items',[]):
    i=copy.deepcopy(raw); i['id']=rid+':'+i['id']; i['origin']=rid
    if i.get('sprite') in r.get('visuals',{}).get('sprites',{}):i['icon_visual']=freeze_sprite(r['visuals']['sprites'][i['sprite']],r['visuals']['palette'])
    s['items'][i['id']]=i
   for raw in r['plan'].get('quests',[]):
    q=copy.deepcopy(raw); q['id']=rid+':'+q['id']; q['target']=rid+':'+q['target'] if q['target'] not in C.BASE_ITEMS else q['target']; q.update(status='active',region=rid,reward=15+r['depth']*5); s['quests'][q['id']]=q
   record=gameplay.design_record(r['plan']);self.state.setdefault('design_history',[]).append(record);self.state['design_history']=self.state['design_history'][-32:]
   previous=self.state['design_history'][:-1]
   if r.get('program') and any(x.get('logic')==record['logic'] for x in previous):self.note('设计提示：这一地区的交互结构与过去相似，导演将在后续创作中避免重复。')
   gameplay.register_objectives(self,r)
   self._merge_lore(r.get('pending_lore',[]),r.get('pending_threads',[])); s['facts']['visited:'+rid]=r['name']
  s['topology'][rid]['visited']=True; s['topology'][rid]['needs_refresh']=False; r['visits']+=1
 def _discard_draft(self,rid):
  node=self.state['topology'].get(rid)
  if not node: return []
  if node['visited']: raise InvalidPatch('cannot remove visited connection')
  removed=[rid]
  for child in list(node['children']): removed.extend(self._discard_draft(child))
  self.state['topology'].pop(rid); self.cache.pop(rid,None)
  return removed
 def validate_patch(self,raw,context):
  p=parse_patch(raw,context['kind'])
  if p['kind']=='region' and context.get('refresh') and context.get('existing_destinations'):
   expected={d['id'] for d in context['existing_destinations']}
   actual={d['id'] for d in p['region'].get('destinations',[])}
   if actual!=expected:raise InvalidPatch('refresh must preserve existing_destinations IDs so already prepared roads remain usable')
  if p['kind']=='reaction':
   rid=context['current_region']['id']; re=p['reaction']; items={i['id'] for i in re['items']}
   known=set(self.state['items']); known.update(k.removeprefix(rid+':') for k in self.state['items'] if k.startswith(rid+':'))
   for e in re['spawns']:
    if e['kind']=='chest' and e['item_id'] not in items|known:
     raise InvalidPatch('chest item '+e['item_id']+' is undefined: define it in reaction.items or reference available_items')
   entities=self.region(rid)['entities']+re['spawns']
   art=copy.deepcopy(self.region(rid).get('visuals',{}))
   if 'visuals' in re:art.setdefault('sprites',{}).update(re['visuals']['sprites'])
   for e in re['spawns']:
    if e.get('sprite') and e['sprite'] not in art.get('sprites',{}):raise InvalidPatch('undefined visual sprite '+e['sprite'])
   for q in re['quests']:
    def matches(value,target): return value==target or value==rid+':'+target
    if q['goal']=='collect': valid=any(e['kind']=='chest' and not e.get('spent',False) and matches(e['item_id'],q['target']) for e in entities)
    else: valid=any(e['kind']==('npc' if q['goal']=='talk' else 'enemy') and not e.get('spent',False) and matches(e['id'],q['target']) for e in entities)
    if not valid: raise InvalidPatch('quest target '+q['target']+' is absent or wrong kind: reference a matching current or newly spawned entity/item')
  if p['kind']=='region' and 'scene' in p['region']:
   rid=context['target'];node=self.state['topology'][rid]
   specs=p['region'].get('destinations',[])
   links=[dict(target='preview_'+str(i),direction='forward',label=v['name']) for i,v in enumerate(specs)]
   if node['parent']:links.append(dict(target=node['parent'],direction='back',label='return'))
   preview=build_region(p['region'],rid,C.stable_seed(self.state['setting'],rid),node['depth'],links);preview['plan']=p['region']
   gameplay.definitions(self,preview)
  return p
 def apply_patch(self,raw,context,source='llm'):
  return gameplay.transaction(self,lambda:self._apply_patch(raw,context,source))
 def _apply_patch(self,raw,context,source='llm'):
  s=self.state
  if not s or context['epoch']!=s['epoch'] or context['story_revision']!=s['story_revision']: return False
  p=self.validate_patch(raw,context)
  before=copy.deepcopy(s); cache_before=copy.deepcopy(self.cache)
  try:
   if p['kind']=='region':
    rid=context['target']; node=s['topology'].get(rid)
    if node is None or node['visited'] or (node['ready'] and not node.get('needs_refresh')): return False
    discarded=[]
    if p['region'].get('destinations'):
     children=[self._register_destination(rid,spec) for spec in p['region']['destinations']]
     # The parent has never been visited: its unused outlines are still provisional.
     for old in node['children']:
      if old not in children:
       discarded.extend(self._discard_draft(old))
     node['children']=children
    elif not node['children']:
     node['children']=[rid+'a',rid+'b']
     for n,child in enumerate(node['children']): s['topology'][child]=dict(parent=rid,depth=node['depth']+1,ready=False,visited=False,name='远处的灯火' if n==0 else '尚未命名的道路',children=[])
    exits=[dict(target=ch,direction='forward',label='前往 '+s['topology'][ch]['name']) for ch in node['children']]
    if node['parent']: exits.append(dict(target=node['parent'],direction='back',label='返回 '+s['topology'][node['parent']]['name']))
    r=build_region(p['region'],rid,C.stable_seed(s['setting'],rid),node['depth'],exits); r.update(plan=p['region'],source=source,pending_lore=p['lore'],pending_threads=p['threads']); node.update(ready=True,name=r['name'],needs_refresh=False)
    if r.get('visuals'):
     if rid=='r0' and 'hero' not in r['visuals']['sprites']:raise InvalidPatch('opening region requires hero sprite')
     if rid=='r0':s['hero_visual']=freeze_sprite(r['visuals']['sprites']['hero'],r['visuals']['palette'])
     if s.get('hero_visual'):r['visuals']['sprites']['hero']=copy.deepcopy(s['hero_visual'])
    if rid=='r0':
     if 'world_title' in p: s['title']=p['world_title']
     self._enter_content(r); s['player']['x'],s['player']['y']=r['spawn']; self.note(r['description'])
    gameplay.definitions(self,r)
    if rid=='r0':gameplay.enter(self,r)
    self.persist(r,delete=discarded)
   else:
    rid=context['current_region'].get('id'); r=copy.deepcopy(self.region(rid))
    if not r: return False
    re=p['reaction']
    for k in ('weather','rule'):
     if k in re: r[k]=re[k]
    for up in re['npc_lines']:
     e=next((e for e in r['entities'] if e['id']==up['id'] and e['kind']=='npc' and not e['spent']),None)
     if e is None: raise InvalidPatch('unknown/nonliving NPC')
     e['dialogue']=up['dialogue']
    occupied={(e['x'],e['y']) for e in r['entities']}|{tuple(r['spawn'])}
    if s['current']==rid: occupied.add((s['player']['x'],s['player']['y']))
    occupied.update((e['x'],e['y']-1) for e in r['entities'] if e['kind']=='exit')
    free=sorted(reachable(r['tiles'],r['spawn']))
    prefix=f'{rid}:event_{s["story_revision"]}_'
    item_refs={i['id']:prefix+i['id'] for i in re['items']}
    entity_refs={e['id']:prefix+e['id'] for e in re['spawns']}
    for raw_item in re['items']:
     i=copy.deepcopy(raw_item); i['id']=item_refs[i['id']];i['origin']=rid
     if i['id'] in s['items']: raise InvalidPatch('item already exists')
     item_art=re.get('visuals',r.get('visuals',{}))
     if i.get('sprite') in item_art.get('sprites',{}):i['icon_visual']=freeze_sprite(item_art['sprites'][i['sprite']],item_art['palette'])
     s['items'][i['id']]=i
    for raw in re['spawns']:
     if len(r['entities'])>=28: raise InvalidPatch('region entity capacity reached')
     e=copy.deepcopy(raw); e['id']=entity_refs[e['id']]
     if any(x['id']==e['id'] for x in r['entities']): raise InvalidPatch('entity already exists')
     if e['kind']=='chest':
      e['item_id']=item_refs.get(e['item_id'],e['item_id'])
      if e['item_id'] not in s['items'] and rid+':'+e['item_id'] in s['items']: e['item_id']=rid+':'+e['item_id']
      if e['item_id'] not in s['items']: raise InvalidPatch('unknown reaction item')
     zones={'north':(r['width']//2,8),'south':(r['width']//2,r['height']-10),'east':(r['width']-11,r['height']//2),'west':(10,r['height']//2),'center':(r['width']//2,r['height']//2)}
     zx,zy=zones[e['zone']]
     pos=next((pos for pos in sorted(free,key=lambda p:abs(p[0]-zx)+abs(p[1]-zy)) if pos not in occupied and 3<pos[0]<r['width']-4 and 4<pos[1]<r['height']-4),None)
     if pos is None: raise InvalidPatch('no room for new entity')
     pos=tuple(e.get('at',pos))
     e.update(x=pos[0],y=pos[1],spent=False,local_id=raw['id']); occupied.add(pos); r['entities'].append(e)
    for raw_quest in re['quests']:
     q=copy.deepcopy(raw_quest); q['id']=prefix+q['id']
     if q['id'] in s['quests']: raise InvalidPatch('quest already exists')
     refs=item_refs if q['goal']=='collect' else entity_refs
     q['target']=refs.get(q['target'],q['target'])
     existing_targets=s['items'] if q['goal']=='collect' else {e['id'] for e in r['entities']}
     if q['target'] not in existing_targets and rid+':'+q['target'] in existing_targets: q['target']=rid+':'+q['target']
     if q['goal']=='collect': valid=any(e['kind']=='chest' and not e['spent'] and e['item_id']==q['target'] for e in r['entities'])
     else: valid=any(e['id']==q['target'] and not e['spent'] and e['kind']==('npc' if q['goal']=='talk' else 'enemy') for e in r['entities'])
     if not valid: raise InvalidPatch('quest target is absent or wrong kind')
     q.update(status='active',region=rid,reward=15+r['depth']*5); s['quests'][q['id']]=q
    for spec in re['locations']:
     children=s['topology'][rid]['children']
     target=self._register_destination(rid,spec)
     if target in children: continue
     if len(children)>=4 or len(r['entities'])>=28: raise InvalidPatch('region connection capacity reached')
     pos=next((p for p in sorted(free,key=lambda p:(p[1],p[0])) if p[1]>=5 and p not in occupied and (p[0],p[1]-1) in free and (p[0],p[1]-1) not in occupied),None)
     if pos is None: raise InvalidPatch('no room for new connection')
     occupied.add(pos); occupied.add((pos[0],pos[1]-1)); children.append(target)
     r['entities'].append(dict(id=prefix+'gate_'+spec['id'],kind='exit',name='前往 '+spec['name'],target=target,direction='forward',x=pos[0],y=pos[1],spent=False))
    gameplay.reaction(self,r,re)
    self._merge_lore(p['lore'],p['threads']); s['director_reaction_pending']=False; r['revision']+=1; self.note('世界回应：'+re['text']); self.persist(r)
  except Exception:
   self.state=before; self.cache=cache_before; raise
  return True
 def check_quests(self,goal,target):
  for q in self.state['quests'].values():
   if q['status']=='active' and q['goal']==goal and q['target']==target:
    q['status']='complete'; self.state['player']['gold']+=q['reward']; self.state['facts']['quest:'+q['id']]='complete'; self.note('完成委托：'+q['name']+f'  +{q["reward"]} 金币')
 def snapshot(self):
  if not self.state: return dict(started=False,version=0)
  s=self.state; r=copy.deepcopy(self.region()); p=s['player']
  if r:
   for e in r['entities']:
    if e['kind']=='exit': e['name']=('返回 ' if e['direction']=='back' else '前往 ')+s['topology'][e['target']]['name']
  inv=[dict(s['items'][k],quantity=n,equipped=k in (p['weapon'],p['charm'])) for k,n in p['inventory'].items() if n>0 and k in s['items']]
  generated_actions=Runtime(self,r).available(scope='combat' if s['battle'] else 'explore') if r and r.get('program') else []
  return copy.deepcopy(dict(available_actions=generated_actions,content_version=2,started=True,version=s['version'],epoch=s['epoch'],title=s['title'],setting=s['setting'],story_revision=s['story_revision'],time=s['time'],
   region={k:v for k,v in r.items() if k not in ('plan','pending_lore','pending_threads')} if r else None,player=p,inventory=inv,quests=list(s['quests'].values())[-20:],threads=list(s['threads'].values())[-10:],journal=s['journal'][-10:],battle=s['battle'],ui=s['ui'],map_count=sum(n['visited'] for n in s['topology'].values()),
   frontier=[dict(id=rid,name=s['topology'][rid]['name'],ready=s['topology'][rid]['ready']) for rid in s['topology'][s['current']]['children']]))
 def action(self,a):
  return gameplay.action(self,a)
 def _action(self,a):
  if not self.state or not self.region(): raise GameError('世界正在生成。')
  if not isinstance(a,dict): raise GameError('动作必须是对象。')
  op=a.get('op'); s=self.state; r=self.region(); p=s['player']
  if op=='close':
   if s['battle']: raise GameError('请先结束战斗或撤离。')
   s['ui']={}; self.persist(); return
  if s['battle']:
   if op!='combat': raise GameError('战斗中不能这样做。')
   self.combat(a.get('move','')); return
  if op=='move':
   if s['ui']: return
   dx,dy=a.get('dx',0),a.get('dy',0)
   if type(dx) is not int or type(dy) is not int or abs(dx)+abs(dy)!=1: raise GameError('一次只能移动一格。')
   p['facing']=[dx,dy]; x,y=p['x']+dx,p['y']+dy
   if not(0<=x<r['width'] and 0<=y<r['height']) or r['tiles'][y][x] in C.BLOCKED: self.persist(); return
   block=next((e for e in r['entities'] if (x,y) in cells_for(e) and not e['spent'] and e.get('solid',True)),None)
   if not block and solid_at(r,x,y):self.persist();return
   if block and block['kind']!='exit':
    if block['kind']=='enemy': self.interact(block)
    else: self.persist()
    return
   p['x'],p['y']=x,y; s['steps']+=1
   if s['steps']%4==0: s['time']+=1
   if r['rule']=='healing_rain' and s['steps']%12==0: p['hp']=min(p['max_hp'],p['hp']+1)
   self.persist(); return
  if op=='interact':
   if s['ui']: return
   candidates=[e for e in r['entities'] if not e['spent'] and gameplay.distance(e,p)<=1]
   if a.get('id'): candidates=[e for e in candidates if e['id']==a['id']]
   candidates.sort(key=lambda e:0 if [e['x']-p['x'],e['y']-p['y']]==p['facing'] else 1)
   if candidates:
    self.interact(candidates[0]); return candidates[0]['id']
   return
  if op=='choice':
   if s['ui'].get('kind')!='dialogue': raise GameError('当前没有对话选项。')
   npc=next((e for e in r['entities'] if e['id']==s['ui'].get('entity')),None); ch=next((c for c in (npc or {}).get('choices',[]) if c['id']==a.get('id')),None)
   if ch is None: raise GameError('无效选项。')
   key='choice:'+npc['id']+':'+ch['id']
   if key in s['facts']: raise GameError('你已做过这个选择。')
   s['facts'][key]=ch['tag']; s['ui']=dict(kind='dialogue',title=npc['name'],lines=[ch['reply']],choices=[])
   event,delete=self.story('choice',ch['text'],dict(tag=ch['tag'],npc=npc['id'])); self.persist(r,event=event,delete=delete); return npc['id']
  if op=='buy':
   if s['ui'].get('kind')!='shop': raise GameError('你不在商店。')
   item=s['items'].get(a.get('id'))
   if item is None or item['id'] not in s['ui']['stock']: raise GameError('店里没有这件物品。')
   if p['gold']<item['price']: raise GameError('金币不足。')
   p['gold']-=item['price']; p['inventory'][item['id']]=p['inventory'].get(item['id'],0)+1; self.note('购入：'+item['name']); self.persist(); return
  if op=='use':
   if s['ui']: raise GameError('先结束当前交互。')
   item=s['items'].get(a.get('id'))
   if not item or p['inventory'].get(item['id'],0)<1: raise GameError('背包里没有这件物品。')
   if item['kind'] in ('weapon','charm'): p[item['kind']]=item['id']; self.note('装备：'+item['name'])
   elif item['kind']=='consumable':
    stat,cap=('hp','max_hp') if item['effect']=='heal' else ('mp','max_mp')
    if p[stat]>=p[cap]: raise GameError('现在不需要使用。')
    p[stat]=min(p[cap],p[stat]+item['power']); p['inventory'][item['id']]-=1; self.note('使用：'+item['name'])
   else: raise GameError('这件物品等待着它的用途。')
   self.persist(); return
  raise GameError('不支持的动作。')
 def interact(self,e):
  if gameplay.interact(self,e):return
  s=self.state; p=s['player']; r=self.region(); kind=e['kind']
  if kind=='exit':
   target=e['target']; node=s['topology'][target]
   if not node['ready']: s['ui']=dict(kind='message',title='世界仍在生长',lines=['这条道路还在生成。可以先探索周围，或在右侧查看生成状态。']); self.persist(); return
   old=s['current']; new=self.region(target); self._enter_content(new); s['current']=target
   back=next((g for g in new['entities'] if g['kind']=='exit' and g['target']==old),None)
   p['x'],p['y']=(back['x'],back['y']) if back and 'scene' in new else ((back['x'],back['y']-1) if back else new['spawn']); s['ui']={}; s['time']+=10; self.note('抵达：'+new['name']); self.note(new['description'])
   self.persist(new,event=dict(type='arrival',text=new['name'],region=target,revision=s['story_revision'])); return
  if kind=='npc':
   self.check_quests('talk',e['id'])
   if e['role']=='merchant':
    stock=['potion','ether']+[i for i in s['items'] if i.startswith(r['id']+':')][:4]; s['ui']=dict(kind='shop',title=e['name'],lines=e['dialogue'],stock=stock,goods=[s['items'][i] for i in stock])
   elif e['role']=='healer':
    p['hp']=p['max_hp']; p['mp']=p['max_mp']; s['ui']=dict(kind='dialogue',title=e['name'],lines=e['dialogue']+['生命与魔力恢复。'],choices=[])
   else:
    choices=[ch for ch in e['choices'] if 'choice:'+e['id']+':'+ch['id'] not in s['facts']]; s['ui']=dict(kind='dialogue',title=e['name'],entity=e['id'],lines=e['dialogue'],choices=choices)
   self.persist(); return
  if kind=='chest':
   item=s['items'][e['item_id']]; p['inventory'][item['id']]=p['inventory'].get(item['id'],0)+1; e['spent']=True; s['facts']['opened:'+e['id']]=item['id']; self.check_quests('collect',item['id'])
   s['ui']=dict(kind='message',title='发现：'+item['name'],lines=[item['description'],'按 I 打开背包，可以装备或使用。']); event,delete=self.story('discovery','获得：'+item['name'],dict(item=item['id'])); self.persist(r,event=event,delete=delete); return
  if kind=='shrine':
   p['hp']=p['max_hp']; p['mp']=p['max_mp']; s['time']+=30; s['ui']=dict(kind='message',title=e['name'],lines=['在微光中休息，生命与魔力恢复。你的脚步已经保存。']); self.persist(); return
  if kind=='enemy':
   level=max(1,min(30,r['depth']+1)); tier=e['tier']; hp=e.get('stats',{}).get('hp',20+level*9+tier*10)
   s['battle']=dict(authored=gameplay.has_combat(r),id=e['id'],name=e['name'],monster=e['monster'],sprite=e.get('sprite','enemy'),move=e['move'],tier=tier,level=level,hp=hp,max_hp=hp,attack=e.get('stats',{}).get('attack',5+level*2+tier),turn=0,burn=0,poison=0,guard=False,log=['你遭遇了 '+e['name']+'。']); s['ui']={}; self.persist()
 def combat(self,move):
  if gameplay.combat(self,move):return
  s=self.state; p=s['player']; b=s['battle']; r=self.region()
  if move not in ('attack','skill','defend','potion','flee'): raise GameError('无效战斗指令。')
  if move=='skill' and (r['rule']=='no_magic' or p['mp']<5): raise GameError('当前不能使用魔法。')
  if move=='potion' and p['inventory'].get('potion',0)<1: raise GameError('没有星露药剂。')
  b['turn']+=1; rng=random.Random(C.stable_seed(s['epoch'],b['id'],s['steps'],b['turn'])); weapon=s['items'][p['weapon']]; charm=s['items'].get(p['charm'],{}); log=b['log']; defending=move=='defend'
  if move in ('attack','skill'):
   damage=8+p['level']*2+(weapon['power'] if weapon['effect']=='attack' else 0)+rng.randint(0,4)
   if move=='skill': p['mp']-=5; damage=int(damage*1.9)
   if r['rule']=='volatile': damage=int(damage*1.3)
   if r['rule']=='echo' and b['turn']%3==0: damage*=2; log.append('回声法则：这一击重复奏响。')
   if b['guard']: damage=max(1,damage//2); b['guard']=False
   b['hp']=max(0,b['hp']-damage); log.append(('星火术' if move=='skill' else '攻击')+f'造成 {damage} 点伤害。')
   if weapon['effect']=='burn': b['burn']=2
   if weapon['effect']=='drain': p['hp']=min(p['max_hp'],p['hp']+max(1,damage//5))
  elif move=='potion': p['inventory']['potion']-=1; p['hp']=min(p['max_hp'],p['hp']+35); log.append('恢复 35 点生命。')
  elif move=='flee':
   if rng.random()<.75: s['battle']=None; self.note('你撤出了战斗。'); self.persist(); return
   log.append('没能撤离。')
  else: p['mp']=min(p['max_mp'],p['mp']+2); log.append('架起防御，恢复 2 点魔力。')
  if b['burn']>0 and b['hp']>0: b['hp']=max(0,b['hp']-3); b['burn']-=1; log.append('余烬造成 3 点伤害。')
  if b['hp']<=0:self._win_battle();return
  if b['move']=='guard' and b['turn']%3==1: b['guard']=True; log.append(b['name']+'进入防御。')
  else:
   damage=b['attack']+rng.randint(0,3)
   if b['move']=='rage' and b['hp']<b['max_hp']//2: damage=int(damage*1.4)
   if r['rule']=='volatile': damage=int(damage*1.3)
   damage=max(1,damage-(charm.get('power',0) if charm.get('effect')=='defense' else 0))
   if defending: damage=max(1,damage//3)
   p['hp']=max(0,p['hp']-damage); log.append(b['name']+f'造成 {damage} 点伤害。')
   if b['move']=='venom' and b['turn']%2==0: b['poison']=2
   if b['move']=='drain': b['hp']=min(b['max_hp'],b['hp']+damage//3)
  if b['poison']>0: p['hp']=max(0,p['hp']-2); b['poison']-=1; log.append('毒素造成 2 点伤害。')
  if r['rule']=='healing_rain': p['hp']=min(p['max_hp'],p['hp']+3)
  if p['hp']<=0:self._defeat()
  else: b['log']=log[-7:]
  self.persist(r)

 def _win_battle(self):
  s=self.state;p=s['player'];b=s['battle'];r=self.region()
  e=next(e for e in r['entities'] if e['id']==b['id']); e['spent']=True; reward=8+b['level']*5+b['tier']*4; p['gold']+=reward; p['xp']+=18+b['tier']*10
  while p['xp']>=p['level']*45:
   p['xp']-=p['level']*45; p['level']+=1; p['max_hp']+=9; p['max_mp']+=3; p['hp']=p['max_hp']; p['mp']=p['max_mp']; self.note(f'提升至等级 {p["level"]}！')
  s['facts']['defeated:'+e['id']]=True; self.check_quests('defeat',e['id']); event,delete=self.story('victory','击败 '+e['name']+f'，获得 {reward} 金币。',dict(enemy=e['id'])); s['battle']=None; s['ui']=dict(kind='message',title='战斗胜利',lines=[event['text'],'胜利正在影响接下来生成的内容。']); self.persist(r,event=event,delete=delete); return

 def _defeat(self):
  s=self.state;p=s['player'];r=self.region()
  loss=min(p['gold'],max(5,p['gold']//5)); p['gold']-=loss; p['hp']=p['max_hp']; p['mp']=p['max_mp']; p['x'],p['y']=r['spawn']; s['battle']=None; s['ui']=dict(kind='message',title='从灯火中醒来',lines=[f'你回到入口，遗失 {loss} 金币。敌人仍在原处。']); self.note('你在失去意识后回到入口。')
