"""Semantic plans become seeded, connected maps, not LLM-authored tile arrays."""
import random
from collections import deque
from . import catalog as C
WIDTH,HEIGHT=52,36

def reachable(tiles,start):
 h,w=len(tiles),len(tiles[0]); seen={tuple(start)}; queue=deque(seen)
 while queue:
  x,y=queue.popleft()
  for nx,ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
   if 0<=nx<w and 0<=ny<h and tiles[ny][nx] not in C.BLOCKED and (nx,ny) not in seen:
    seen.add((nx,ny)); queue.append((nx,ny))
 return seen

def build_region(plan,rid,seed,depth,exits):
 rng=random.Random(seed); w,h=WIDTH,HEIGHT
 tiles=[[C.WALL if x<2 or y<2 or x>=w-2 or y>=h-2 else C.GROUND for x in range(w)] for y in range(h)]
 layout=plan['layout']
 if layout in ('river','islands'):
  river=rng.randint(19,30)
  for y in range(2,h-2):
   river=C.clamp(river+rng.choice((-1,0,0,1)),15,36)
   for x in range(river-2,river+3): tiles[y][x]=C.WATER
 elif layout in ('labyrinth','ruins'):
  for y in range(5,h-4,5):
   gap=rng.randint(5,w-7)
   for x in range(3,w-3):
    if abs(x-gap)>2 and rng.random()>.18: tiles[y][x]=C.WALL
 else:
  for _ in range(10):
   cx,cy=rng.randint(6,w-7),rng.randint(5,h-6)
   for dy in range(-1,2):
    for dx in range(-2,3):
     if rng.random()<.65: tiles[cy+dy][cx+dx]=C.WATER if layout=='grove' else C.WALL
 spawn=[w//2,h-5]; hub=(w//2+rng.randint(-3,3),h//2+rng.randint(-2,2)); occupied={tuple(spawn)}; important=[hub,tuple(spawn)]
 props=[]; entities=[]; zones={'north':(w//2,8),'south':(w//2,h-10),'east':(w-11,h//2),'west':(10,h//2),'center':hub}
 def place(zone):
  zx,zy=zones.get(zone,hub)
  for _ in range(250):
   pos=(C.clamp(zx+rng.randint(-6,6),4,w-5),C.clamp(zy+rng.randint(-4,4),5,h-6))
   if all(abs(pos[0]-x)+abs(pos[1]-y)>2 for x,y in occupied): occupied.add(pos); return pos
  for yy in range(5,h-5):
   for xx in range(4,w-4):
    if (xx,yy) not in occupied: occupied.add((xx,yy)); return xx,yy
  raise ValueError('no free map slot')
 for lm in plan.get('landmarks',[]):
  x,y=place(lm['zone']); prop=dict(kind=lm['type'],x=x,y=y)
  if 'sprite' in lm:prop['sprite']=lm['sprite']
  props.append(prop)
  # Landmark sprites are scenery. Their approach remains walkable and validated.
  important.append((x,y+1))
 item_ids={i['id']:rid+':'+i['id'] for i in plan.get('items',[])}
 for raw in plan['entities']:
  e=dict(raw); e['local_id']=e['id']; e['id']=rid+':'+e['id']; e['x'],e['y']=place(e.get('zone','center')); e['spent']=False
  if e['kind']=='chest': e['item_id']=item_ids.get(e['item_id'],e['item_id'])
  entities.append(e); important.append((e['x'],e['y']))
 for n,link in enumerate(exits):
  x,y=(w//2,h-3) if link['direction']=='back' else ((6,5) if n%2==0 else (w-7,5))
  while (x,y) in occupied: x+=1
  occupied.add((x,y)); important.extend(((x,y),(x,y-1)))
  entities.append(dict(id=f'{rid}:gate_{n}',kind='exit',name=link['label'],target=link['target'],direction=link['direction'],x=x,y=y,spent=False))
 def carve(a,b):
  x,y=a; points=[]; horiz=rng.choice((True,False))
  while (x,y)!=tuple(b):
   points.append((x,y))
   if (horiz and x!=b[0]) or y==b[1]: x+=1 if b[0]>x else -1
   else: y+=1 if b[1]>y else -1
  points.append((x,y))
  for px,py in points:
   for dx,dy in ((0,0),(1,0),(0,1),(-1,0)):
    xx,yy=px+dx,py+dy
    if 2<=xx<w-2 and 2<=yy<h-2: tiles[yy][xx]=C.BRIDGE if tiles[yy][xx]==C.WATER else C.PATH
 for anchor in important: carve(hub,anchor)
 visuals=plan.get('visuals'); scenery=visuals['scenery'] if visuals else ['tree','tree','bush','rock','flower']; density=visuals['density'] if visuals else .075
 for y in range(3,h-3):
  for x in range(3,w-3):
   if scenery and tiles[y][x]==C.GROUND and (x,y) not in occupied and rng.random()<density:
    key=rng.choice(scenery); props.append(dict(kind='scenery' if visuals else key,sprite=key,x=x,y=y))
 area=reachable(tiles,spawn)
 if any((e['x'],e['y']) not in area for e in entities): raise ValueError('unreachable interaction')
 region=dict(id=rid,name=plan['name'],description=plan['description'],biome=plan['biome'],layout=layout,weather=plan['weather'],rule=plan['rule'],depth=depth,seed=seed,width=w,height=h,tiles=tiles,props=props,entities=entities,spawn=spawn,visits=0,revision=0)
 if visuals:region['visuals']=visuals
 return region
