import copy
import hashlib
import itertools
import json
import pickle
import re
from collections import OrderedDict, deque
from .diagnostics import InvalidPatch, issue

LIMIT = 3000
COMBAT_TURNS = 60
PLAYER_NOISE = ('x', 'y', 'facing', 'hp', 'mp', 'xp')


def check_region(world, parsed, context):
    from .campaign import chapter
    from .playability import clone
    rid = context['target']
    if not chapter(world.state, rid):
        return dict(status='not_applicable')
    probe = clone(world)
    try:
        probe._apply_patch(None, context, _validated=copy.deepcopy(parsed))
        return Search(probe, rid).run()
    finally:
        probe.store.close()


def written(node, key):
    if isinstance(node, list):
        for v in node:
            yield from written(v, key)
    elif isinstance(node, dict):
        if node.get('op') == 'chapter' and node.get('key') == key and not isinstance(node.get('value'), (dict, list)):
            yield node['value']
        for v in node.values():
            yield from written(v, key)


class Search:
    def __init__(self, probe, rid):
        from .campaign import chapter, promised_values
        self.probe, self.rid = probe, rid
        c = chapter(probe.state, rid)
        self.cid = c['id']
        jobs = {f for j in (probe.state.get('adventure') or {}).get('jobs', {}).values() if j['region'] == rid for f in j.get('flag_writes', [])}
        promised = promised_values(probe.state, c)
        self.flags = {k: sorted(promised.get(k, ()), key=repr) for k, v in c['flag_sources'].items() if v == rid and k not in jobs}
        self.items = {v['region'] + ':' + k: v['count'] for k, v in c['item_sources'].items() if v['region'] == rid}
        self.requirements = [('item', k, n) for k, n in self.items.items()] + [('flag', k, v) for k, values in self.flags.items() for v in values]
        self.inputs = self.foreign(c)
        self.error = None

    def foreign(self, c):
        from .campaign import graph_from_state, promised_values
        from .progression import explore
        s = self.probe.state
        region = self.probe.region(self.rid)
        read = set(re.findall(r'"chapter\.(\w+)"', json.dumps([region.get('program', {}), region.get('scenes', [])], ensure_ascii=False)))
        read |= {v['flag'] for e in c['links'] if self.rid in (e['a'], e['b']) for v in e['requires'] + e['discover'] if 'flag' in v}
        read = {k for k in read if k in c['flags'] and c['flag_sources'].get(k) != self.rid}
        if s['campaign']['active'] != self.cid:
            return dict(items={}, abilities=set(), flags={k: [c['flags'][k]] for k in sorted(read)})
        graph = graph_from_state(s)
        graph = dict(graph, flag_sources={k: ('' if v == self.rid else v) for k, v in graph['flag_sources'].items()},
                     items={k: dict(v, region='' if v['region'] == self.rid else v['region']) for k, v in graph['items'].items()})
        found = explore(graph)
        flag_keys, item_keys, _ = found['keys']
        items, abilities, flags = {}, set(), {k: {c['flags'][k]} for k in read}
        reached = {state[0] for state in found['order']}
        promised = promised_values(s, c)
        for key in read:
            source = c['flag_sources'][key]
            if source not in reached:
                continue
            flags[key] |= promised.get(key, set())
            if s['topology'][source]['ready']:
                flags[key] |= set(written(self.probe.region(source).get('program', {}), key))
            elif type(c['flags'][key]) is bool:
                flags[key].add(not c['flags'][key])
        for state in found['order']:
            for key, count in zip(item_keys, state[2]):
                inventory = graph['items'][key]['region'] + ':' + key
                if graph['items'][key]['region'] and count:
                    items[inventory] = max(items.get(inventory, 0), count)
            abilities |= state[3]
            for key, value in zip(flag_keys, state[1]):
                if key in flags:
                    flags[key].add(value)
        return dict(items=items, abilities=abilities, flags={k: [c['flags'][k]] + sorted(v - {c['flags'][k]}, key=repr) for k, v in sorted(flags.items())})

    def save(self):
        return pickle.dumps((self.probe.state, self.probe.region(self.rid)), pickle.HIGHEST_PROTOCOL)

    def load(self, snapshot):
        state, region = pickle.loads(snapshot)
        self.probe.state = state
        self.probe.cache = OrderedDict([(self.rid, region)])

    def act(self, action):
        from .world import GameError
        try:
            self.probe.action(copy.deepcopy(action))
            return True
        except (GameError, InvalidPatch) as exc:
            if self.error is None and not isinstance(exc, GameError) and action['op'] != 'move':
                self.error = f'{action} → {exc}'
            return False

    def starts(self):
        from . import gameplay
        p, s = self.probe.state['player'], self.probe.state
        for key, count in self.inputs['items'].items():
            p['inventory'][key] = max(p['inventory'].get(key, 0), count)
        p['abilities'] = sorted(set(p.get('abilities', [])) | self.inputs['abilities'])
        if s['current'] == self.rid:
            return [(self.save(), '开局位于本地区')]
        region = self.probe.region(self.rid)
        self.probe._enter_content(region)
        s['topology'][self.rid]['visited'] = True
        keys = list(self.inputs['flags'])
        combos = list(itertools.product(*self.inputs['flags'].values()))
        if len(combos) > 64:
            combos = [tuple(s['campaign']['chapters'][self.cid]['flags'][k] for k in keys)]
        base = self.save()
        result = []
        for combo in combos:
            self.load(base)
            self.probe.state['campaign']['chapters'][self.cid]['flags'].update(zip(keys, combo))
            self.probe.persist()
            outside = self.save()
            for x, y, name in self.entries():
                self.load(outside)
                region = self.probe.region(self.rid)
                s = self.probe.state
                s['current'] = self.rid
                s['player'].update(x=x, y=y)
                s['ui'] = {}
                s['battle'] = None
                gameplay.transaction(self.probe, lambda: gameplay.enter(self.probe, region))
                result.append((self.save(), '从' + name + '进入' + ('（' + '，'.join(f'{k}={v!r}' for k, v in zip(keys, combo)) + '）' if keys else '')))
        return result

    def entries(self):
        region = self.probe.region(self.rid)
        return [(e['x'], e['y'], e['name']) for e in region['entities'] if e['kind'] == 'exit' and not e.get('spent') and not e.get('locked')]

    def key(self):
        from .scene import routes_from
        s = self.probe.state
        r = self.probe.region(self.rid)
        p = s['player']
        adv = s.get('adventure') or {}
        c = s['campaign']['chapters'][self.cid]
        runtime = {k: v for k, v in r.get('runtime', {}).items() if k not in ('clock', 'history', 'timers')}
        runtime['used'] = sorted(runtime.get('used', []))
        runtime['timers'] = sorted(t.get('id', '') for t in r.get('runtime', {}).get('timers', []))
        view = dict(
            place=min(routes_from(r, (p['x'], p['y']))),
            player={k: v for k, v in p.items() if k not in PLAYER_NOISE and k != 'inventory'},
            inventory={k: n for k, n in p['inventory'].items() if n},
            chapter=[c['flags'], [e['revealed'] for e in c['links']], c['complete']],
            foreign={k: c['flags'][k] for k in self.inputs['flags']},
            quests={k: q['status'] for k, q in s['quests'].items()},
            missions={k: [m['status'], m.get('discovered')] for k, m in adv.get('missions', {}).items()},
            cast={k: a['state'] for k, a in adv.get('cast', {}).items()},
            facts=sorted(k for k in s['facts'] if not k.startswith('visited:')),
            runtime=runtime,
            entities=[(e['id'], None if e['kind'] == 'enemy' else (e['x'], e['y']), e.get('spent'), e.get('solid'), e.get('locked'), e.get('sprite')) for e in r['entities']],
            props=[(e.get('id'), e.get('x'), e.get('y'), e.get('spent'), e.get('solid')) for e in r.get('props', [])],
            tiles=r['tiles'],
            over=bool(s.get('game_over')))
        return hashlib.blake2b(json.dumps(view, sort_keys=True, default=str, ensure_ascii=False).encode(), digest_size=16).digest()

    def won(self):
        adv = self.probe.state.get('adventure') or {}
        return bool(self.probe.state.get('game_over')) and any(e['final'] and e['shown'] for e in adv.get('endings', {}).values())

    def met(self):
        s = self.probe.state
        if self.won():
            return frozenset(range(len(self.requirements)))
        flags = s['campaign']['chapters'][self.cid]['flags']
        inventory = s['player']['inventory']
        return frozenset(i for i, (kind, k, v) in enumerate(self.requirements) if (inventory.get(k, 0) >= v if kind == 'item' else flags[k] == v))

    def settle(self, depth=0):
        s = self.probe.state
        for _ in range(COMBAT_TURNS):
            if not s['battle']:
                break
            self.fight()
            s = self.probe.state
        if s.get('game_over'):
            return [(self.save(), '抵达最终结局')] if self.won() else []
        if s['battle']:
            return []
        ui = s['ui']
        kind = ui.get('kind')
        if not kind:
            return [(self.save(), '')]
        options = []
        if kind == 'actions':
            options = [(dict(op='content_action', id=a['id']), a['label']) for a in ui.get('actions', []) if a.get('enabled', True)]
        elif kind == 'dialogue':
            options = [(dict(op='choice', id=c['id']), c.get('text', c['id'])) for c in ui.get('choices', [])]
        elif kind == 'shop':
            options = [(dict(op='buy', id=g['id']), '购买' + g['name']) for g in ui.get('goods', []) if s['player']['gold'] >= g['price']]
        if depth > 6:
            options = []
        base = self.save()
        result = []
        for action, label in options:
            self.load(base)
            if self.act(action):
                result += [(snap, '选「' + label + '」' + ('，' + more if more else '')) for snap, more in self.settle(depth + 1)]
        self.load(base)
        if self.act(dict(op='close')):
            result += self.settle(depth + 1) if self.probe.state['ui'] != ui else []
        return result

    def fight(self):
        from .runtime import Runtime
        s = self.probe.state
        r = self.probe.region(self.rid)
        moves = ['attack']
        if s['battle'].get('authored'):
            moves = ['rule:' + a['id'] for a in Runtime(self.probe, r).available(scope='combat') if a['enabled']]
        if not any(self.act(dict(op='combat', move=m)) for m in moves):
            self.act(dict(op='combat', move='flee'))

    def moves(self):
        from .gameplay import item_availability
        from .runtime import Runtime
        from .scene import routes_from, path_to, interaction_cells
        s = self.probe.state
        r = self.probe.region(self.rid)
        p = s['player']
        previous = routes_from(r, (p['x'], p['y']))
        leave = False
        for e in r['entities']:
            if e.get('spent'):
                continue
            path = path_to(previous, interaction_cells(e))
            if path is None:
                continue
            if e['kind'] == 'exit':
                leave = leave or not e.get('locked')
                continue
            yield 'walk', (path, e['id']), '与' + e['name'] + '互动'
        for a in Runtime(self.probe, r).available(scope='explore'):
            if a['target'] == 'player' and a['enabled']:
                yield 'act', dict(op='invoke', id=a['id']), a['label']
        for key, count in p['inventory'].items():
            item = s['items'].get(key, {})
            if count > 0 and item.get('use') and item_availability(self.probe, item)['enabled']:
                yield 'act', dict(op='use', id=key), '使用' + item['name']
        if leave:
            yield 'leave', None, ''
            for x, y, name in self.entries():
                yield 'enter', (x, y), '离开后从' + name + '重新进入'
            c = s['campaign']['chapters'][self.cid]
            for key, values in self.inputs['flags'].items():
                for value in values[1:]:
                    if c['flags'][key] != value:
                        yield 'flag', (key, value), f'在外地把旗标 {key} 推进为 {value!r}'

    def perform(self, kind, data):
        s = self.probe.state
        if kind == 'act':
            return self.settle() if self.act(data) else []
        if kind == 'enter':
            s['player'].update(x=data[0], y=data[1])
            return [(self.save(), '')]
        if kind == 'flag':
            s['campaign']['chapters'][self.cid]['flags'][data[0]] = data[1]
            self.probe.persist(self.probe.region(self.rid))
            return [(self.save(), '')]
        path, target = data
        at = (s['player']['x'], s['player']['y'])
        for point in path:
            if not self.act(dict(op='move', dx=point[0] - at[0], dy=point[1] - at[1])):
                return []
            s = self.probe.state
            if s['ui'] or s['battle']:
                return self.settle()
            if (s['player']['x'], s['player']['y']) != point:
                return []
            at = point
        if not self.act(dict(op='interact', id=target)):
            return []
        return self.settle()

    def run(self):
        nodes, parent, edges, met, leaves = {}, {}, {}, {}, set()
        queue = deque()
        for snapshot, label in self.starts():
            self.load(snapshot)
            for snap, more in self.settle():
                self.load(snap)
                k = self.key()
                if k not in nodes:
                    nodes[k], parent[k], met[k] = snap, (None, label + ('，' + more if more else '')), self.met()
                    queue.append(k)
        while queue:
            k = queue.popleft()
            self.load(nodes[k])
            edges[k] = set()
            if self.won():
                leaves.add(k)
                continue
            for kind, data, label in list(self.moves()):
                if kind == 'leave':
                    leaves.add(k)
                    continue
                self.load(nodes[k])
                for snap, more in self.perform(kind, data):
                    self.load(snap)
                    n = self.key()
                    edges[k].add(n)
                    if n not in nodes:
                        if len(nodes) >= LIMIT:
                            raise self.reject(f'地区内状态搜索超过 {LIMIT} 个状态上限，无法证明本地区兑现章节承诺；减少相互独立的开关、可重复动作或随机巡逻，让谜题状态更少')
                        nodes[n], parent[n], met[n] = snap, (k, label + ('，' + more if more else '')), self.met()
                        queue.append(n)

        def path(k):
            steps = []
            while k is not None:
                k, label = parent[k]
                steps.append(label)
            return ' → '.join(steps[::-1])

        incoming = {}
        for k, nexts in edges.items():
            for n in nexts:
                incoming.setdefault(n, set()).add(k)

        def closure(goals):
            alive = set(goals)
            queue = deque(goals)
            while queue:
                for prev in incoming.get(queue.popleft(), ()):
                    if prev not in alive:
                        alive.add(prev)
                        queue.append(prev)
            return alive

        names = [self.describe(q) for q in self.requirements]
        held = set().union(*met.values()) if met else set()
        missing = [names[i] for i in range(len(self.requirements)) if i not in held]
        if missing:
            raise self.reject(f'地区内容没有兑现章节承诺：{"；".join(missing)}（已穷举 {len(nodes)} 个地区状态，外部输入：{self.inputs_text()}）。确认承诺的道具/旗标由本地区的可达交互产出，钥匙不能只放在需要它自己才能打开的门后；外地钥匙按外部输入里的完整 ID（地区:道具）判断，不要在本地区重新定义同名道具')
        goals = [('离开本地区（任一可用出口）', leaves)]
        for i, q in enumerate(self.requirements):
            if q[0] == 'item':
                goals.append(('取得' + names[i], {k for k, v in met.items() if i in v}))
        for key, values in self.flags.items():
            idx = {i for i, q in enumerate(self.requirements) if q[0] == 'flag' and q[1] == key}
            if idx:
                goals.append((f'让旗标 {key} 达到承诺值 {"/".join(map(repr, values))} 之一', {k for k, v in met.items() if v & idx}))
        for name, targets in goals:
            alive = closure(targets)
            stuck = next((k for k in nodes if k not in alive), None)
            if stuck is not None:
                raise self.reject(f'地区软锁：按以下步骤行动后再也无法{name}：{path(stuck)}。检查一次性消耗的钥匙、不可逆开关和会封死道路的物件')
        return dict(status='verified', states=len(nodes), requirements=names, inputs=self.inputs_text(),
                    witness={names[i]: path(next(k for k in nodes if i in met[k])) for i in range(len(self.requirements))})

    def describe(self, q):
        kind, key, value = q
        if kind == 'item':
            return f'道具 {key.split(":", 1)[1]}×{value}'
        return f'旗标 {key}={value!r}'

    def inputs_text(self):
        parts = [f'{k}×{n}' for k, n in sorted(self.inputs['items'].items())]
        parts += ['能力 ' + a for a in sorted(self.inputs['abilities'])]
        parts += [f'旗标 {k}∈{v}' for k, v in self.inputs['flags'].items()]
        return '、'.join(parts) or '无'

    def reject(self, message):
        if self.error:
            message += f'。搜索中首个内容执行错误：{self.error}'
        return InvalidPatch(issues=[issue('region.program', message[:1600], category='gameplay')])
