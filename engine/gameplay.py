"""Connect executable content to the existing authoritative game loop."""
import copy
from .schema import InvalidPatch
from .runtime import Runtime, RuleError, install, check_references, design_record
from .scene import paint, validate_space, cells_for


def transaction(world, operation):
    """Commit the action AND all generated effects once, or restore everything."""
    if getattr(world, '_batch', None) is not None:
        return operation()
    before = copy.deepcopy(world.state)
    cache_before = copy.deepcopy(world.cache)
    pending_before = world.reaction_needed
    world._batch = dict(regions={}, events=[], delete=set())
    try:
        result = operation()
        batch = world._batch
        if batch['regions'] or batch['events'] or world.state != before:
            world.store.commit(world.state, list(batch['regions'].values()), batch['events'],
                               delete_regions=batch['delete'])
        return result
    except Exception:
        world.state, world.cache, world.reaction_needed = before, cache_before, pending_before
        raise
    finally:
        world._batch = None


def definitions(world, region):
    install(region)
    items = dict(world.state['items'])
    for item in region.get('plan', {}).get('items', []):
        key = region['id']+':'+item['id']
        items[key] = dict(item, id=key, local_id=item['id'], origin=region['id'])
    check_references(region, items)
    objects={e.get('id') for e in region['entities']}|{e.get('local_id') for e in region['entities']}
    for key in region.get('audio',{}).get('objects',{}):
        if key not in objects:raise RuleError('audio references an unknown object',path='audio.objects.'+key)


def enter(world, region):
    if not region.get('program'): return
    install(region)
    register_objectives(world, region)
    vm = Runtime(world, region)
    vm.emit('enter')
    cue=region.get('audio',{}).get('bindings',{}).get('enter')
    if cue:world.queue_audio(cue,region)


def register_objectives(world, region):
    for q in region.get('program', {}).get('objectives', []):
        key = region['id']+':'+q['id']
        if key not in world.state['quests']:
            world.state['quests'][key] = dict(id=key, name=q['name'], description=q['description'],
                goal='program', target='', status=region.get('runtime', {}).get('done', {}).get(q['id'], 'active'),
                region=region['id'], reward=0)


def reaction(world, region, patch):
    # New drawing recipes may be added without rewriting a known character.
    ids=[e.get('local_id',e.get('id')) for e in region['entities']]
    if len(ids)!=len(set(ids)): raise RuleError('ambiguous local entity ID; invent a fresh ID')
    if 'visuals' in patch:
        art = copy.deepcopy(patch['visuals'])
        old = region.get('visuals', {})
        for key, value in old.get('sprites', {}).items():
            if key in art['sprites'] and art['sprites'][key] != value:
                raise RuleError('use a NEW sprite ID for a transformed object: '+key)
        art['sprites'] = {**old.get('sprites', {}), **art['sprites']}
        if len(art['sprites']) > 96: raise RuleError('region texture capacity reached')
        art['bindings'] = {**old.get('bindings', {}), **art.get('bindings', {})}
        if world.state.get('hero_visual'): art['sprites']['hero'] = copy.deepcopy(world.state['hero_visual'])
        region['visuals'] = art
    if 'audio' in patch:
        audio=region.setdefault('audio',{})
        for group in ('music','cues','bindings','objects'):audio.setdefault(group,{}).update(copy.deepcopy(patch['audio'].get(group,{})))
        if 'ambience' in patch['audio']:audio['ambience']=copy.deepcopy(patch['audio']['ambience'])
        if len(audio['music'])>16 or len(audio['cues'])>32:raise RuleError('installed audio capacity reached')
    if patch.get('program'): install(region, patch['program']); register_objectives(world, region)
    if patch.get('module_sources'):
        known={(s['module'],s['id'],s['sha256']) for s in region.get('module_sources',[])}
        for source in patch['module_sources']:
            if (source['module'],source['id'],source['sha256']) not in known:
                region.setdefault('module_sources',[]).append(copy.deepcopy(source))
    if patch.get('paint'): paint(region, patch['paint'])
    vm = Runtime(world, region)
    for update in patch.get('object_updates', []):
        obj = vm.entity(update['id'])
        if obj is world.state['player'] or obj.get('kind') == 'exit': raise RuleError('cannot directly rewrite player/exit')
        if 'at' in update: obj['x'], obj['y'] = update['at']
        if 'solid' in update: obj['solid'] = update['solid']
        if 'sprite' in update:
            if update['sprite'] not in region.get('visuals', {}).get('sprites', {}): raise RuleError('undefined new sprite')
            obj['sprite'] = update['sprite']
        if update.get('remove'): obj['spent'] = True
    definitions(world, region)
    from .library import usage
    region['library_usage']=usage(region)
    validate_space(region, world.state['player'] if world.state['current'] == region['id'] else None)


