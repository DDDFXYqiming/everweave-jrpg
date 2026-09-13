"""Compile a model's spatial drawing, without substituting a canned map layout."""
import copy
import json
import math
from . import catalog as C
from .schema import InvalidPatch
from .content import paint_commands
from .diagnostics import issue


def cells_for(obj):
    """Footprints extend right/up from a sprite's bottom-left logical cell."""
    w, h = obj.get('footprint', [1, 1])
    return [(obj['x'] + dx, obj['y'] - dy) for dy in range(h) for dx in range(w)]


def solid_at(region, x, y, ignore=None):
    for obj in region.get('props', []) + region.get('entities', []):
        if (ignore is not None and obj.get('id') == ignore) or obj.get('spent') or not obj.get('solid', False):
            continue
        if (x, y) in cells_for(obj): return True
    return False


def paint(region, commands):
    width, height = region['width'], region['height']
    surfaces = region.setdefault('surfaces', [[''] * width for _ in range(height)])
    for command in paint_commands(commands, width, height):
        surface = command.get('surface', '')
        for field in ('surface','wall_surface','door_surface'):
            if command.get(field) and command[field] not in region.get('visuals',{}).get('sprites',{}):
                raise InvalidPatch('undefined surface recipe '+command[field])
        def put(x, y, tile=None, skin=None):
            if not 0 <= x < width or not 0 <= y < height:
                raise InvalidPatch('painting outside scene')
            region['tiles'][y][x] = command['tile'] if tile is None else tile
            surfaces[y][x] = surface if skin is None else skin
        if 'line' in command:
            radius = (command['width'] - 1) // 2
            for a, b in zip(command['line'], command['line'][1:]):
                x, y = a
                while True:
                    for dy in range(-radius, command['width'] - radius):
                        for dx in range(-radius, command['width'] - radius):
                            if 0 <= x+dx < width and 0 <= y+dy < height: put(x+dx, y+dy)
                    if [x, y] == b: break
                    if x != b[0]: x += 1 if b[0] > x else -1
                    else: y += 1 if b[1] > y else -1
        else:
            x, y, w, h = command.get('rect', command.get('room'))
            for yy in range(y, y+h):
                for xx in range(x, x+w):
                    edge = xx in (x, x+w-1) or yy in (y, y+h-1)
                    wall='room' in command and edge
                    put(xx, yy, C.WALL if wall else None, command.get('wall_surface','') if wall else None)
            for xx, yy in command.get('doors', []):
                if not (x <= xx < x+w and y <= yy < y+h and (xx in (x, x+w-1) or yy in (y, y+h-1))):
                    raise InvalidPatch('door must be on its room perimeter')
                put(xx, yy, C.PATH,command.get('door_surface',''))


