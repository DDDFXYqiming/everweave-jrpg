"""Executable content grammar, not a catalogue of ready-made quests.

Everything here is data: bounded expressions, effects and event handlers. No Python,
GDScript, filesystem access, imports, network calls or eval are exposed to a model.
"""
import copy
import math
import re

from .schema import InvalidPatch, obj, text, ident, arr
from .diagnostics import checked

OPS = {
    'add': (2, 8), 'sub': (2, 2), 'mul': (2, 8), 'div': (2, 2),
    'mod': (2, 2), 'min': (1, 8), 'max': (1, 8), 'abs': (1, 1),
    'eq': (2, 2), 'ne': (2, 2), 'lt': (2, 2), 'le': (2, 2),
    'gt': (2, 2), 'ge': (2, 2), 'and': (1, 8), 'or': (1, 8),
    'not': (1, 1), 'concat': (1, 8), 'inside': (6, 6),
}
EVENTS = {'enter', 'move', 'wait', 'interact', 'choice', 'victory',
          'turn_start', 'enemy_turn', 'turn_end', 'tick', 'invoke', 'use'}
TILES = {'ground': 0, 'path': 1, 'water': 2, 'wall': 3, 'bridge': 4}


def integer(value, lo, hi, name='integer'):
    if type(value) is not int or not lo <= value <= hi:
        raise InvalidPatch(f'{name} must be an integer in {lo}..{hi}')
    return value


def boolean(value):
    if type(value) is not bool:
        raise InvalidPatch('expected boolean')
    return value


def scalar(value):
    if type(value) in (bool, int, float):
        if abs(value) > 1_000_000 or not math.isfinite(value):
            raise InvalidPatch('state value out of bounds')
        return value
    if isinstance(value, str) and len(value) <= 400:
        return value
    raise InvalidPatch('state values must be bounded JSON scalars')


def state_values(value):
    if not isinstance(value, dict) or len(value) > 64:
        raise InvalidPatch('state requires an object with at most 64 entries')
    return {ident(k): scalar(v) for k, v in value.items()}


def target(value):
    value = text(value, 'target', 160)
    if not re.fullmatch(r'[a-z][a-z0-9_:]*', value):
        raise InvalidPatch('target must be a local or canonical entity ID')
    return value


def path(value, writable=False):
    value = text(value, 'state path', 200)
    bits = value.split('.')
    if any(not re.fullmatch(r'[a-z][a-z0-9_:]*', bit) for bit in bits):
        raise InvalidPatch('invalid state path')
    valid = ((bits[0] == 'vars' and len(bits) == 2) or
             (bits[0] == 'self' and len(bits) == 3 and bits[1] == 'state') or
             (bits[0] == 'objects' and len(bits) == 4 and bits[2] == 'state'))
    if not writable:
        valid |= bits[0] in ('chapter','resources') and len(bits)==2
        valid |= (bits[0] in ('player', 'battle', 'world', 'event') and len(bits) == 2)
        valid |= (bits[0] == 'self' and len(bits) == 2)
        valid |= (bits[0] == 'objects' and len(bits) == 3)
    if not valid:
        raise InvalidPatch('unsupported state path; no arbitrary world writes')
    return value


def expression(value, depth=0):
    if depth > 10:
        raise InvalidPatch('expression nesting exceeds 10')
    if not isinstance(value, dict):
        return scalar(value)
    if set(value) == {'get'}:
        return {'get': path(value['get'])}
    if set(value) == {'item'}:
        return {'item': target(value['item'])}
    if set(value) == {'fact'}:
        return {'fact': text(value['fact'], 'fact', 200)}
    if set(value) == {'history', 'field'}:
        integer(value['history'], 0, 63, 'history offset')
        if value['field'] not in ('x', 'y'):
            raise InvalidPatch('history field must be x or y')
        return copy.deepcopy(value)
    obj(value, 'expression', ('op', 'args'), ('op', 'args'))
    if value['op'] not in OPS:
        raise InvalidPatch('unknown expression operator')
    lo, hi = OPS[value['op']]
    return {'op': value['op'], 'args': [expression(x, depth + 1)
            for x in arr(value['args'], 'arguments', hi, lo)]}


