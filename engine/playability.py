"""隔离执行与保守的进展检查。未知表达式不会被误判为无解。"""
import copy
import itertools
from collections import OrderedDict
from .diagnostics import InvalidPatch


class RegionEntryError(InvalidPatch):
    def __init__(self,target,error):
        self.target=target
        super().__init__(issues=[dict(i,path='entry.'+i['path']) for i in error.issues])


def clone(world):
    from .storage import Store
    from .world import World
    store=Store(':memory:')
    regions=[copy.deepcopy(world.region(rid)) for rid,n in world.state['topology'].items() if n['ready']]
    store.commit(copy.deepcopy(world.state),[r for r in regions if r])
    return World(store)


def check_entry(world,parsed,context):
    """在真实解释器的独立存档中发布，并验证每个实际入口。"""
    from . import gameplay
    probe=clone(world)
    try:
        rid=context['target']
        # 首区安装本身会执行 enter；其他地区安装后逐入口试运行。
        probe._apply_patch(None,context,_validated=copy.deepcopy(parsed))
        if rid=='r0':return
        region=probe.region(rid)
        starts=[region['spawn']]+[[e['x'],e['y']] for e in region['entities'] if e['kind']=='exit']
        base_state=copy.deepcopy(probe.state);base_region=copy.deepcopy(region)
        for start in starts:
            probe.state=copy.deepcopy(base_state);probe.cache=OrderedDict([(rid,copy.deepcopy(base_region))])
            region=probe.region(rid);probe._enter_content(region)
            probe.state['current']=rid;probe.state['player'].update(x=start[0],y=start[1]);probe.state['ui']={};probe.state['battle']=None
            gameplay.transaction(probe,lambda:gameplay.enter(probe,region))
            if not probe.state['ui'] and not probe.state['battle'] and not probe.state.get('game_over'):
                probe.action({'op':'wait'})
    except InvalidPatch as exc:
        raise exc.under('region.entry_validation') from None
    finally:probe.store.close()


def replay(world,actions,goal):
    """只重放正常动作；目标由调用方传入，不授予状态或物品。"""
    if len(actions)>512:raise InvalidPatch('验收路线超过 512 个动作')
    probe=clone(world)
    try:
        for index,action in enumerate(actions):
            try:probe.action(copy.deepcopy(action))
            except (InvalidPatch,ValueError) as exc:
                raise InvalidPatch(f'验收路线第 {index+1} 步失败：{exc}',path=f'playtest[{index}]',category='gameplay') from None
        if not goal(probe):raise InvalidPatch('验收路线未达成目标',path='playtest',category='gameplay')
        return {'status':'verified','actions':len(actions)}
    finally:probe.store.close()


UNKNOWN=object()


