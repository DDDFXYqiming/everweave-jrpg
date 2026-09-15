"""Fast, goal-free player controls over the existing local game API.

The caller chooses what to explore. This tool only observes, walks and acts;
it never completes objectives, changes coordinates or configures cloud calls.
"""
import argparse
from collections import deque
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.catalog import BLOCKED
from engine.scene import cells_for


def select(value, keys):
    return {key: value[key] for key in keys if key in value}


def visible_entities(snapshot):
    # The current client displays the whole current room, without fog of war.
    # Hidden campaign exits are removed by World.snapshot; spent actors vanish.
    return [e for e in (snapshot.get('region') or {}).get('entities', [])
            if not e.get('spent') and not e.get('hidden')]


def observe(s):
    """Explicit allowlist: no program, conditions, future scenes or cast state."""
    r = s.get('region') or {}; p = s.get('player', {}); ui = s.get('ui') or {}
    result = select(s, ('started', 'title', 'time', 'map_count', 'game_over'))
    result['location'] = select(r, ('id', 'name', 'description', 'weather', 'width', 'height'))
    result['player'] = select(p, ('x', 'y'))
    spec = s.get('game_spec')
    if spec:
        result['player']['identity'] = spec.get('identity')
        result['player']['resources'] = [select(v, ('id', 'label', 'value', 'max')) for v in spec.get('resources', [])]
        if spec.get('systems', {}).get('progression'):
            result['player'].update(select(p, ('level', 'xp')))
    else:
        result['player'].update(select(p, ('hp', 'max_hp', 'mp', 'max_mp', 'gold', 'level', 'xp')))
    result['entities'] = [select(e, ('id', 'name', 'kind', 'x', 'y', 'footprint', 'locked', 'blocked_reason')) for e in visible_entities(s)]
    result['inventory'] = [select(i, ('id', 'name', 'description', 'quantity', 'equipped', 'usable')) for i in s.get('inventory', [])]
    result['goals'] = [select(q, ('id', 'name', 'description', 'status')) for q in s.get('quests', [])]
    if s.get('adventure'):
        result['adventure'] = s['adventure']  # Already a public projection in World.
    result['journal'] = s.get('journal', [])
    result['ui'] = select(ui, ('kind', 'title', 'lines', 'ready', 'name'))
    for key in ('actions', 'choices'):
        result['ui'][key] = [select(a, ('id', 'label', 'text', 'description', 'enabled', 'blocked_reason')) for a in ui.get(key, [])]
    result['ui']['goods'] = [select(i, ('id', 'name', 'description', 'price')) for i in ui.get('goods', [])]
    result['actions'] = [select(a, ('id', 'label', 'description', 'enabled', 'blocked_reason', 'scope', 'target')) for a in s.get('available_actions', [])]
    result['battle'] = select(s.get('battle') or {}, ('name', 'hp', 'max_hp', 'turn', 'log'))
    return result


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('The local game API must not redirect.')


class LocalAPI:
    def __init__(self, folder):
        runtime = json.loads((Path(folder) / 'runtime.json').read_text(encoding='utf-8-sig'))
        address = urlsplit(runtime['url'])
        if (address.scheme != 'http' or address.hostname != '127.0.0.1' or not address.port
                or address.username or address.password or address.path not in ('', '/')
                or address.query or address.fragment):
            raise ValueError('Expected a loopback runtime URL from launch.py.')
        self.url = runtime['url'].rstrip('/'); self.token = runtime['token']
        self.opener = build_opener(ProxyHandler({}), NoRedirects())

    def request(self, path, data=None):
        headers = {'Authorization': 'Bearer ' + self.token}
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            headers.update({'Content-Type': 'application/json', 'X-Request-ID': str(uuid.uuid4())})
        try:
            with self.opener.open(Request(self.url + path, body, headers), timeout=15) as response:
                return json.load(response)
        except HTTPError as exc:
            error = json.loads(exc.read()).get('error', 'Game action rejected')
            raise ValueError(error) from None
        except (URLError, TimeoutError) as exc:
            # A timed-out mutation may have committed: never replay it automatically.
            raise ValueError('Local request failed; observe again before deciding whether to repeat the action.') from exc

    def snapshot(self): return self.request('/state')
    def action(self, data): return self.request('/action', data)


def route(s, target):
    """Shortest physical route to interaction range; never inspect game rules."""
    r = s['region']; start = (s['player']['x'], s['player']['y'])
    occupied = set()
    for group in ('props', 'entities'):
        for obj in r.get(group, []):
            if not obj.get('spent') and obj.get('solid', group == 'entities'):
                occupied.update(cells_for(obj))
    goals = {point for x, y in cells_for(target) for point in ((x, y), (x-1, y), (x+1, y), (x, y-1), (x, y+1))}
    queue = deque([start]); previous = {start: None}
    while queue:
        point = queue.popleft()
        if point in goals:
            path = []
            while previous[point] is not None:
                path.append(point); point = previous[point]
            return list(reversed(path))
        x, y = point
        for nxt in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
            nx, ny = nxt
            if (nxt not in previous and 0 <= nx < r['width'] and 0 <= ny < r['height']
                    and r['tiles'][ny][nx] not in BLOCKED and nxt not in occupied):
                previous[nxt] = point; queue.append(nxt)
    return None


