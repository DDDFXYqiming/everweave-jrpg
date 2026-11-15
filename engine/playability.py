import copy
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
    from . import gameplay
    probe=clone(world)
    try:
        rid=context['target']
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
