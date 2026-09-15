"""Validated worker output: portable skills, cast bindings and choice scenes."""
import copy
from .diagnostics import InvalidPatch

def ability_contract_errors(body,kind,ctx):
    """Independent checks also run when another part of the JSON is malformed."""
    from .diagnostics import issue
    if not isinstance(body,dict):return []
    skills=(ctx or {}).get('adventure_state',{} ) or {}
    skills=skills.get('skills',{})
    if not skills:return []
    defined={a['id'] for a in body.get('abilities',[]) if isinstance(a,dict) and isinstance(a.get('id'),str)} if isinstance(body.get('abilities',[]),list) else set()
    implemented=defined|{k for k,v in skills.items() if v.get('rule')}
    errors=[]
    required={k for j in (ctx or {}).get('content_contract',{}).get('commissions',[]) for k in j.get('skills',[])}
    for key in required-implemented:
        errors.append(issue(kind+'.abilities','commissioned skill needs an executable definition',category='reference',value=key,expected=dict(field=kind+'.abilities',brief=skills.get(key),format='action with matching id/label/scope, target=player, once=false, when and portable effects')))
    def walk(v,path):
        if isinstance(v,list):
            for index,x in enumerate(v):walk(x,f'{path}[{index}]')
        elif isinstance(v,dict):
            if v.get('op')=='learn' and (not isinstance(v.get('id'),str) or v['id'] not in implemented):
                errors.append(issue(path+'.id','learn requires an implemented global skill',category='reference',value=v.get('id'),expected='define the commissioned skill in '+kind+'.abilities; retain the earned learning action'))
            for k,x in v.items():walk(x,path+'.'+k)
    walk(body,kind)
    return errors

def parse_abilities(raw):
    from .content import program
    result=program({'actions':raw})['actions']
    def portable(v):
        if isinstance(v,list):
            for x in v:portable(x)
        elif isinstance(v,dict):
            if 'get' in v and str(v['get']).split('.')[0] not in ('player','resources','cast','battle'):raise InvalidPatch('portable ability cannot depend on local state')
            if 'item' in v or 'history' in v or 'fact' in v:raise InvalidPatch('portable ability must use persistent resource/cast state')
            if 'op' in v and v['op'] not in ('if','stat','resource','message','actor') and 'args' not in v:raise InvalidPatch('unsupported portable ability effect')
            for x in v.values():portable(x)
    for a in result:
        if a['target']!='player' or a['once']:raise InvalidPatch('portable skills target player and are repeatable')
        portable(a['when']);portable(a['effects'])
    return result

def parse_scenes(raw):
    from .schema import obj,arr,ident,text
    from .content import expression,effects
    result=[]
    for scene in arr(raw,'scenes',6):
        obj(scene,'scene dialogue',('id','title','lines','choices'),('id','title','lines'))
        lines=[]
        for line in arr(scene['lines'],'scene lines',8,1):
            obj(line,'scene line',('speaker','text'),('speaker','text'))
            lines.append(dict(speaker=ident(line['speaker']),text=text(line['text'],'scene text',400)))
        choices=[]
        for choice in arr(scene.get('choices',[]),'scene choices',4):
            obj(choice,'scene choice',('id','label','when','effects'),('id','label','effects'))
            choices.append(dict(id=ident(choice['id']),label=text(choice['label'],'choice label',80),when=expression(choice.get('when',True)),effects=effects(choice['effects'])))
        if len({c['id'] for c in choices})!=len(choices):raise InvalidPatch('duplicate scene choice')
        result.append(dict(id=ident(scene['id']),title=text(scene['title'],'scene title',100),lines=lines,choices=choices))
    if len({s['id'] for s in result})!=len(result):raise InvalidPatch('duplicate scene ID')
    return result