def distance(entity, player):
    return min(abs(x-player['x'])+abs(y-player['y']) for x, y in cells_for(entity))


def item_local_dependency(node):
    if isinstance(node,list):return any(item_local_dependency(v) for v in node)
    if not isinstance(node,dict):return False
    if str(node.get('get',node.get('path',''))).startswith(('objects.','vars.','self.')):return True
    if node.get('op') in ('move','sprite','solid','remove','paint','timer','emit','end_battle'):return True
    if 'item' in node and ':' not in node['item']:return True
    return any(item_local_dependency(v) for v in node.values())


def item_availability(world,item):
    p=world.state['player'];r=world.region();use=item.get('use')
    label=(use or {}).get('label','装备' if item.get('kind') in ('weapon','charm') else '使用')
    reason=''
    if p['inventory'].get(item.get('id'),0)<1:reason='背包里没有这件物品。'
    elif world.state['battle']:reason='请先结束战斗。'
    elif world.state['ui']:reason='先结束当前交互。'
    elif use:
        if not r:reason='地区尚未就绪。'
        elif item.get('origin',r['id'])!=r['id'] and item_local_dependency(use):reason='此物品的交互绑定原地区；请返回后使用。'
        else:
            # Evaluate on a private view so inspecting conditions cannot alter
            # player/object state or spend the live runtime's execution budget.
            view=copy.copy(world);view.state=dict(world.state,player=copy.deepcopy(p))
            vm=Runtime(view,copy.deepcopy(r))
            try:
                if not vm.expr(use['when']):reason=vm._resource_hint(use['when']) or '当前不满足物品使用条件。'
            except RuleError:reason='此物品当前不可使用。'
    elif item.get('kind') in ('weapon','charm'):
        if p.get(item['kind'])==item['id']:reason='已经装备。'
    elif item.get('kind')=='consumable':
        stat,cap=('hp','max_hp') if item['effect']=='heal' else ('mp','max_mp')
        if p[stat]>=p[cap]:reason='生命已满。' if stat=='hp' else '魔力已满。'
    else:reason='在相关人物或物件处使用。'
    return dict(enabled=not reason,blocked_reason=reason,label=label)