def interruption(before, after):
    if after.get('game_over'): return 'game_over'
    if after.get('battle'): return 'battle'
    if after.get('ui'): return 'dialogue_or_menu'
    if (after.get('region') or {}).get('id') != (before.get('region') or {}).get('id'): return 'region_changed'
    a, b = observe(before), observe(after)
    for key in ('inventory', 'goals', 'adventure', 'journal', 'entities'):
        if a.get(key) != b.get(key): return key + '_changed'
    pa, pb = dict(a['player']), dict(b['player'])
    for key in ('x', 'y'): pa.pop(key, None); pb.pop(key, None)
    if pa != pb: return 'resources_changed'
    return None


class Session:
    def __init__(self, api): self.api = api

    def go(self, key, interact=False, max_steps=160):
        started = time.monotonic(); s = self.api.snapshot(); moves = 0; reason = ''
        while moves < max_steps:
            if s.get('battle') or s.get('ui') or s.get('game_over'):
                reason = 'finish_current_interaction'; break
            target = next((e for e in visible_entities(s) if e['id'] == key), None)
            if not target: reason = 'target_not_visible'; break
            path = route(s, target)
            if path is None: reason = 'no_walkable_route'; break
            if not path:
                reason = 'arrived'
                if interact:
                    s = self.api.action({'op': 'interact', 'id': key}); reason = 'interacted'
                break
            x, y = path[0]; p = s['player']
            after = self.api.action({'op': 'move', 'dx': x-p['x'], 'dy': y-p['y']}); moves += 1
            reason = interruption(s, after)
            if not reason and (after['player']['x'], after['player']['y']) != (x, y): reason = 'movement_blocked'
            s = after
            if reason: break
        return dict(reason=reason or 'step_limit', moves=moves, seconds=round(time.monotonic()-started, 3), observation=observe(s))

    def act(self, op, key=None):
        s = self.api.snapshot(); ui = s.get('ui') or {}; data = {'op': op}
        if op == 'choose':
            field = 'choices' if ui.get('kind') == 'dialogue' else 'actions'
            offered = ui.get(field, [])
            data = {'op': 'choice' if field == 'choices' else 'content_action', 'id': key}
        elif op == 'invoke': offered = s.get('available_actions', []); data['id'] = key
        elif op == 'use':
            offered = [dict(i, enabled=i.get('usable', {}).get('enabled', False)) for i in s.get('inventory', [])]; data['id'] = key
        elif op == 'interact': offered = visible_entities(s); data['id'] = key
        elif op == 'combat':
            if not s.get('battle'): raise ValueError('No battle is active.')
            options = s.get('available_actions', []) if s['battle'].get('authored') else []
            allowed = {a['id'] for a in options if a.get('enabled', True)} | {'flee'}
            if not s['battle'].get('authored'): allowed |= {'attack', 'skill', 'defend', 'potion'}
            if key not in allowed: raise ValueError('That combat action is not offered.')
            data['move'] = 'rule:'+key if s['battle'].get('authored') and key != 'flee' else key; offered = None
        else: offered = None
        if offered is not None and not any(a['id'] == key and a.get('enabled', True) for a in offered):
            raise ValueError('That action is not currently offered or enabled.')
        return {'observation': observe(self.api.action(data))}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', type=Path, required=True)
    p.add_argument('--record', type=Path, help='Append public observations and actions as JSONL; no raw state or credentials')
    commands = p.add_subparsers(dest='command', required=True)
    commands.add_parser('observe')
    go = commands.add_parser('go'); go.add_argument('id'); go.add_argument('--interact', action='store_true')
    go.add_argument('--max-steps', type=int, default=160)
    for op in ('choose', 'invoke', 'use', 'interact', 'combat'):
        commands.add_parser(op).add_argument('id')
    for op in ('close', 'wait', 'enter_exit'): commands.add_parser(op)
    args = p.parse_args(); session = Session(LocalAPI(args.data_dir))
    if args.command == 'observe': result = {'observation': observe(session.api.snapshot())}
    elif args.command == 'go': result = session.go(args.id, args.interact, max(1, min(args.max_steps, 300)))
    else: result = session.act(args.command, getattr(args, 'id', None))
    if args.record:
        args.record.parent.mkdir(parents=True, exist_ok=True)
        with args.record.open('a', encoding='utf-8') as f:
            f.write(json.dumps(dict(command=args.command, id=getattr(args, 'id', None), **result), ensure_ascii=False) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False)); sys.exit(1)