def event_name(value):
    if not isinstance(value, str) or (value not in EVENTS and not re.fullmatch(r'signal_[a-z0-9_]{1,32}', value)):
        raise InvalidPatch('unknown event; custom signals start with signal_')
    return value


def effects(value, depth=0):
    if depth > 5:
        raise InvalidPatch('effect nesting exceeds 5')
    result = []
    for raw in arr(value, 'effects', 32):
        if not isinstance(raw, dict):
            raise InvalidPatch('effect must be an object')
        op = raw.get('op')
        if op in ('set', 'change'):
            obj(raw, op, ('op', 'path', 'value'), ('op', 'path', 'value'))
            out = dict(op=op, path=path(raw['path'], True), value=expression(raw['value']))
        elif op == 'if':
            obj(raw, op, ('op', 'when', 'then', 'else'), ('op', 'when', 'then'))
            out = dict(op=op, when=expression(raw['when']), then=effects(raw['then'], depth + 1))
            out['else'] = effects(raw.get('else', []), depth + 1)
        elif op == 'stat':
            obj(raw, op, ('op', 'target', 'name', 'delta'), ('op', 'target', 'name', 'delta'))
            if raw['target'] not in ('player', 'enemy') or raw['name'] not in ('hp', 'mp', 'gold'):
                raise InvalidPatch('stat target/name not supported')
            if raw['target'] == 'enemy' and raw['name'] != 'hp':
                raise InvalidPatch('enemy supports hp only')
            out = dict(raw, delta=expression(raw['delta']))
        elif op == 'item':
            obj(raw, op, ('op', 'id', 'count'), ('op', 'id', 'count'))
            out = dict(op=op, id=target(raw['id']), count=expression(raw['count']))
        elif op == 'move':
            obj(raw, op, ('op', 'target', 'to'), ('op', 'target', 'to'))
            out = dict(op=op, target=target(raw['target']), to=[expression(x) for x in arr(raw['to'], 'position', 2, 2)])
        elif op in ('sprite', 'solid', 'remove'):
            fields = ('op', 'target') if op == 'remove' else ('op', 'target', 'value')
            obj(raw, op, fields, fields)
            out = dict(op=op, target=target(raw['target']))
            if op != 'remove':
                out['value'] = ident(raw['value']) if op == 'sprite' else expression(raw['value'])
        elif op == 'chapter':
            obj(raw,op,('op','key','value'),('op','key','value'))
            out=dict(op=op,key=ident(raw['key']),value=expression(raw['value']))
        elif op == 'resource':
            obj(raw,op,('op','id','delta'),('op','id','delta'))
            out=dict(op=op,id=ident(raw['id']),delta=expression(raw['delta']))
        elif op == 'paint':
            obj(raw, op, ('op', 'rect', 'tile', 'surface'), ('op', 'rect', 'tile'))
            out = dict(op=op, rect=[expression(x) for x in arr(raw['rect'], 'rect', 4, 4)], tile=tile(raw['tile']))
            if 'surface' in raw: out['surface'] = ident(raw['surface'])
        elif op == 'end_battle':
            obj(raw, op, ('op', 'result'), ('op', 'result'))
            if raw['result'] not in ('victory', 'escape'): raise InvalidPatch('invalid battle outcome')
            out = dict(raw)
        elif op == 'message':
            obj(raw, op, ('op', 'text'), ('op', 'text'))
            out = dict(op=op, text=expression(raw['text']))
        elif op in ('sound','music'):
            obj(raw,op,('op','cue'),('op','cue'))
            out=dict(op=op,cue=ident(raw['cue']))
        elif op == 'emit':
            obj(raw, op, ('op', 'event'), ('op', 'event'))
            out = dict(op=op, event=event_name(raw['event']))
            if not out['event'].startswith('signal_'): raise InvalidPatch('emit only custom signals')
        elif op == 'timer':
            obj(raw, op, ('op', 'id', 'after', 'event'), ('op', 'id', 'after', 'event'))
            out = dict(op=op, id=ident(raw['id']), after=integer(raw['after'], 1, 1000), event=event_name(raw['event']))
            if not out['event'].startswith('signal_'): raise InvalidPatch('timer only custom signals')
        else:
            raise InvalidPatch('unknown effect ' + str(op))
        result.append(out)
    return result