def dress(region):
    """Seeded visual-only dressing. Never add collision, loot or gameplay rules."""
    if not region.get('scene') or not region.get('visuals'):return
    art=region['visuals'];explicit=[p for p in region.get('props',[]) if not p.get('scenery_auto')]
    sprites=art.get('sprites',{});choices=[k for k in art.get('scenery',[]) if k in sprites]
    from .materials import definitions
    material_defs=definitions()
    from .library import catalog
    placements={k:catalog().get(sprites[k].get('asset'),{}).get('placement','ground') for k in choices}
    legacy={asset:m['tiles'] for m in material_defs.values() for asset in m.get('legacy_assets',[])}
    surface_roles={k:(s.get('tiles',[]) if 'material' in s else legacy.get(s.get('asset'),[])) for k,s in sprites.items()}
    no_dressing={k for k,s in sprites.items() if 'material' in s and not s.get('dressing',True)}
    objects=region.get('entities',[])+explicit
    signature=C.stable_seed('dressing-v2',region['seed'],json.dumps([region['tiles'],region.get('surfaces',[]),art.get('scenery',[]),art.get('density',0),
        [[e.get('id'),e['x'],e['y'],e.get('footprint'),e.get('spent')] for e in objects],
        {k:sprites[k].get('size',[16,16]) for k in choices},surface_roles,sorted(no_dressing),placements],sort_keys=True))
    if region.get('dressing_signature')==signature:return
    region['dressing_signature']=signature;region['props']=explicit
    density=art.get('density',.045)
    if not choices or density<=0:return
    w,h=region['width'],region['height'];reserved=set()
    def ground(x,y):
        if not (0<=x<w and 0<=y<h):return False
        tile=region['tiles'][y][x]
        if tile not in (C.GROUND,C.PATH):return False
        skins=region.get('surfaces',[])
        skin=skins[y][x] if skins else ''
        if skin in no_dressing:return False
        roles=surface_roles.get(skin,[])
        # Older models sometimes label an entire indoor floor PATH, or a road
        # GROUND. Use an explicit material role when available; never block it.
        if roles:return C.GROUND in roles
        return tile==C.GROUND
    for e in objects+[dict(x=region['spawn'][0],y=region['spawn'][1])]:
        if e.get('spent'):continue
        for x,y in cells_for(e):
            reserved.update((x+dx,y+dy) for dy in range(-1,2) for dx in range(-1,2))
    for key,(x,y) in region.get('scene',{}).get('anchors',{}).items():
        if key.startswith('link_') or key=='chapter_gate':reserved.update((x+dx,y+dy) for dy in range(-1,2) for dx in range(-1,2))
    candidates=[]
    for y in range(h):
        for x in range(w):
            roll=C.stable_seed(region['seed'],'decoration',x,y)
            if (roll%10000)/10000 < density:candidates.append((roll,x,y))
    count=0
    for roll,x,y in sorted(candidates):
        if count>=192:break
        key=choices[(roll//10000)%len(choices)];sw,sh=sprites[key].get('size',[16,16])
        # Match renderer's bottom-center visual bounds, not just a one-cell anchor.
        left=math.floor(x+.5-sw/32);right=math.ceil(x+.5+sw/32);top=math.floor(y+1-sh/16)
        area={(xx,yy) for yy in range(top,y+1) for xx in range(left,right)}
        if area & reserved:continue
        if placements[key]=='wall_front':
            if not ground(x,y+1) or any(not (0<=xx<w and 0<=yy<h) or region['tiles'][yy][xx]!=C.WALL for xx,yy in area):continue
        elif any(not ground(xx,yy) for xx,yy in area):continue
        region['props'].append(dict(id=f'{region["id"]}:__scenery_{x}_{y}',kind='decoration',sprite=key,x=x,y=y,solid=False,scenery_auto=True))
        reserved.update(area);count+=1


def validate_space(region, player=None, full=False):
    """Geometry and escape checks, not a claim to prove arbitrary puzzles solvable."""
    from .pcg import reachable
    w, h = region['width'], region['height']
    for obj in region['entities'] + region.get('props', []):
        if obj.get('spent'): continue
        for x, y in cells_for(obj):
            if not 0 <= x < w or not 0 <= y < h:
                raise InvalidPatch('object footprint is outside map: ' + obj.get('id', obj.get('kind', '?')))
    start = [player['x'], player['y']] if player else region['spawn']
    if not (0 <= start[0] < w and 0 <= start[1] < h) or region['tiles'][start[1]][start[0]] in C.BLOCKED:
        raise InvalidPatch('player/spawn is in blocked terrain')
    if solid_at(region, *start): raise InvalidPatch('solid object overlaps player/spawn')
    # Dynamic objects can be doors; do not erase their puzzle to auto-connect them.
    area = reachable(region['tiles'], start)
    gates = [e for e in region['entities'] if e['kind'] == 'exit']
    if gates and not any((g['x'], g['y']) in area for g in gates):
        raise InvalidPatch('scene leaves no structurally reachable exit')
    if full:
        errors=[]
        for index,obj in enumerate(region['entities']):
            footprint=set(cells_for(obj))
            approach={(x+dx,y+dy) for x,y in footprint for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))}-footprint
            if not obj.get('solid'):approach |= footprint
            if not area.intersection(approach):
                loc=f'region.entities[{index}].at' if 'at' in obj else 'region.scene.anchors.'+obj.get('anchor_key',obj.get('local_id',obj['id']))
                errors.append(issue(loc,'no approach to object '+obj['id'],category='gameplay',
                    value={'anchor':[obj['x'],obj['y']],'footprint':obj.get('footprint',[1,1])},
                    expected='at least one reachable cell along the object footprint boundary'))
        for obj in region.get('props', []):
            if obj.get('solid') and any((g['x'], g['y']) in cells_for(obj) for g in gates):
                raise InvalidPatch('scenery covers an exit')
        if errors:raise InvalidPatch(issues=errors)