def action(world, a):
    def apply():
        if not isinstance(a, dict) or not world.state or not world.region():
            from .world import GameError
            raise GameError('世界未就绪，或动作格式无效。')
        r = world.region(); s = world.state; op = a.get('op')
        previous = (s['current'], s['steps'], bool(s['battle']), copy.deepcopy(s['ui']))
        if op in ('invoke', 'actions', 'wait'):
            if s['battle'] or s['ui']: raise RuleError('先结束当前交互。')
            vm = Runtime(world, r)
            if op == 'actions':
                options = vm.available(scope='explore')
                s['ui'] = dict(kind='actions', title='此刻可以做什么', lines=[], actions=options)
                world.persist(); return
            if op == 'invoke':
                definition = vm.invoke(a.get('id'), 'explore')
                event, _ = world.story('interaction', definition['label'], dict(action=definition['id']))
                world.persist(r, event=event)
            else:
                s['time'] += 1
                vm.emit('wait', advance=True); world.persist(r)
            show_messages(world, vm)
            return
        if op == 'content_action':
            if s['battle'] or s['ui'].get('kind') != 'actions': raise RuleError('没有可操作对象。')
            offered = {entry['id'] for entry in s['ui'].get('actions', [])}
            if a.get('id') not in offered: raise RuleError('无效操作。')
            s['ui'] = {}
            vm = Runtime(world, r); definition = vm.invoke(a['id'], 'explore')
            event, _ = world.story('interaction', definition['label'], dict(action=definition['id']))
            show_messages(world, vm); world.persist(r, event=event); return
        if op == 'use' and not s['battle']:
            item = s['items'].get(a.get('id'), {})
            if item.get('use'):
                availability=item_availability(world,item)
                if not availability['enabled']:raise RuleError(availability['blocked_reason'])
                vm = Runtime(world, r); use = item['use']
                # Local-object dependencies cannot silently bind to a different region.
                if item.get('origin', r['id']) != r['id'] and item_local_dependency(use):
                    raise RuleError('此物品的交互绑定原地区；请返回后使用。')
                if not vm.expr(use['when']): raise RuleError('当前不满足物品使用条件。')
                s['player']['inventory'][item['id']] -= use['consume']
                vm.run(use['effects']); vm.emit('use', advance=True, item=item['id'])
                event, _ = world.story('use', use['label']+'：'+item['name'])
                show_messages(world, vm); world.persist(r, event=event); return
        interaction_target = world._action(a)
        current = world.region()
        if not current.get('program'): return
        if previous[0] != s['current']:
            enter(world, current); world.persist(current); return
        vm = Runtime(world, current)
        if op == 'move' and s['steps'] != previous[1]:
            vm.emit('move', advance=True, x=s['player']['x'], y=s['player']['y'])
        elif op in ('interact', 'choice') and not s['battle'] and interaction_target:
            vm.emit(op, target=interaction_target, advance=True, choice=a.get('id', '') if op == 'choice' else '')
        else: return
        show_messages(world, vm); world.persist(current)
    return transaction(world, apply)


def show_messages(world, vm):
    if vm.messages and not world.state.get('battle') and not world.state['ui']:
        world.state['ui'] = dict(kind='message', title='世界发生了变化', lines=vm.messages[-6:])


def interact(world, entity):
    r = world.region()
    if entity['kind'] == 'exit' or not r.get('program'): return False
    actions = Runtime(world, r).available(target=entity['id'], scope='explore')
    if not actions and entity['kind'] != 'object': return False
    world.state['ui'] = dict(kind='actions', title=entity['name'], lines=[entity.get('description', '')], actions=actions)
    world.persist(r)
    return True


def has_combat(region):
    return any(a['scope'] == 'combat' for a in region.get('program', {}).get('actions', []))


def combat(world, move):
    r = world.region(); s = world.state; b = s['battle']; p = s['player']
    if not has_combat(r): return False
    if move == 'flee':
        s['battle'] = None; world.note('你撤出了战斗。'); world.persist(r); return True
    if not isinstance(move, str) or not move.startswith('rule:'): raise RuleError('请选择模型生成的战斗操作。')
    vm = Runtime(world, r)
    offered = {a['id']: a for a in vm.available(scope='combat')}
    key = move[5:]
    if key not in offered or not offered[key]['enabled']: raise RuleError('当前不能使用这个技能。')
    b['turn'] += 1
    world.sound_event('combat')
    vm.emit('turn_start', target='enemy')
    if p['hp'] <= 0: world._defeat(); world.persist(r); return True
    if b['hp'] > 0 and not vm.end_result:
        definition = vm.invoke(key, 'combat')
        b['log'].append(definition['label'])
    if vm.end_result == 'escape': s['battle'] = None; world.persist(r); return True
    if b['hp'] <= 0 or vm.end_result == 'victory':
        vm.emit('victory', target=b['id']); world._win_battle(); return True
    hooks = r.get('program', {}).get('hooks', [])
    if any(h['on'] == 'enemy_turn' for h in hooks): vm.emit('enemy_turn', target=b['id'])
    else:
        p['hp'] = max(0, p['hp']-b['attack']); b['log'].append(b['name']+f"造成 {b['attack']} 点伤害。")
    vm.emit('turn_end', target=b['id'], advance=True)
    b['log'] = (b['log']+vm.messages)[-7:]
    if vm.end_result == 'escape': s['battle'] = None
    elif p['hp'] <= 0: world._defeat()
    elif b['hp'] <= 0 or vm.end_result == 'victory':
        vm.emit('victory', target=b['id']); world._win_battle(); return True
    world.persist(r); return True
