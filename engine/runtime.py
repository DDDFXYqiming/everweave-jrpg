"""Gas-metered interpreter for model-authored game rules.

Programs are JSON syntax trees, never host-language scripts. One caller-owned
transaction encloses a player action, its hooks, timers and objective rewards.
"""
import copy
import math
from collections import deque
from .schema import InvalidPatch
from .content import scalar, path
from .scene import cells_for, solid_at, paint, validate_space
from . import catalog as C


class RuleError(InvalidPatch):
    pass


def install(region, spec=None):
    if spec is not None:
        old = region.setdefault('program', {})
        if old and spec:
            old['summary'] = spec.get('summary', old.get('summary', ''))
            old.setdefault('vars', {}).update({k: v for k, v in spec.get('vars', {}).items()
                                              if k not in old.get('vars', {})})
            for key in ('actions', 'hooks', 'objectives'):
                entries = {v['id']: v for v in old.get(key, [])}
                # New definitions may be added, but existing commitments are immutable.
                for value in spec.get(key, []):
                    if value['id'] in entries and entries[value['id']] != value:
                        raise RuleError('cannot replace an installed definition: ' + value['id'])
                    entries[value['id']] = copy.deepcopy(value)
                if len(entries) > (64 if key != 'objectives' else 32):
                    raise RuleError('installed program capacity reached')
                old[key] = list(entries.values())
        else:
            region['program'] = copy.deepcopy(spec)
    state = region.setdefault('runtime', dict(vars={}, used=[], done={}, timers=[], clock=0, history=[]))
    for key, value in region.get('program', {}).get('vars', {}).items():
        state['vars'].setdefault(key, value)
    if len(state['vars']) > 128:
        raise RuleError('too many runtime variables')
    return state