def program(value):
    obj(value, 'program', ('summary', 'vars', 'actions', 'hooks', 'objectives'))
    result = dict(summary=text(value.get('summary', '交互规则'), 'program summary', 300),
                  vars=state_values(value.get('vars', {})), actions=[], hooks=[], objectives=[])
    for raw in arr(value.get('actions', []), 'actions', 32):
        obj(raw, 'action', ('id', 'label', 'target', 'scope', 'when', 'effects', 'once', 'description', 'blocked_hint'), ('id', 'label', 'effects'))
        scope = raw.get('scope', 'explore')
        if scope not in ('explore', 'combat'): raise InvalidPatch('scope must be explore or combat')
        result['actions'].append(dict(id=ident(raw['id']), label=text(raw['label'], 'action label', 64),
            description=text(raw.get('description', raw['label']), 'action description', 200),
            target=target(raw.get('target', 'player')), scope=scope, when=expression(raw.get('when', True)),
            effects=effects(raw['effects']), once=boolean(raw.get('once', False))))
        if 'blocked_hint' in raw:result['actions'][-1]['blocked_hint']=text(raw['blocked_hint'],'blocked hint',200)
    for raw in arr(value.get('hooks', []), 'hooks', 32):
        obj(raw, 'hook', ('id', 'on', 'target', 'when', 'effects', 'once'), ('id', 'on', 'effects'))
        result['hooks'].append(dict(id=ident(raw['id']), on=event_name(raw['on']), target=target(raw.get('target', 'player')), when=expression(raw.get('when', True)),
            effects=effects(raw['effects']), once=boolean(raw.get('once', False))))
    for raw in arr(value.get('objectives', []), 'objectives', 12):
        obj(raw, 'objective', ('id', 'name', 'description', 'when', 'fail_when', 'reward'), ('id', 'name', 'when'))
        result['objectives'].append(dict(id=ident(raw['id']), name=text(raw['name'], 'objective name', 64),
            description=text(raw.get('description', raw['name']), 'objective description', 300),
            when=expression(raw['when']), fail_when=expression(raw.get('fail_when', False)), reward=effects(raw.get('reward', []))))
    for field in ('actions', 'hooks', 'objectives'):
        ids = [x['id'] for x in result[field]]
        if len(ids) != len(set(ids)): raise InvalidPatch('duplicate program ' + field)
    # Bound total syntax size, including nested branches; execution has an independent gas limit.
    def count(node):
        if isinstance(node, dict): return 1 + sum(count(x) for x in node.values())
        if isinstance(node, list): return 1 + sum(count(x) for x in node)
        return 1
    if count(result) > 6500: raise InvalidPatch('program is too large')
    return result


def tile(value):
    if isinstance(value, str) and value in TILES: return TILES[value]
    if isinstance(value,str):
        raise InvalidPatch('unsupported tile type',value=value,expected='ground/path/water/wall/bridge; material belongs in visuals.terrain or a surface recipe')
    return integer(value, 0, 4, 'tile')


def point(value, width, height):
    p = arr(value, 'point', 2, 2)
    return [integer(p[0], 0, width - 1, 'x'), integer(p[1], 0, height - 1, 'y')]


