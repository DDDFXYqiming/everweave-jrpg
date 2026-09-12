"""Opening possessions are authored once with the first region, not a global kit."""
from .diagnostics import InvalidPatch, checked
from .schema import obj, arr, reference
from .content import integer


def parse(value):
    obj(value,'starting loadout',('inventory','weapon','charm'),('inventory',))
    result={'inventory':[]}
    for index,entry in enumerate(arr(value['inventory'],'starting inventory',8)):
        at=f'inventory[{index}]'
        checked(at,obj,entry,'starting item',('item_id','count'),('item_id','count'))
        result['inventory'].append({'item_id':checked(at+'.item_id',reference,entry['item_id']),
                                   'count':checked(at+'.count',integer,entry['count'],1,9)})
    if len({i['item_id'] for i in result['inventory']})!=len(result['inventory']):
        raise InvalidPatch('duplicate starting item',path='inventory')
    if sum(i['count'] for i in result['inventory'])>20:
        raise InvalidPatch('starting inventory exceeds 20 items',path='inventory')
    for slot in ('weapon','charm'):
        if value.get(slot):result[slot]=checked(slot,reference,value[slot])
    return result


def validate(plan,context):
    kit=plan.get('starting_loadout')
    opening=context.get('target')=='r0'
    authored=context.get('item_policy')=='authored'
    if kit is None:
        if opening and authored:
            raise InvalidPatch('opening region needs starting_loadout',path='region.starting_loadout',
                               expected='{inventory:[{item_id:local item ID,count:1..9}],weapon?:local ID,charm?:local ID}; define these in region.items')
        return
    if not opening:raise InvalidPatch('starting possessions may only be defined for the opening',path='region.starting_loadout')
    definitions={i['id']:i for i in plan['items']}
    for index,entry in enumerate(kit['inventory']):
        if entry['item_id'] not in definitions:
            raise InvalidPatch('starting item must be defined in this region',path=f'region.starting_loadout.inventory[{index}].item_id',category='reference',value=entry['item_id'])
    owned={entry['item_id'] for entry in kit['inventory']}
    for slot in ('weapon','charm'):
        key=kit.get(slot)
        if key and (key not in owned or definitions[key]['kind']!=slot):
            raise InvalidPatch('equipped starting item must be owned and match its slot',path='region.starting_loadout.'+slot,category='reference',value=key)


def apply(world,region):
    if world.state.get('item_policy')!='authored' or world.state.get('loadout_applied'):return
    kit=region['plan']['starting_loadout'];player=world.state['player']
    for entry in kit['inventory']:
        key=region['id']+':'+entry['item_id']
        player['inventory'][key]=entry['count']
    for slot in ('weapon','charm'):
        player[slot]=region['id']+':'+kit[slot] if kit.get(slot) else ''
    world.state['loadout_applied']=True
