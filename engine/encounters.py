"""Optional authored overworld threats, advanced by normal player turns."""
from collections import deque
from .catalog import BLOCKED
from .scene import cells_for, solid_at

def validate(raw):
    from .schema import obj,enum,arr
    from .content import integer,point,expression
    obj(raw,'enemy behavior',('mode','radius','leash','pace','patrol','when','engage_range'),('mode',))
    result=dict(mode=enum(raw['mode'],('guard','patrol','hunt'),'behavior mode'),
        radius=integer(raw.get('radius',5),1,10),leash=integer(raw.get('leash',10),1,16),
        pace=integer(raw.get('pace',2),1,4),engage_range=integer(raw.get('engage_range',1),1,2),
        patrol=[point(p,96,72) for p in arr(raw.get('patrol',[]),'patrol',8)],when=expression(raw.get('when',True)))
    if result['mode']=='patrol' and not result['patrol']:
        from .schema import InvalidPatch
        raise InvalidPatch('patrol needs at least one waypoint')
    return result

def distance(enemy,player):
    return min(abs(x-player['x'])+abs(y-player['y']) for x,y in cells_for(enemy))

def line_of_sight(region,a,b):
    x,y=a;tx,ty=b;dx=abs(tx-x);dy=-abs(ty-y);sx=1 if x<tx else -1;sy=1 if y<ty else -1;error=dx+dy
    while (x,y)!=(tx,ty):
        twice=2*error
        if twice>=dy:error+=dy;x+=sx
        if twice<=dx:error+=dx;y+=sy
        if (x,y)!=(tx,ty) and (region['tiles'][y][x] in BLOCKED or solid_at(region,x,y)):return False
    return True

def next_step(region,enemy,target,player):
    start=(enemy['x'],enemy['y']);queue=deque([start]);parents={start:None}
    occupied={cell for obj in region['entities']+region.get('props',[]) if obj.get('id')!=enemy['id'] and not obj.get('spent') and (obj.get('solid') or obj.get('kind')=='exit') for cell in cells_for(obj)}
    occupied.add((player['x'],player['y']))
    while queue and len(parents)<384:
        at=queue.popleft()
        if abs(at[0]-target[0])+abs(at[1]-target[1])<=1:
            while parents[at] not in (None,start):at=parents[at]
            return at
        neighbors=sorted(((at[0]-1,at[1]),(at[0]+1,at[1]),(at[0],at[1]-1),(at[0],at[1]+1)),key=lambda p:abs(p[0]-target[0])+abs(p[1]-target[1]))
        for point in neighbors:
            if point in parents:continue
            obj=dict(enemy,x=point[0],y=point[1]);cells=cells_for(obj)
            if any(not(0<=x<region['width'] and 0<=y<region['height']) or region['tiles'][y][x] in BLOCKED or (x,y) in occupied for x,y in cells):continue
            parents[point]=at;queue.append(point)
    return start

def advance(world):
    from .runtime import Runtime
    from .game_spec import enabled
    s=world.state;r=world.region();p=s['player']
    if not enabled(s,'combat') or s['battle'] or s['ui'] or s.get('game_over'):return
    if not any(e.get('behavior') and not e.get('spent') for e in r['entities']):return
    if s.get('encounter_grace',0)>0:s['encounter_grace']-=1;world.persist();return
    clock=r.setdefault('encounter_clock',0)+1;r['encounter_clock']=clock
    vm=Runtime(world,r)
    for enemy in r['entities']:
        behavior=enemy.get('behavior')
        if enemy['kind']!='enemy' or enemy.get('spent') or not behavior:continue
        vm.actor=enemy.get('local_id',enemy['id'])
        if not vm.expr(behavior['when']):enemy['alerted']=False;continue
        home=enemy.setdefault('home',[enemy['x'],enemy['y']])
        d=distance(enemy,p);nearest=min(cells_for(enemy),key=lambda cell:abs(cell[0]-p['x'])+abs(cell[1]-p['y']))
        sees=d<=behavior['radius'] and line_of_sight(r,nearest,(p['x'],p['y']))
        enemy['alerted']=sees;enemy['intent']='追击' if sees and behavior['mode']!='guard' else '警戒' if sees else '巡逻' if behavior['mode']=='patrol' else '驻守'
        if sees and d<=behavior['engage_range']:
            world.interact(enemy);world.persist(r);return
        if clock%behavior['pace'] or behavior['mode']=='guard':continue
        target=None
        if sees and abs(p['x']-home[0])+abs(p['y']-home[1])<=behavior['leash']:target=(p['x'],p['y'])
        elif behavior['mode']=='patrol':
            index=enemy.setdefault('patrol_index',0)%len(behavior['patrol']);target=tuple(behavior['patrol'][index])
            if abs(enemy['x']-target[0])+abs(enemy['y']-target[1])<=1:enemy['patrol_index']=(index+1)%len(behavior['patrol']);target=tuple(behavior['patrol'][enemy['patrol_index']])
        elif (enemy['x'],enemy['y'])!=tuple(home):target=tuple(home)
        if target:
            enemy['x'],enemy['y']=next_step(r,enemy,target,p)
            if sees and distance(enemy,p)<=behavior['engage_range']:
                world.interact(enemy);world.persist(r);return
    world.persist(r)
