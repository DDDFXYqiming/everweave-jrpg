"""An immutable per-world selection of systems and bounded player resources."""
import copy
from .diagnostics import InvalidPatch

SYSTEMS=('combat','inventory','equipment','progression')
BUILTINS={'hp':'max_hp','mp':'max_mp','gold':None}

def validate(raw):
    from .schema import obj,ident,text,arr
    from .content import integer,boolean
    obj(raw,'game_spec',('identity','inventory_label','journal_label','systems','resources','visual_theme','failure_mode'),('identity','inventory_label','journal_label','systems','resources','visual_theme'))
    out={k:text(raw[k],k,120) for k in ('identity','inventory_label','journal_label','visual_theme')}
    obj(raw['systems'],'systems',SYSTEMS,SYSTEMS)
    out['systems']={k:boolean(raw['systems'][k]) for k in SYSTEMS}
    mode=raw.get('failure_mode','checkpoint' if out['systems']['combat'] else 'none')
    if mode not in ('none','checkpoint','end') or (mode=='none' and out['systems']['combat']):raise InvalidPatch('failure_mode must be checkpoint/end for combat, or none for no automatic failure')
    out['failure_mode']=mode
    out['resources']=[];seen=set()
    for r in arr(raw['resources'],'resources',8):
        obj(r,'resource',('id','label','initial','max','display'),('id','label','initial','max'))
        key=ident(r['id'])
        if key in seen:raise InvalidPatch('duplicate player resource '+key)
        seen.add(key);cap=integer(r['max'],1,100000,'resource max')
        display=r.get('display','bar')
        if display not in ('bar','number'):raise InvalidPatch('resource display must be bar or number')
        out['resources'].append(dict(id=key,label=text(r['label'],'resource label',40),initial=integer(r['initial'],0,cap),max=cap,display=display))
    if out['systems']['combat'] and 'hp' not in seen:raise InvalidPatch('combat requires the hp resource; give it a setting-appropriate label')
    if out['systems']['equipment'] and not out['systems']['inventory']:raise InvalidPatch('equipment requires inventory')
    return out

def enabled(state,system):return state.get('game_spec',{}).get('systems',{}).get(system,True)
def resource(state,key):return next((r for r in state.get('game_spec',{}).get('resources',[]) if r['id']==key),None)
def active(state,key):return 'game_spec' not in state or resource(state,key) is not None

def install(state,spec):
    state['game_spec']=copy.deepcopy(spec);p=state['player'];p['resources']={}
    for key,cap in BUILTINS.items():
        p[key]=0
        if cap:p[cap]=0
    p.update(gold=0,xp=0,level=1,weapon='',charm='',inventory={})
    for r in spec['resources']:
        if r['id'] in BUILTINS:
            p[r['id']]=r['initial']
            if BUILTINS[r['id']]:p[BUILTINS[r['id']]]=r['max']
        else:p['resources'][r['id']]=r['initial']

def value(state,key):
    if not active(state,key):raise InvalidPatch('disabled player resource '+key)
    return state['player'][key] if key in BUILTINS else state['player'].get('resources',{}).get(key,0)

def change(state,key,delta):
    from .content import scalar
    r=resource(state,key)
    if not r:raise InvalidPatch('undefined player resource '+key)
    if type(delta) not in (int,float):raise InvalidPatch('resource delta must be numeric')
    scalar(delta);new=max(0,min(r['max'],value(state,key)+delta))
    if key in BUILTINS:state['player'][key]=new
    else:state['player']['resources'][key]=new

def snapshot(state):
    if 'game_spec' not in state:return None
    spec=copy.deepcopy(state['game_spec'])
    for r in spec['resources']:r['value']=value(state,r['id'])
    return spec

def check_plan(state,plan):
    if 'game_spec' not in state:return
    from .library import candidates,catalog
    profile=candidates(dict(setting=state['setting'],game_spec=state['game_spec']))['profile']
    def art_check(v):
        if isinstance(v,list):
            for x in v:art_check(x)
        elif isinstance(v,dict):
            if 'material' in v:return
            if 'asset' in v:
                entry=catalog().get(v['asset'],{})
                if profile in ('modern','sci_fi') and entry.get('kind')=='image' and profile not in entry.get('tags',[]) and not set(entry.get('roles',[])) & {'ground','vegetation'}:
                    raise InvalidPatch('asset does not fit this world; draw an original sprite',category='reference',value=v['asset'],expected=state['game_spec']['visual_theme'])
            for x in v.values():art_check(x)
    art_check(plan.get('visuals',{}))
    entities=plan.get('entities',plan.get('spawns',[]));items=plan.get('items',[])
    if not enabled(state,'combat') and any(e['kind']=='enemy' for e in entities):raise InvalidPatch('this game_spec disables combat and enemies')
    if not enabled(state,'inventory') and (items or any(e['kind']=='chest' for e in entities)):raise InvalidPatch('this game_spec disables inventory')
    if not enabled(state,'equipment') and any(i['kind'] in ('weapon','charm') for i in items):raise InvalidPatch('equipment is disabled; use tools and resource costs')
    for i in items:
        if i['kind']=='consumable' and not i.get('use') and not active(state,'hp' if i['effect']=='heal' else 'mp'):raise InvalidPatch('consumable restores a disabled resource')
    if any(e['kind']=='shrine' or e.get('role')=='healer' for e in entities) and not (active(state,'hp') and active(state,'mp')):
        raise InvalidPatch('legacy healer/shrine restores hp+mp; author an object with explicit resource effects instead')
    if any(e.get('role')=='merchant' for e in entities) and not (enabled(state,'inventory') and active(state,'gold')):raise InvalidPatch('legacy merchant requires currency; use a generic object for barter')
    def walk(node):
        if isinstance(node,list):
            for v in node:walk(v)
        elif isinstance(node,dict):
            path=str(node.get('get',node.get('path','')))
            if path.startswith('player.'):
                key=path.split('.')[1];key=key.removeprefix('max_')
                if key in BUILTINS and not active(state,key):raise InvalidPatch('rule uses disabled resource '+key)
                if key in ('xp','level') and not enabled(state,'progression'):raise InvalidPatch('progression is disabled')
            if path.startswith('resources.') and not resource(state,path.split('.')[1]):raise InvalidPatch('undefined custom resource in expression '+path)
            if node.get('op')=='stat' and node.get('target')=='player' and not active(state,node.get('name')):raise InvalidPatch('rule changes disabled player resource')
            if node.get('op')=='resource' and not resource(state,node.get('id')):raise InvalidPatch('undefined custom resource')
            if node.get('scope')=='combat' and not enabled(state,'combat'):raise InvalidPatch('combat actions are disabled')
            for v in node.values():walk(v)
    walk(plan.get('program',{}))
    for item in items:walk(item.get('use',{}))