def validate(world,body,ctx):
    from . import adventure
    from .game_spec import check_plan
    adv=adventure.state(world)
    if not adv:
        if body.get('scenes') or body.get('abilities') or any(e.get('actor_id') for e in body.get('entities',body.get('spawns',[]))):raise InvalidPatch('persistent story content needs an adventure plan')
        return
    actors=adv['cast'];skills=adv['skills']
    entities=body.get('entities',body.get('spawns',[]));present=set()
    for e in entities:
        if 'actor_id' not in e:continue
        key=e['actor_id']
        if key not in actors or not actors[key]['state']['alive']:raise InvalidPatch('unknown or dead cast member '+key)
        if key in present:raise InvalidPatch('cast member appears twice in one region')
        present.add(key)
    abilities={a['id']:a for a in body.get('abilities',[])}
    for key,a in abilities.items():
        if key not in skills or a['label']!=skills[key]['name'] or a['scope']!=skills[key]['scope']:raise InvalidPatch('ability differs from its global brief')
        if skills[key].get('rule') and skills[key]['rule']!=a:raise InvalidPatch('installed portable ability is immutable; omit the duplicate definition',expected=skills[key]['rule'])
        check_plan(world.state,{'program':{'actions':[a]}})
    existing=world.region(ctx['target']) if ctx['kind']=='reaction' else None
    scenes={s['id']:s for s in (existing or {}).get('scenes',[])}
    for scene in body.get('scenes',[]):
        if scene['id'] in scenes and scene!=scenes[scene['id']]:raise InvalidPatch('installed scene is immutable')
        scenes[scene['id']]=scene
        for line in scene['lines']:
            if line['speaker']!='narrator' and line['speaker'] not in actors:raise InvalidPatch('unknown scene speaker')
            if line['speaker']!='narrator':present.add(line['speaker'])
        check_plan(world.state,{'program':scene})
    triggered=set();granted=set();written=set()
    def walk(v):
        if isinstance(v,list):
            for x in v:walk(x)
        elif isinstance(v,dict):
            path=str(v.get('get',''))
            if path.startswith('cast.'):
                bits=path.split('.')
                if len(bits)!=3 or bits[1] not in actors or bits[2] not in actors[bits[1]]['state']:raise InvalidPatch('unknown persistent cast field')
            if v.get('op')=='actor' and (v['id'] not in actors or v['key'] not in actors[v['id']]['state']):raise InvalidPatch('unknown persistent actor state')
            if v.get('op')=='learn' and (v['id'] not in skills or not (skills[v['id']].get('rule') or v['id'] in abilities)):raise InvalidPatch('skill must be implemented before it is granted')
            if v.get('op')=='learn':granted.add(v['id'])
            if v.get('op')=='scene' and v['id'] not in scenes:raise InvalidPatch('unknown story scene')
            if v.get('op')=='scene':triggered.add(v['id'])
            if v.get('op')=='chapter':written.add(v['key'])
            for x in v.values():walk(x)
    walk(body)
    if existing:present.update(e.get('actor_id') for e in existing['entities'] if not e.get('spent'))
    jobs=ctx.get('content_contract',{}).get('commissions',[])
    for job in jobs:
        if not set(job.get('flag_writes',[]))<=written:raise InvalidPatch('commission must implement its new flag producers')
        foes=[e for e in entities if e['kind']=='enemy'];limits=job.get('limits',{})
        if len(foes)>limits.get('max_enemies',32):raise InvalidPatch('encounter exceeds commissioned enemy count')
        for e in foes:
            for key,field in (('enemy_hp','hp'),('enemy_attack','attack')):
                if key in limits and (field not in e.get('stats',{}) or e['stats'][field]>limits[key]):raise InvalidPatch('enemy stats exceed or omit the director limit '+key)
        if not set(job['cast'])<=present:raise InvalidPatch('commission needs its cast binding or speaking scene: '+job['id'])
        if not set(job['skills'])<=set(abilities)|{k for k,v in skills.items() if v.get('rule')}:raise InvalidPatch('commission must implement requested skills')
        if job['kind']=='scene' and not body.get('scenes'):raise InvalidPatch('scene commission requires an executable scene')
        if job['kind']=='scene' and not triggered:raise InvalidPatch('scene commission needs a player-facing scene trigger')
        if job['kind']=='ability' and not set(job['skills'])<=granted:raise InvalidPatch('ability commission must provide an earned learning action')
        if job['kind']=='encounter' and world.state['game_spec']['systems']['combat'] and not any(e['kind']=='enemy' for e in entities):raise InvalidPatch('encounter commission requires an actual enemy')
    if ctx.get('commission_ids'):
        for field in ('object_updates','paint','npc_lines','weather','rule','locations','future_updates'):
            if body.get(field):raise InvalidPatch('a content worker may add definitions, not directly rewrite world facts: '+field)