def check_progress(world,body,context):
    """宽松固定点检查旗标、钥匙、资源与路线的确定死锁。"""
    from .campaign import chapter
    from .costs import requirements
    chapter_data=chapter(world.state,context['target'])
    if not chapter_data:return {'status':'not_applicable'}
    rid=context['target'];flags={k:{v} for k,v in chapter_data['flags'].items()}
    state=world.state;p=state['player'];items={k:v for k,v in p['inventory'].items()}
    resources={r['id']:(p.get(r['id'],0) if r['id'] in ('hp','mp','gold') else p.get('resources',{}).get(r['id'],0)) for r in state['game_spec']['resources']}
    caps={r['id']:r['max'] for r in state['game_spec']['resources']}
    bodies={rid:body}
    for node in chapter_data['regions']:
        key=node['id']
        if key!=rid and state['topology'][key]['ready']:
            region=world.region(key)
            bodies[key]=dict(region.get('plan',{}),program=region.get('program',{}),scenes=region.get('scenes',[]))
    reached={state['current']} if state['current'] in {n['id'] for n in chapter_data['regions']} else {chapter_data['regions'][0]['id']}
    def item_key(key,owner):return key if ':' in key or key in state['items'] else owner+':'+key
    def evaluate(expr,owner):
        if not isinstance(expr,dict):return {expr}
        if 'item' in expr:
            count=items.get(item_key(expr['item'],owner),0)
            if any(r not in bodies for r in reached) or count>128:return UNKNOWN
            return set(range(count+1))
        path=expr.get('get','')
        if path.startswith('chapter.'):return flags.get(path.split('.')[1],UNKNOWN)
        if path.startswith('resources.') or path in ('player.hp','player.mp','player.gold'):
            amount=resources.get(path.split('.')[1],0)
            return set(range(int(amount)+1)) if type(amount) is int and amount<=128 else UNKNOWN
        if 'op' not in expr:return UNKNOWN
        op=expr['op'];args=[evaluate(a,owner) for a in expr.get('args',[])]
        if op=='and':
            if any(v is not UNKNOWN and not any(v) for v in args):return {False}
            return {True,False} if any(v is UNKNOWN or False in v for v in args) else {True}
        if op=='or':
            if any(v is not UNKNOWN and all(v) for v in args):return {True}
            return {True,False} if any(v is UNKNOWN or any(v) for v in args) else {False}
        if any(v is UNKNOWN for v in args) or not args:return UNKNOWN
        if op=='not':return {not v for v in args[0]}
        functions={'eq':lambda a,b:a==b,'ne':lambda a,b:a!=b,'lt':lambda a,b:a<b,'le':lambda a,b:a<=b,
                   'gt':lambda a,b:a>b,'ge':lambda a,b:a>=b}
        if op not in functions or len(args)!=2:return UNKNOWN
        try:return {functions[op](*values) for values in itertools.islice(itertools.product(*args),128)}
        except (TypeError,ValueError):return UNKNOWN
    def possible(expr,owner):
        value=evaluate(expr,owner);return value is UNKNOWN or any(value)
    def conditions(values):return all(flags.get(v['flag']) is UNKNOWN or v['eq'] in flags.get(v['flag'],set()) for v in values)
    def effects(commands,owner):
        for command in commands:
            op=command.get('op')
            if op=='if':
                if possible(command['when'],owner):effects(command['then'],owner)
                if possible({'op':'not','args':[command['when']]},owner):effects(command.get('else',[]),owner)
            elif op=='chapter':
                key=command['key'];value=evaluate(command['value'],owner)
                if value is UNKNOWN:flags[key]=UNKNOWN
                elif flags.get(key) is not UNKNOWN:flags.setdefault(key,set()).update(value)
            elif op=='item':
                amount=command['count']
                if isinstance(amount,dict) or type(amount) is int and amount>0:items[item_key(command['id'],owner)]=999
            elif op=='resource' or op=='stat' and command.get('target')=='player':
                key=command.get('id',command.get('name'));delta=command.get('delta')
                if isinstance(delta,dict) or type(delta) in (int,float) and delta>0:resources[key]=caps.get(key,1000000)
    for _ in range(128):
        before=repr((flags,items,resources,reached))
        for edge in chapter_data['links']:
            if not conditions(edge.get('requires',[])) or edge.get('hidden') and not edge.get('revealed') and not conditions(edge.get('discover',[])):continue
            if edge['a'] in reached:reached.add(edge['b'])
            if edge['b'] in reached and not edge.get('one_way'):reached.add(edge['a'])
        for owner in list(reached):
            candidate=bodies.get(owner)
            if candidate is None:
                # 未制作的可达地区可以提供其承诺的旗标，以及尚未知晓的资源/物品。
                for key,source in chapter_data['flag_sources'].items():
                    if source==owner:flags[key]=UNKNOWN
                # 有未知内容时不凭当前背包推断所有未来支付或钥匙不可能。
                for key in resources:resources[key]=caps.get(key,1000000)
                continue
            for entry in candidate.get('starting_loadout',{}).get('inventory',[]):items[item_key(entry['item_id'],owner)]=max(items.get(item_key(entry['item_id'],owner),0),entry['count'])
            for entity in candidate.get('entities',[]):
                if entity.get('kind')=='chest':items[item_key(entity['item_id'],owner)]=999
            program=candidate.get('program',{})
            definitions=program.get('actions',[])+program.get('hooks',[])+program.get('objectives',[])
            definitions+= [choice for scene in candidate.get('scenes',[]) for choice in scene.get('choices',[])]
            definitions+= [item['use'] for item in candidate.get('items',[]) if item.get('use')]
            for definition in definitions:
                if possible(definition.get('when',True),owner) and all(resources.get(k,0)>=v for k,v in requirements(definition).items()):
                    effects(definition.get('effects',definition.get('reward',[])),owner)
        if repr((flags,items,resources,reached))==before:break
    else:return {'status':'unproven','reason':'analysis_budget'}
    needed=(chapter_data['complete_when'] if not chapter_data['complete'] else [])+[
        condition for m in chapter_data['milestones']
        if state['quests'].get(chapter_data['id']+':'+m['id'],{}).get('status','active')=='active' for condition in m['when']]
    errors=[{'path':'region.program','category':'gameplay','message':f"旗标 {c['flag']} 无法达到目标值；检查生产动作、钥匙、代价和路线的循环依赖"}
            for c in needed if flags.get(c['flag']) is not UNKNOWN and c['eq'] not in flags.get(c['flag'],set())]
    if errors:raise InvalidPatch(issues=errors)
    return {'status':'unproven','reason':'relaxed_dependencies_passed'}