class Runtime:
    def __init__(self, world, region, event=None, actor='player'):
        self.world, self.region = world, region
        self.s = world.state
        self.rt = install(region)
        self.event = event or {}
        self.actor = actor
        self.gas = 4096
        self.queue = deque()
        self.messages = []
        self.changed = False
        self.end_result = None

    def spend(self, amount=1):
        self.gas -= amount
        if self.gas < 0:
            raise RuleError('rule execution budget exceeded; action rolled back')

    def entity(self, name):
        if name == 'self': name = self.actor
        if name == 'player': return self.s['player']
        if name == 'enemy':
            if not self.s.get('battle'): raise RuleError('no current enemy')
            name = self.s['battle']['id']
        for obj in self.region['entities'] + self.region.get('props', []):
            if name in (obj.get('id'), obj.get('local_id'), obj.get('id','').removeprefix(self.region['id']+':')):
                if obj.get('spent'): raise RuleError('object is no longer present: ' + name)
                return obj
        raise RuleError('undefined object: ' + name)

    def item_id(self, key):
        if key in self.s['items']: return key
        candidate = self.region['id'] + ':' + key
        if candidate in self.s['items']: return candidate
        matches = [k for k in self.s['items'] if k.startswith(self.region['id']+':') and k.endswith(':'+key)]
        if len(matches) == 1: return matches[0]
        raise RuleError('undefined/ambiguous item: ' + key)

    def access(self, name, write=False):
        path(name, write)
        bits = name.split('.')
        if bits[0] == 'vars': return self.rt['vars'], bits[1]
        if bits[0] == 'self':
            obj = self.entity(self.actor)
            return (obj.setdefault('state', {}), bits[2]) if len(bits) == 3 else (obj, bits[1])
        if bits[0] == 'objects':
            obj = self.entity(bits[1])
            return (obj.setdefault('state', {}), bits[3]) if len(bits) == 4 else (obj, bits[2])
        sources = {'player': self.s['player'], 'battle': self.s.get('battle') or {},
                   'world': {'time': self.s['time'], 'steps': self.s['steps'], 'clock': self.rt['clock']},
                   'event': self.event}
        return sources[bits[0]], bits[1]

    def expr(self, value):
        self.spend()
        if not isinstance(value, dict): return scalar(value)
        if 'get' in value:
            obj, key = self.access(value['get'])
            if key not in obj:
                if value['get'].startswith(('event.', 'battle.')): return 0
                raise RuleError('undefined state path: ' + value['get'])
            return scalar(obj[key])
        if 'item' in value: return self.s['player']['inventory'].get(self.item_id(value['item']), 0)
        if 'fact' in value: return scalar(self.s['facts'].get(value['fact'], False))
        if 'history' in value:
            history = self.rt['history']
            p = history[max(0, len(history)-1-value['history'])] if history else self.s['player']
            return p[value['field']]
        op = value['op']
        if op == 'and': return all(bool(self.expr(x)) for x in value['args'])
        if op == 'or': return any(bool(self.expr(x)) for x in value['args'])
        args = [self.expr(x) for x in value['args']]
        if op == 'not': return not args[0]
        if op == 'eq': return args[0] == args[1]
        if op == 'ne': return args[0] != args[1]
        if op == 'concat': return scalar(''.join(str(x) for x in args))
        if any(type(x) not in (int, float) for x in args): raise RuleError('numeric operands required: '+op)
        if op in ('div', 'mod') and args[1] == 0: raise RuleError('division by zero')
        if op == 'add': result = sum(args)
        elif op == 'sub': result = args[0]-args[1]
        elif op == 'mul': result = math.prod(args)
        elif op == 'div': result = args[0]/args[1]
        elif op == 'mod': result = args[0]%args[1]
        elif op == 'min': result = min(args)
        elif op == 'max': result = max(args)
        elif op == 'abs': result = abs(args[0])
        elif op == 'lt': result = args[0] < args[1]
        elif op == 'le': result = args[0] <= args[1]
        elif op == 'gt': result = args[0] > args[1]
        elif op == 'ge': result = args[0] >= args[1]
        elif op == 'inside': result = args[2] <= args[0] < args[2]+args[4] and args[3] <= args[1] < args[3]+args[5]
        else: raise RuleError('unsupported expression')
        return scalar(result)

    def run(self, commands):
        for c in commands:
            self.spend(); op = c['op']
            if op in ('set', 'change'):
                obj, key = self.access(c['path'], True); value = self.expr(c['value'])
                if op == 'change':
                    if type(value) not in (int, float) or type(obj.get(key, 0)) not in (int, float):
                        raise RuleError('change needs numbers')
                    value = scalar(obj.get(key, 0)+value)
                if key not in obj and len(obj) >= 128: raise RuleError('state capacity reached')
                self.changed |= obj.get(key) != value; obj[key] = value
            elif op == 'if': self.run(c['then'] if self.expr(c['when']) else c['else'])
            elif op == 'stat':
                target = self.s['player'] if c['target'] == 'player' else self.s.get('battle')
                if target is None: raise RuleError('stat requires battle')
                value = self.expr(c['delta'])
                if type(value) not in (int, float): raise RuleError('stat delta must be numeric')
                delta = max(-2000, min(2000, int(value))); name = c['name']
                cap = target.get('max_'+name, 1_000_000)
                target[name] = max(0, min(cap, target.get(name, 0)+delta)); self.changed = True
            elif op == 'item':
                key = self.item_id(c['id']); amount = self.expr(c['count'])
                if type(amount) is not int or not -99 <= amount <= 99: raise RuleError('item count outside budget')
                inv = self.s['player']['inventory']; count = inv.get(key, 0)+amount
                if count < 0 or count > 999: raise RuleError('insufficient items or inventory cap')
                inv[key] = count; self.changed = True
            elif op == 'move':
                obj = self.entity(c['target']); x, y = [self.expr(v) for v in c['to']]
                if type(x) is not int or type(y) is not int or not (0 <= x < self.region['width'] and 0 <= y < self.region['height']):
                    raise RuleError('move outside scene')
                obj['x'], obj['y'] = x, y; self.changed = True
            elif op in ('sprite', 'solid', 'remove'):
                obj = self.entity(c['target'])
                if obj is self.s['player'] or obj.get('kind') == 'exit': raise RuleError('cannot rewrite player or engine exit')
                if op == 'sprite':
                    if c['value'] not in self.region.get('visuals', {}).get('sprites', {}): raise RuleError('undefined sprite')
                    obj['sprite'] = c['value']
                elif op == 'solid':
                    value = self.expr(c['value'])
                    if type(value) is not bool: raise RuleError('solid needs boolean')
                    obj['solid'] = value
                else: obj['spent'] = True
                self.changed = True
            elif op == 'paint':
                spec = dict(rect=[self.expr(v) for v in c['rect']], tile=c['tile'])
                if 'surface' in c: spec['surface'] = c['surface']
                self.spend(int(spec['rect'][2]*spec['rect'][3])//8)
                paint(self.region, [spec]); self.changed = True
            elif op == 'message':
                message = str(self.expr(c['text'])); self.messages.append(message)
                self.world.note(message)
            elif op == 'emit': self.queue.append({'type': c['event']})
            elif op == 'timer':
                timers = self.rt['timers']
                if len(timers) >= 32 and not any(t['id'] == c['id'] for t in timers): raise RuleError('too many timers')
                timers[:] = [t for t in timers if t['id'] != c['id']]
                timers.append(dict(id=c['id'], due=self.rt['clock']+c['after'], event=c['event']))
            elif op == 'end_battle':
                if not self.s.get('battle'): raise RuleError('no battle to finish')
                self.end_result = c['result']
            else: raise RuleError('unknown command')

    def event_data(self, name, target='player', **data):
        canonical = self.s['battle']['id'] if target == 'enemy' and self.s.get('battle') else target
        for obj in self.region['entities'] + self.region.get('props', []):
            if canonical in (obj.get('id'), obj.get('local_id')):
                canonical = obj.get('id', canonical)
                break
        return dict(type=name, target=canonical.removeprefix(self.region['id']+':'), canonical_target=canonical, **data)

    def emit(self, name, target='player', advance=False, **data):
        if advance:
            self.rt['clock'] += 1
            self.rt['history'].append({k: self.s['player'][k] for k in ('x', 'y')})
            self.rt['history'] = self.rt['history'][-64:]
        self.queue.append(self.event_data(name,target,**data))
        if advance:
            self.queue.append(self.event_data('tick'))
            due = [t for t in self.rt['timers'] if t['due'] <= self.rt['clock']]
            self.rt['timers'] = [t for t in self.rt['timers'] if t not in due]
            self.queue.extend(self.event_data(t['event']) for t in due)
        events = 0
        while self.queue:
            events += 1
            if events > 32: raise RuleError('event cascade limit exceeded')
            self.event = self.queue.popleft()
            for hook in self.region.get('program', {}).get('hooks', []):
                self.spend()
                key = 'hook:'+hook['id']
                if hook['on'] != self.event['type'] or (hook['once'] and key in self.rt['used']): continue
                self.actor = hook.get('target', 'player')
                if self.expr(hook['when']):
                    if hook['once']: self.rt['used'].append(key)
                    self.run(hook['effects'])
            self.objectives()
        self.actor = 'player'
        validate_space(self.region, self.s['player'])

    def objectives(self):
        self.actor = 'player'
        for q in self.region.get('program', {}).get('objectives', []):
            if q['id'] in self.rt['done']: continue
            if self.expr(q['fail_when']): status = 'failed'
            elif self.expr(q['when']): status = 'complete'
            else: continue
            self.rt['done'][q['id']] = status
            quest = self.s['quests'].get(self.region['id']+':'+q['id'])
            if quest is not None: quest['status'] = status
            self.s['facts']['objective:'+self.region['id']+':'+q['id']] = status
            if status == 'complete': self.run(q['reward'])
            event, _ = self.world.story('objective', ('完成：' if status == 'complete' else '未能完成：')+q['name'])
            self.world.persist(self.region, event=event)

    def available(self, target=None, scope=None):
        result = []; p = self.s['player']
        for a in self.region.get('program', {}).get('actions', []):
            if scope and a['scope'] != scope: continue
            if a['once'] and 'action:'+a['id'] in self.rt['used']: continue
            try:
                obj = self.entity(a['target']); self.actor = a['target']
                canonical = obj.get('id', 'player')
                if target and target not in (canonical, a['target']): continue
                if a['scope'] == 'explore' and obj is not p:
                    if min(abs(x-p['x'])+abs(y-p['y']) for x, y in cells_for(obj)) > 1: continue
                if a['scope'] == 'combat' and not self.s.get('battle'): continue
                enabled = bool(self.expr(a['when']))
                result.append(dict(id=a['id'], label=a['label'], description=a['description'], enabled=enabled, scope=a['scope'], target=canonical))
            except RuleError:
                continue
        self.actor = 'player'
        return result

    def invoke(self, key, scope):
        options = {a['id']: a for a in self.available(scope=scope)}
        if key not in options or not options[key]['enabled']: raise RuleError('action not available here')
        a = next(a for a in self.region['program']['actions'] if a['id'] == key)
        self.actor = a['target']; self.event = self.event_data('invoke', a['target'], action=key)
        if a['once']: self.rt['used'].append('action:'+key)
        self.run(a['effects'])
        self.emit('invoke', target=a['target'], advance=scope == 'explore', action=key)
        return a


def check_references(region, items):
    """Validate static references in definitions without executing gameplay rewards."""
    objects = {'player', 'enemy', 'self'}
    for e in region['entities']+region.get('props', []):
        if 'id' not in e: continue
        objects.update((e['id'], e.get('local_id', e['id']), e['id'].removeprefix(region['id']+':')))
    sprites = region.get('visuals', {}).get('sprites', {})
    known_items = set(items) | {k.removeprefix(region['id']+':') for k in items}
    known_items.update(k.rsplit(':',1)[-1] for k in items if k.startswith(region['id']+':'))
    def walk(node):
        if isinstance(node, list):
            for v in node: walk(v)
        elif isinstance(node, dict):
            name = node.get('get', node.get('path', ''))
            if name.startswith('objects.') and name.split('.')[1] not in objects: raise RuleError('undefined object path '+name)
            if name.startswith('vars.') and name.split('.')[1] not in region.get('runtime',{}).get('vars',region.get('program',{}).get('vars',{})):
                raise RuleError('declare variable before use: '+name)
            if node.get('op') in ('move', 'sprite', 'solid', 'remove') or 'label' in node or 'on' in node:
                if node.get('target', 'player') not in objects: raise RuleError('undefined action target')
            if 'item' in node and node['item'] not in known_items: raise RuleError('undefined item expression')
            if node.get('op') == 'item' and node['id'] not in known_items: raise RuleError('undefined item effect')
            if node.get('op') == 'sprite' and node['value'] not in sprites: raise RuleError('undefined sprite effect')
            if 'surface' in node and node['surface'] not in sprites: raise RuleError('undefined surface')
            for value in node.values(): walk(value)
    walk(region.get('program', {}))
    for item in items.values():
        if item.get('origin') == region['id']: walk(item.get('use', {}))


def design_record(plan):
    """Store compact structural signatures; labels and colors do not fake novelty."""
    import hashlib
    import json
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    aliases = {}
    def token(value):
        aliases.setdefault(value, 'id'+str(len(aliases)))
        return aliases[value]
    def structure(value, field=''):
        if isinstance(value, list): return [structure(v,field) for v in value]
        if isinstance(value, dict):
            return {k:structure(v,k) for k,v in sorted(value.items())
                    if k not in ('name','label','description','summary','text')}
        if isinstance(value,str):
            if field in ('id','target','item','sprite'): return token(value)
            if field in ('get','path'):
                parts=value.split('.')
                if parts[0]=='vars':parts[1]=token(parts[1])
                if parts[0]=='objects':parts[1]=token(parts[1])
                if 'state' in parts:parts[-1]=token(parts[-1])
                return '.'.join(parts)
            if field=='event' or field=='on':
                return 'signal_'+token(value) if value.startswith('signal_') else value
        return value
    logic = structure(plan.get('program',{}))
    scene = plan.get('scene',{})
    geometry = {k:scene[k] for k in ('size','spawn','base','paint') if k in scene}
    shapes = []
    for recipe in plan.get('visuals',{}).get('sprites',{}).values():
        shapes.append([recipe['size'],[c[:-1] for c in recipe['layers']]])
    return dict(fingerprint=digest([geometry,logic,shapes]), geometry=digest(geometry),logic=digest(logic),
                shapes=digest(shapes),name=plan['name'],space=scene.get('summary',plan['layout']),
                gameplay=plan.get('program',{}).get('summary','legacy interaction'),
                motifs=list(plan.get('visuals',{}).get('sprites',{}))[:20])