def install(world,region,body,ctx):
    from . import adventure
    from .visuals import freeze_sprite
    adv=adventure.state(world)
    if not adv:return
    for e in region['entities']:
        if not e.get('actor_id'):continue
        actor=adv['cast'][e['actor_id']];key=e.get('sprite')
        if key in region.get('visuals',{}).get('sprites',{}):
            actor.setdefault('visual',freeze_sprite(region['visuals']['sprites'][key],region['visuals']['palette']))
            region['visuals']['sprites'][key]=copy.deepcopy(actor['visual'])
    for a in body.get('abilities',[]):adv['skills'][a['id']]['rule']=copy.deepcopy(a)
    scenes={s['id']:s for s in region.get('scenes',[])}
    scenes.update({s['id']:copy.deepcopy(s) for s in body.get('scenes',[])})
    region['scenes']=list(scenes.values())
    for job in ctx.get('content_contract',{}).get('commissions',[]):
        adv['jobs'][job['id']]['status']='applied'
        adv['jobs'][job['id']]['receipt']=dict(summary=body.get('text',body.get('description',''))[:400],scenes=[s['id'] for s in body.get('scenes',[])],abilities=[a['id'] for a in body.get('abilities',[])])
    adventure.sync_cast(world,region)

def show(vm,key):
    if vm.s['battle']:raise InvalidPatch('story scenes require exploration')
    scene=next((s for s in vm.region.get('scenes',[]) if s['id']==key),None)
    if not scene:raise InvalidPatch('unknown story scene')
    cast=vm.s.get('adventure',{}).get('cast',{})
    lines=[(cast[line['speaker']]['name']+'：' if line['speaker']!='narrator' else '')+line['text'] for line in scene['lines']]
    choices=[dict(id='scene:'+key+':'+c['id'],label=c['label'],description=c['label'],enabled=bool(vm.expr(c['when'])),blocked_reason='当前条件尚未满足。',scope='explore',target='player') for c in scene['choices']]
    speakers=list(dict.fromkeys(line['speaker'] for line in scene['lines'] if line['speaker']!='narrator'))
    portraits=[dict(name=cast[k]['name'],visual=cast[k]['visual']) for k in speakers if cast[k].get('visual')]
    vm.s['ui']=dict(kind='actions' if choices else 'message',title=scene['title'],lines=lines,actions=choices,portraits=portraits,scene_id=key,scene_token=vm.s['story_revision'])

def choose(world,key):
    from .runtime import Runtime
    ui=world.state['ui'];scene=next(s for s in world.region().get('scenes',[]) if s['id']==ui['scene_id'])
    choice=next((c for c in scene['choices'] if key=='scene:'+scene['id']+':'+c['id']),None)
    vm=Runtime(world,world.region())
    if not choice or not vm.expr(choice['when']):raise InvalidPatch('scene choice is unavailable')
    world.state['ui']={};vm.run(choice['effects']);vm.emit('choice',choice=choice['id'],advance=True)
    from .gameplay import show_messages
    show_messages(world,vm)
    event,_=world.story('choice',choice['label'],dict(scene=scene['id']));world.persist(world.region(),event=event)
