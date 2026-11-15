from collections import deque
from .diagnostics import InvalidPatch, issue

LIMIT = 100000


def search(graph):
    from .campaign import satisfied
    regions = set(graph['regions'])
    links = [e for e in graph['links'] if e['a'] in regions and e['b'] in regions]
    flag_keys = sorted(graph['flags'])
    item_keys = sorted(graph['items'])
    mission_keys = sorted(graph['missions'])
    missions = graph['missions']
    flag_domains = {k: {graph['flags'][k]} for k in flag_keys}
    for conditions in _condition_lists(graph):
        for c in conditions:
            if 'flag' in c:
                flag_domains[c['flag']].add(c['eq'])
    flag_domains = {k: sorted(v, key=repr) for k, v in flag_domains.items()}
    finals = [e for e in graph['endings'] if e['final']]
    local = [e for e in finals if all(not missions[m]['frozen'] or missions[m]['status'] == 'complete' for m in e['requires'])]
    target = '最终结局' if local else '本章完成条件'

    def facts(state):
        _, flags, items, abilities, statuses, _, _ = state
        return dict(flags=dict(zip(flag_keys, flags)), items=dict(zip(item_keys, items)),
                    abilities=abilities, missions=dict(zip(mission_keys, statuses)))

    def settle(state):
        region, flags, items, abilities, statuses, granted, revealed = state
        notes = []
        while True:
            view = facts((region, flags, items, abilities, statuses, granted, revealed))
            changed = False
            current = dict(zip(mission_keys, statuses))
            for key in mission_keys:
                m = missions[key]
                if m['frozen'] or current[key] != 'active':
                    continue
                if m['fail_when'] and satisfied(m['fail_when'], view):
                    current[key] = 'failed'
                elif all(current[d] == 'complete' for d in m['depends']) and satisfied(m['when'], view):
                    current[key] = 'complete'
                else:
                    continue
                notes.append(f'任务 {key} {"失败" if current[key] == "failed" else "完成"}')
                changed = True
                view['missions'] = current
            statuses = tuple(current[k] for k in mission_keys)
            opened = {e['id'] for e in links if e['id'] not in revealed and satisfied(e['discover'], view)}
            if opened:
                revealed = revealed | opened
                notes.append('揭示路线 ' + '、'.join(sorted(opened)))
                changed = True
            if not changed:
                return (region, flags, items, abilities, statuses, granted, revealed), notes

    def goal(state):
        statuses = dict(zip(mission_keys, state[4]))
        if local:
            return any(all(statuses[m] == 'complete' for m in e['requires']) for e in local)
        return satisfied(graph['complete_when'], facts(state))

    def successors(state):
        region, flags, items, abilities, statuses, granted, revealed = state
        view = facts(state)
        complete = {k for k, v in view['missions'].items() if v == 'complete'}
        for e in links:
            if e['id'] not in revealed or not satisfied(e['requires'], view):
                continue
            if e['a'] == region:
                yield (e['b'], flags, items, abilities, statuses, granted, revealed), f'经 {e["id"]} 前往 {e["b"]}'
            if e['b'] == region and not e['one_way']:
                yield (e['a'], flags, items, abilities, statuses, granted, revealed), f'经 {e["id"]} 前往 {e["a"]}'
        for i, key in enumerate(flag_keys):
            if graph['flag_sources'][key] != region or not set(graph['flag_gates'].get(key, [])) <= complete:
                continue
            for value in flag_domains[key]:
                if value != flags[i]:
                    yield (region, flags[:i] + (value,) + flags[i + 1:], items, abilities, statuses, granted, revealed), f'在 {region} 把旗标 {key} 设为 {value!r}'
        for i, key in enumerate(item_keys):
            source = graph['items'][key]
            if source['region'] == region and key not in granted:
                yield (region, flags, items[:i] + (items[i] + source['count'],) + items[i + 1:], abilities, statuses, granted | {key}, revealed), f'在 {region} 取得道具 {key}×{source["count"]}'
        for job in graph['skills']:
            if job['region'] == region and 'job:' + job['id'] not in granted and set(job['requires']) <= complete:
                yield (region, flags, items, abilities | frozenset(job['skills']), statuses, granted | {'job:' + job['id']}, revealed), f'在 {region} 学会能力 {"、".join(job["skills"])}'

    inventory = graph['inventory']
    start, notes = settle((graph['start'], tuple(graph['flags'][k] for k in flag_keys), tuple(inventory.get(k, 0) for k in item_keys),
                           frozenset(graph['abilities']), tuple(missions[k]['status'] for k in mission_keys),
                           frozenset(graph['granted']), frozenset(e['id'] for e in links if e['revealed'])))
    parent = {start: (None, '开局' + ('（' + '；'.join(notes) + '）' if notes else ''))}
    edges = {}
    order = [start]
    queue = deque([start])
    while queue:
        state = queue.popleft()
        if goal(state):
            edges[state] = []
            continue
        nexts = []
        for raw, label in successors(state):
            nxt, notes = settle(raw)
            if nxt == state:
                continue
            nexts.append(nxt)
            if nxt not in parent:
                if len(parent) >= LIMIT:
                    raise InvalidPatch(issues=[issue('campaign', f'章节进度搜索超过 {LIMIT} 个状态上限，无法证明可通关；请减少相互独立的旗标取值、道具或任务，或拆到下一章', category='gameplay')])
                parent[nxt] = (state, label + ('（' + '；'.join(notes) + '）' if notes else ''))
                order.append(nxt)
                queue.append(nxt)
        edges[state] = nexts

    def path(state):
        steps = []
        while state is not None:
            state, label = parent[state][0], parent[state][1]
            steps.append(label)
        return steps[::-1]

    reached = sorted({s[0] for s in order})
    goals = [s for s in order if goal(s)]
    if not goals:
        raise InvalidPatch(issues=[issue('campaign', f'从开局无法到达任何{target}（已穷举 {len(order)} 个状态，可到达地区：{"、".join(reached)}）；检查钥匙/道具/能力是否只产在需要它的门后、单向路线和任务依赖', category='gameplay')])
    incoming = {}
    for state, nexts in edges.items():
        for nxt in nexts:
            incoming.setdefault(nxt, []).append(state)
    alive = set(goals)
    queue = deque(goals)
    while queue:
        for prev in incoming.get(queue.popleft(), []):
            if prev not in alive:
                alive.add(prev)
                queue.append(prev)
    stuck = next((s for s in order if s not in alive), None)
    if stuck is not None:
        raise InvalidPatch(issues=[issue('campaign', f'软锁：按以下步骤行动后再也无法到达{target}：{" → ".join(path(stuck))}。此时{describe(stuck, flag_keys, item_keys, mission_keys)}', category='gameplay')])
    return dict(target=target, path=path(goals[0]), states=len(order), regions=reached)


def describe(state, flag_keys, item_keys, mission_keys):
    region, flags, items, abilities, statuses, _, _ = state
    parts = [f'位于 {region}', '旗标 ' + ', '.join(f'{k}={v!r}' for k, v in zip(flag_keys, flags))]
    if item_keys:
        parts.append('道具 ' + ', '.join(f'{k}×{v}' for k, v in zip(item_keys, items)))
    if abilities:
        parts.append('能力 ' + '、'.join(sorted(abilities)))
    if mission_keys:
        parts.append('任务 ' + ', '.join(f'{k}:{v}' for k, v in zip(mission_keys, statuses)))
    return '；'.join(parts)


def _condition_lists(graph):
    for e in graph['links']:
        yield e['requires']
        yield e['discover']
    for m in graph['missions'].values():
        if m['frozen']:
            continue
        yield m['when']
        yield m['fail_when']
    yield graph['complete_when']