def build(plan, rid, seed, depth, exits):
    scene = plan['scene']; w, h = scene['size']
    region = dict(id=rid, name=plan['name'], description=plan['description'], biome=plan['biome'],
                  layout=plan['layout'], weather=plan['weather'], rule=plan['rule'], depth=depth,
                  seed=seed, width=w, height=h, tiles=[[scene['base']] * w for _ in range(h)],
                  props=[], entities=[], spawn=list(scene['spawn']), visits=0, revision=0,
                  surface_version=2,scene=copy.deepcopy(scene), program=copy.deepcopy(plan.get('program', {})))
    if 'visuals' in plan: region['visuals'] = copy.deepcopy(plan['visuals'])
    if 'audio' in plan:region['audio']=copy.deepcopy(plan['audio'])
    if 'module_sources' in plan:region['module_sources']=copy.deepcopy(plan['module_sources'])
    from .library import usage
    region['library_usage']=usage(plan)
    paint(region, scene['paint'])
    anchors = scene['anchors']
    occupied = set()
    for raw in plan.get('landmarks', []):
        key = raw.get('id', raw['type'])
        pos = raw.get('at', anchors.get(key))
        if pos is None: raise InvalidPatch('scene needs anchor for landmark ' + key)
        prop = dict(raw, id=rid+':'+key, local_id=key, kind=raw['type'], x=pos[0], y=pos[1])
        region['props'].append(prop)
    for raw in plan['entities']:
        pos = raw.get('at', anchors.get(raw['id']))
        if pos is None: raise InvalidPatch('scene needs anchor for entity ' + raw['id'])
        e = copy.deepcopy(raw)
        e.update(id=rid+':'+raw['id'], local_id=raw['id'], x=pos[0], y=pos[1], spent=False)
        e.setdefault('solid', e['kind'] in ('enemy', 'npc'))
        local_items={item['id'] for item in plan.get('items',[])}
        if e['kind'] == 'chest' and ':' not in e['item_id'] and (e['item_id'] in local_items or e['item_id'] not in C.BASE_ITEMS): e['item_id'] = rid+':'+e['item_id']
        if tuple(pos) in occupied: raise InvalidPatch('entities share a scene anchor')
        occupied.add(tuple(pos)); region['entities'].append(e)
    forward = 0
    for n, link in enumerate(exits):
        key = link.get('anchor') or ('back' if link['direction'] == 'back' else f'forward_{forward}')
        if link['direction'] != 'back': forward += 1
        pos = anchors.get(key)
        if pos is None: raise InvalidPatch('scene needs exit anchor '+key,path='region.scene.anchors.'+key,
                                           expected=f'a free reachable [x,y] for {link["label"]}, within {w}x{h}')
        if tuple(pos) in occupied:
            collision=next(e['id'] for e in region['entities'] if [e['x'],e['y']]==list(pos))
            raise InvalidPatch('exit overlaps another entity '+collision,path='region.scene.anchors.'+key,
                               category='gameplay',value=pos,expected='a distinct free portal cell')
        occupied.add(tuple(pos))
        region['entities'].append(dict(id=f'{rid}:gate_{n}', kind='exit', name=link['label'],
            x=pos[0], y=pos[1], target=link['target'], direction=link['direction'], anchor_key=key, spent=False, solid=False))
        if 'link_id' in link:region['entities'][-1]['link_id']=link['link_id']
    validate_space(region, full=True)
    dress(region)
    return region