def paint_commands(value, width, height):
    result = []
    for raw in arr(value, 'scene paint', 96):
        obj(raw, 'paint command', ('rect', 'room', 'line', 'width', 'tile', 'surface', 'doors','wall_surface','door_surface'), ('tile',))
        shapes = set(raw) & {'rect', 'room', 'line'}
        if len(shapes) != 1: raise InvalidPatch('paint needs exactly one rect, room or line')
        shape = next(iter(shapes)); out = dict(tile=tile(raw['tile']))
        if shape in ('rect', 'room'):
            rect = arr(raw[shape], shape, 4, 4)
            x, y = point(rect[:2], width, height)
            w = integer(rect[2], 1, width - x); h = integer(rect[3], 1, height - y)
            if shape == 'room' and min(w, h) < 3: raise InvalidPatch('room too small')
            out[shape] = [x, y, w, h]
        else:
            out['line'] = [point(p, width, height) for p in arr(raw['line'], 'line', 20, 2)]
            out['width'] = integer(raw.get('width', 1), 1, 6)
        if 'surface' in raw: out['surface'] = ident(raw['surface'])
        for field in ('wall_surface','door_surface'):
            if field in raw:
                if shape!='room':raise InvalidPatch(field+' requires a room command')
                out[field]=ident(raw[field])
        if 'doors' in raw:
            if shape != 'room': raise InvalidPatch('doors require room')
            out['doors'] = [point(p, width, height) for p in arr(raw['doors'], 'doors', 8)]
        result.append(out)
    return result


def scene(value):
    obj(value, 'scene', ('size', 'spawn', 'base', 'paint', 'anchors', 'summary'), ('size', 'spawn', 'paint', 'anchors'))
    # Report independent tile mistakes together instead of consuming a complete
    # model repair just to reveal the next material/collision-type mix-up.
    errors=[]
    tile_fields=[('base',value.get('base','ground'))]
    if isinstance(value['paint'],list):
        tile_fields.extend((f'paint[{i}].tile',command['tile']) for i,command in enumerate(value['paint']) if isinstance(command,dict) and 'tile' in command)
    for location,raw in tile_fields:
        try:checked(location,tile,raw)
        except InvalidPatch as exc:errors.extend(exc.issues)
    if errors:raise InvalidPatch(issues=errors)
    size = arr(value['size'], 'scene size', 2, 2)
    w, h = integer(size[0], 16, 96), integer(size[1], 12, 72)
    anchors = value['anchors']
    if not isinstance(anchors, dict) or len(anchors) > 64: raise InvalidPatch('invalid scene anchors')
    result = dict(size=[w, h], spawn=point(value['spawn'], w, h), base=tile(value.get('base', 'ground')),
                  paint=paint_commands(value['paint'], w, h), anchors={}, summary=text(value.get('summary', '空间设计'), 'scene summary', 300))
    for name, pos in anchors.items():
        if name not in ('back', 'forward_0', 'forward_1', 'forward_2', 'forward_3'): target(name)
        result['anchors'][name] = point(pos, w, h)
    return result


def entity_extensions(raw, out):
    if 'at' in raw: out['at'] = point(raw['at'], 96, 72)
    if 'solid' in raw: out['solid'] = boolean(raw['solid'])
    if 'state' in raw: out['state'] = state_values(raw['state'])
    if 'description' in raw: out['description'] = text(raw['description'], 'object description', 300)
    if 'footprint' in raw:
        label=out.get('id',raw.get('id',out.get('type','object')))
        out['footprint'] = [integer(x, 1, 8, f"entity {label}.footprint[{i}]") for i,x in enumerate(arr(raw['footprint'], 'footprint', 2, 2))]
    if 'stats' in raw:
        obj(raw['stats'], 'enemy stats', ('hp', 'attack'), ('hp',))
        out['stats'] = dict(hp=integer(raw['stats']['hp'], 1, 2000), attack=integer(raw['stats'].get('attack', 8), 0, 200))
    return out


def item_use(value):
    obj(value, 'item.use', ('label', 'when', 'effects', 'consume'), ('effects',))
    return dict(label=text(value.get('label', '使用'), 'use label', 40), when=expression(value.get('when', True)),
                effects=effects(value['effects']), consume=integer(value.get('consume', 1), 0, 1))
