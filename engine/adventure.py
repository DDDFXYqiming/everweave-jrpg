"""Global creative definitions and work orders; all facts live in the world store."""
import copy
import hashlib
import json
import time
from .diagnostics import InvalidPatch

def state(world):return world.state.get('adventure') if world.state else None

def visible(world,m):
    adv=state(world)
    if m.get('discovered'):return True
    dependencies=all(adv['missions'][d]['status']=='complete' for d in m['depends'])
    revealed=dependencies and (world.state['topology'][m['region']]['visited'] or m['kind']=='main' and bool(m['depends']))
    if m.get('reveal_when'):
        from .campaign import satisfied
        revealed=dependencies and satisfied(m['reveal_when'],world.state['campaign']['chapters'][m['chapter_id']]['flags'])
    return revealed

def register_mission(world,m):
    if visible(world,m):
        m['discovered']=True
        world.state['quests'][m['id']]=dict(id=m['id'],name=m['name'],description=m['brief'],goal='adventure',region=m['region'],status=m['status'],reward=0)

def validate(raw,flags,regions,existing=None):
    from .schema import obj,arr,ident,text
    from .content import state_values,integer,boolean
    from .campaign import conditions
    obj(raw,'adventure',('cast','skills','missions','endings','economy','commissions'))
    old=existing or {};out=dict(cast=[],skills=[],missions=[],endings=[],economy={},commissions=[])
    for actor in arr(raw.get('cast',[]),'cast',8):
        obj(actor,'cast member',('id','name','role','motive','state'),('id','name','role','motive'))
        values=state_values(actor.get('state',{'alive':True,'trust':0}));values.setdefault('alive',True)
        if type(values['alive']) is not bool:raise InvalidPatch('cast.alive must be boolean')
        if any(type(v) in (int,float) and not -100<=v<=100 for v in values.values()):raise InvalidPatch('cast numeric state is bounded to -100..100')
        out['cast'].append(dict(id=ident(actor['id']),name=text(actor['name'],'cast name',48),role=text(actor['role'],'role',120),motive=text(actor['motive'],'motive',300),state=values))
    for skill in arr(raw.get('skills',[]),'skills',6):
        obj(skill,'skill brief',('id','name','description','scope'),('id','name','description','scope'))
        if skill['scope'] not in ('explore','combat'):raise InvalidPatch('invalid skill scope')
        out['skills'].append(dict(id=ident(skill['id']),name=text(skill['name'],'skill name',64),description=text(skill['description'],'skill brief',300),scope=skill['scope']))
    mission_ids=set()
    for m in arr(raw.get('missions',[]),'missions',10):
        if not isinstance(m,dict) or 'id' not in m:raise InvalidPatch('mission requires an id')
        mission_ids.add(ident(m['id']))
    for mission in raw.get('missions',[]):
        obj(mission,'mission',('id','name','kind','region','brief','depends','when','fail_when','reveal_when'),('id','name','kind','region','brief','when'))
        if mission['kind'] not in ('main','side','encounter'):raise InvalidPatch('mission kind must be main/side/encounter')
        rid=ident(mission['region'])
        if rid not in regions:raise InvalidPatch('unknown mission region '+rid)
        dependencies=[ident(x) for x in arr(mission.get('depends',[]),'mission dependencies',6)]
        if not set(dependencies)<=(mission_ids|set(old.get('missions',{}))):raise InvalidPatch('unknown mission dependency')
        when=conditions(mission['when'],flags)
        if not when:raise InvalidPatch('mission needs a real completion condition')
        out['missions'].append(dict(id=ident(mission['id']),name=text(mission['name'],'mission name',100),kind=mission['kind'],region=rid,brief=text(mission['brief'],'mission brief',450),depends=dependencies,when=when,fail_when=conditions(mission.get('fail_when',[]),flags),reveal_when=conditions(mission.get('reveal_when',[]),flags)))
    pending={m['id']:set(m['depends'])&mission_ids for m in out['missions']}
    while pending:
        roots={k for k,v in pending.items() if not v}
        if not roots:raise InvalidPatch('mission dependencies must not form a cycle')
        pending={k:v-roots for k,v in pending.items() if k not in roots}
    for ending in arr(raw.get('endings',[]),'endings',4):
        obj(ending,'ending',('id','name','description','requires','final'),('id','name','description','requires'))
        requires=[ident(x) for x in arr(ending['requires'],'ending requirements',10,1)]
        if not set(requires)<=(mission_ids|set(old.get('missions',{}))):raise InvalidPatch('unknown ending requirement')
        out['endings'].append(dict(id=ident(ending['id']),name=text(ending['name'],'ending name',100),description=text(ending['description'],'ending description',500),requires=requires,final=boolean(ending.get('final',False))))
    economy=raw.get('economy',{})
    if not isinstance(economy,dict) or len(economy)>8:raise InvalidPatch('economy requires up to eight resource gain limits')
    out['economy']={ident(k):integer(v,1,100000,'gain limit') for k,v in economy.items()}
    actors={a['id'] for a in out['cast']}|set(old.get('cast',{}));skills={a['id'] for a in out['skills']}|set(old.get('skills',{}))
    for job in arr(raw.get('commissions',[]),'commissions',8):
        obj(job,'commission',('id','kind','region','brief','cast','skills','missions','requires','limits'),('id','kind','region','brief'))
        if job['kind'] not in ('scene','encounter','quest','ability'):raise InvalidPatch('unsupported commission kind')
        if not isinstance(job['region'],str) or job['region'] not in regions:raise InvalidPatch('unknown commission region')
        entry=dict(id=ident(job['id']),kind=job['kind'],region=job['region'],brief=text(job['brief'],'commission brief',600))
        limits=job.get('limits',{})
        obj(limits,'encounter limits',('enemy_hp','enemy_attack','max_enemies'))
        entry['limits']={k:integer(v,1,{'enemy_hp':2000,'enemy_attack':200,'max_enemies':8}[k],k) for k,v in limits.items()}
        for field,known in (('cast',actors),('skills',skills),('missions',mission_ids|set(old.get('missions',{}))),('requires',mission_ids|set(old.get('missions',{})))):
            values=[ident(v) for v in arr(job.get(field,[]),field,6)]
            if not set(values)<=known:raise InvalidPatch('unknown '+field+' in commission')
            entry[field]=values
        out['commissions'].append(entry)
    for group in ('cast','skills','missions','endings','commissions'):
        if len({v['id'] for v in out[group]})!=len(out[group]):raise InvalidPatch('duplicate '+group+' definition')
    return out

def install(world,raw,mapping,cid,prefix):
    adv=world.state.setdefault('adventure',dict(cast={},skills={},missions={},endings={},jobs={},economy={},revision=0,event_seq=0,reviewed_seq=0))
    changed=(any(a['id'] not in adv['cast'] for a in raw['cast']) or any(a['id'] not in adv['skills'] for a in raw['skills'])
             or any(raw[k] for k in ('missions','endings','commissions')) or any(k not in adv['economy'] for k in raw['economy']))
    for actor in raw['cast']:
        if actor['id'] in adv['cast']:
            if actor['name']!=adv['cast'][actor['id']]['name']:raise InvalidPatch('persistent cast name is immutable')
        else:adv['cast'][actor['id']]=copy.deepcopy(actor)
    for skill in raw['skills']:
        if skill['id'] in adv['skills'] and any(skill[k]!=adv['skills'][skill['id']][k] for k in ('name','scope')):raise InvalidPatch('use a new skill ID for a different ability')
        adv['skills'].setdefault(skill['id'],copy.deepcopy(skill))
    mission_map={m['id']:prefix+'_'+m['id'] for m in raw['missions']}
    for m in raw['missions']:
        entry=copy.deepcopy(m);entry.update(id=mission_map[m['id']],region=mapping[m['region']],chapter_id=cid,status='active',depends=[mission_map.get(x,x) for x in m['depends']])
        adv['missions'][entry['id']]=entry
    for entry in [adv['missions'][key] for key in mission_map.values()]:register_mission(world,entry)
    for ending in raw['endings']:
        entry=copy.deepcopy(ending);entry.update(id=prefix+'_'+ending['id'],requires=[mission_map.get(x,x) for x in ending['requires']],shown=False)
        adv['endings'][entry['id']]=entry
    for job in raw['commissions']:
        entry=copy.deepcopy(job);entry.update(id=prefix+'_'+job['id'],region=mapping[job['region']],chapter_id=cid,status='queued',requires=[mission_map.get(x,x) for x in job['requires']],missions=[mission_map.get(x,x) for x in job['missions']])
        adv['jobs'][entry['id']]=entry
    for key,limit in raw['economy'].items():adv['economy'].setdefault(key,limit)
    if changed:adv['revision']+=1

def dependencies(world,ctx):
    """Versions only for the identities and work this author actually consumes."""
    adv=state(world)
    if not adv:return None
    contract=ctx.get('content_contract',{})
    ids={a['id'] for a in contract.get('cast',[])}
    skills={a['id'] for a in contract.get('skills',[])}
    jobs={a['id'] for a in contract.get('commissions',[])}
    data=dict(cast={k:{f:v for f,v in adv['cast'].get(k,{}).items() if f!='visual'} for k in sorted(ids)},
              skills={k:adv['skills'].get(k) for k in sorted(skills)},
              jobs={k:{f:v for f,v in adv['jobs'].get(k,{}).items() if f not in ('last_error','receipt')} for k in sorted(jobs)})
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def ready_jobs(world,rid):
    adv=state(world)
    if not adv:return []
    return [j for j in adv['jobs'].values() if j['region']==rid and j['status']=='queued' and all(adv['missions'][m]['status']=='complete' for m in j['requires'])]

def context(world,rid):
    adv=state(world)
    if not adv:return {}
    jobs=ready_jobs(world,rid)
    current=world.cache.get(rid,{})
    actor_ids={k for j in jobs for k in j['cast']}|{e.get('actor_id') for e in current.get('entities',[])}
    skill_ids={k for j in jobs for k in j['skills']}|set(world.state['player'].get('abilities',[]))
    return dict(adventure_revision=adv['revision'],reserve_director_gates=True,content_contract=dict(commissions=copy.deepcopy(jobs),
        cast=copy.deepcopy([v for k,v in adv['cast'].items() if k in actor_ids]),skills=copy.deepcopy([v for k,v in adv['skills'].items() if k in skill_ids]),learned=list(world.state['player'].get('abilities',[])),
        missions=copy.deepcopy([m for m in adv['missions'].values() if m['region']==rid or m['status']=='active'][-16:]),economy=copy.deepcopy(adv['economy'])))

def refresh(world):
    from .campaign import satisfied
    adv=state(world)
    if not adv:return
    for _ in range(len(adv['missions'])+1):
        changed=False
        for m in adv['missions'].values():
            if m['status']!='active':continue
            flags=world.state['campaign']['chapters'][m['chapter_id']]['flags']
            status='failed' if m['fail_when'] and satisfied(m['fail_when'],flags) else 'complete' if all(adv['missions'][d]['status']=='complete' for d in m['depends']) and satisfied(m['when'],flags) else 'active'
            if status!='active':
                m['status']=status;adv['event_seq']+=1;adv['important_seq']=adv['event_seq']
                if visible(world,m):world.note(m['name'])
                changed=True
        if not changed:break
    for m in adv['missions'].values():register_mission(world,m)
    if world.state.get('pending_ending') or world.state.get('game_over'):return
    for end in adv['endings'].values():
        if not end['shown'] and all(adv['missions'][m]['status']=='complete' for m in end['requires']):
            end['shown']=True;world.note(end['description'])
            world.state['pending_ending']={k:end[k] for k in ('id','name','description','final')}
            break

def record(world,event):
    adv=state(world)
    if not adv or not event:return
    kind=event.get('type')
    if kind not in ('arrival','victory','objective','choice','interaction','discovery','use'):return
    signature=(event.get('region','')+':'+kind+':'+str(event.get('data',{}).get('action',event.get('text',''))))
    seen=adv.setdefault('recent_review_events',[])
    if kind in ('interaction','use') and signature in seen:return
    seen.append(signature);adv['recent_review_events']=seen[-64:]
    adv['event_seq']+=1
    if kind in ('victory','objective','choice','discovery'):adv['important_seq']=adv['event_seq']

def review_due(world):
    adv=state(world)
    if not adv:return False
    return (adv.get('important_seq',0)>adv['reviewed_seq'] or
            adv['event_seq']-adv['reviewed_seq']>=8 and time.time()-adv.get('last_review_time',0)>=90)

def memory(world):
    adv=state(world)
    if not adv:return None
    return dict(cast=[{k:copy.deepcopy(a[k]) for k in ('id','name','role','motive','state')} for a in list(adv['cast'].values())[-16:]],
                skills=[{k:copy.deepcopy(a[k]) for k in ('id','name','description','scope')} for a in list(adv['skills'].values())[-16:]],
                missions=copy.deepcopy(list(adv['missions'].values())[-24:]),economy=copy.deepcopy(adv['economy']))

def director_context(world):
    adv=state(world);s=world.state;cid=s['campaign']['active'];c=s['campaign']['chapters'][cid]
    return dict(kind='direction',target=s['current'],epoch=s['epoch'],story_revision=s['story_revision'],content_version=2,
        adventure_revision=adv['revision'],event_seq=adv['event_seq'],setting=s['setting'],game_spec=s['game_spec'],chapter_id=cid,
        chapter={k:copy.deepcopy(c.get(k)) for k in ('goal','flags','flag_sources','regions','links','planning','ending_brief')},
        cast=memory(world)['cast'],skills=memory(world)['skills'],
        missions=copy.deepcopy(list(adv['missions'].values())[-24:]),jobs=copy.deepcopy(list(adv['jobs'].values())[-16:]),
        known_regions=[dict(id=rid,name=n['name'],visited=n['visited'],ready=n['ready']) for rid,n in s['topology'].items()][-32:],
        recent_events=world.store.recent_events(12),economy=adv['economy'])

def validate_direction(world,raw):
    import json
    from .schema import obj,text,arr,ident
    from .campaign import conditions
    if isinstance(raw,str):
        try:raw=json.loads(raw)
        except ValueError as exc:raise InvalidPatch('direction must be JSON') from exc
    obj(raw,'direction envelope',('kind','direction'),('kind','direction'))
    if raw['kind']!='direction':raise InvalidPatch('expected direction')
    d=obj(raw['direction'],'direction',('reason','additions','region_briefs','links','new_flags','new_regions'),('reason',))
    s=world.state;adv=state(world);cid=s['campaign']['active'];c=s['campaign']['chapters'][cid]
    regions={rid for rid,n in s['topology'].items() if n.get('chapter_id')==cid}
    new_regions=[]
    for node in arr(d.get('new_regions',[]),'new regions',2):
        obj(node,'new region',('id','name','description','purpose'),('id','name','description','purpose'))
        key=ident(node['id'])
        if key in s['topology'] or key in regions:raise InvalidPatch('new region must have a fresh canonical ID')
        regions.add(key);new_regions.append(dict(id=key,**{k:text(node[k],k,450) for k in ('name','description','purpose')}))
    if new_regions and len(regions)>16:raise InvalidPatch('chapter region capacity reached; continue in the next chapter')
    flags=dict(c['flags']);new_flags=[]
    for entry in arr(d.get('new_flags',[]),'new flags',6):
        obj(entry,'new flag',('id','initial','source'),('id','initial','source'));key=ident(entry['id'])
        if key in flags:raise InvalidPatch('director may declare new flags, never overwrite existing ones')
        if not isinstance(entry['source'],str) or entry['source'] not in regions:raise InvalidPatch('new flag source must be a chapter region')
        if not (type(entry['initial']) is bool and entry['initial'] is False or type(entry['initial']) is int and entry['initial']==0 or entry['initial']=='pending'):raise InvalidPatch('new flags start false, zero or pending; progress must be earned')
        flags[key]=entry['initial'];new_flags.append(copy.deepcopy(entry))
    if len(flags)>64:raise InvalidPatch('chapter flag capacity reached; continue in a new chapter')
    additions=validate(d.get('additions',{}),flags,regions,adv)
    for flag in new_flags:
        producers=[j for j in additions['commissions'] if j['region']==flag['source']]
        if not producers:raise InvalidPatch('new flags need a matching content commission to implement them')
        producers[0].setdefault('flag_writes',[]).append(flag['id'])
    if additions['economy']:raise InvalidPatch('the global resource gain policy is fixed; do not change it mid-run')
    if len([j for j in adv['jobs'].values() if j['status']=='queued'])+len(additions['commissions'])>8:raise InvalidPatch('too many queued commissions')
    for m in additions['missions']:
        from .campaign import satisfied
        if satisfied(m['when'],flags):raise InvalidPatch('new missions must not retroactively claim completed conditions')
    briefs=[]
    for b in arr(d.get('region_briefs',[]),'region briefs',3):
        obj(b,'region brief',('region','purpose'),('region','purpose'));rid=b['region']
        if not isinstance(rid,str) or rid not in s['topology'] or rid not in regions or s['topology'][rid]['visited']:raise InvalidPatch('only unvisited region briefs can change')
        briefs.append(dict(region=rid,purpose=text(b['purpose'],'purpose',450)))
    links=[]
    for e in arr(d.get('links',[]),'new routes',4 if new_regions else 2):
        obj(e,'new route',('id','a','b','hidden','discover','requires','blocked_reason','one_way'),('id','a','b'))
        if not all(isinstance(e[k],str) and e[k] in regions for k in ('a','b')) or e['a']==e['b']:raise InvalidPatch('new routes connect two current chapter locations')
        hidden=e.get('hidden',False)
        if type(hidden) is not bool:raise InvalidPatch('hidden must be boolean')
        if type(e.get('one_way',False)) is not bool:raise InvalidPatch('one_way must be boolean')
        discover=conditions(e.get('discover',[]),flags)
        if hidden and not discover:raise InvalidPatch('hidden route needs discovery conditions')
        links.append(dict(id=ident(e['id']),a=e['a'],b=e['b'],hidden=hidden,one_way=e.get('one_way',False),discover=discover,requires=conditions(e.get('requires',[]),flags),blocked_reason=text(e.get('blocked_reason','道路尚未打通。'),'blocked reason',160)))
    if len({e['id'] for e in links})!=len(links):raise InvalidPatch('new route IDs must be unique')
    reached=regions-{r['id'] for r in new_regions}
    for _ in range(len(new_regions)+1):
        for edge in links:
            if edge['a'] in reached:reached.add(edge['b'])
            if not edge['one_way'] and edge['b'] in reached:reached.add(edge['a'])
    if reached!=regions:raise InvalidPatch('new locations need an actual outbound connection from the known chapter')
    return dict(reason=text(d['reason'],'director reasoning',600),additions=additions,region_briefs=briefs,links=links,new_flags=new_flags,new_regions=new_regions)

def apply_direction(world,data,ctx):
    from . import campaign
    s=world.state;adv=state(world);cid=s['campaign']['active'];c=s['campaign']['chapters'][cid];prefix='d'+str(adv['revision']+1)
    touched=[]
    before_revision=adv['revision']
    new_ids={r['id'] for r in data.get('new_regions',[])}
    for node in data.get('new_regions',[]):
        rid=node['id'];c['regions'].append(copy.deepcopy(node))
        s['topology'][rid]=dict(parent=s['current'],depth=s['topology'][s['current']]['depth']+1,ready=False,visited=False,name=node['name'],outline=copy.deepcopy(node),children=[],chapter_id=cid)
    for flag in data['new_flags']:
        c['flags'][flag['id']]=flag['initial'];c['flag_sources'][flag['id']]=flag['source']
        node=s['topology'][flag['source']];node['generation_revision']=node.get('generation_revision',0)+1
    for e in data['links']:
        entry=dict(e,id=prefix+'_'+e['id'],chapter_id=cid,revealed=not e['hidden'])
        for side in ('a','b'):
            rid=e[side];used={r['anchor'] for r in campaign.routes(s,rid)}
            anchor=('link_'+hashlib.sha256(entry['id'].encode()).hexdigest()[:12]) if rid in new_ids else next((f'director_gate_{i}' for i in range(2) if f'director_gate_{i}' not in used),None)
            if anchor is None:raise InvalidPatch('no reserved director gate remains at '+rid)
            region=world.region(rid)
            if region and anchor not in region.get('scene',{}).get('anchors',{}):raise InvalidPatch('region has no reserved director gate '+rid)
            if region:
                from .scene import cells_for
                from .pcg import reachable
                at=tuple(region['scene']['anchors'][anchor])
                if any(not obj.get('spent') and at in cells_for(obj) for obj in region['entities']+region.get('props',[]) if obj.get('solid') or obj in region['entities']):
                    raise InvalidPatch('reserved director gate is now occupied: '+rid)
                if at not in reachable(region['tiles'],region['spawn']):
                    raise InvalidPatch('reserved director gate is no longer structurally reachable: '+rid)
            entry['anchor_'+side]=anchor
        c['links'].append(entry)
        for rid in (e['a'],e['b']):
            n=s['topology'][rid];n['generation_revision']=n.get('generation_revision',0)+1
            region=world.region(rid)
            if region:touched.append(region)
    for b in data['region_briefs']:
        node=s['topology'][b['region']];outline=dict(node['outline'],purpose=b['purpose'])
        world._update_outline(node,outline)
    install(world,data['additions'],{rid:rid for rid in s['topology']},cid,prefix)
    if any(data.get(k) for k in ('new_regions','new_flags','links','region_briefs')) and adv['revision']==before_revision:adv['revision']+=1
    adv['reviewed_seq']=max(adv['reviewed_seq'],ctx['event_seq']);adv['last_reason']=data['reason'];adv['last_review_time']=time.time()
    world.persist(*touched)

def check_gain(world,key,amount):
    if type(amount) not in (int,float):raise InvalidPatch('resource gain must be numeric')
    adv=state(world)
    if not adv or amount<=0 or key not in adv['economy']:return
    batch=getattr(world,'_batch',None)
    gains=batch.setdefault('resource_gains',{}) if batch is not None else {}
    total=gains.get(key,0)+amount
    if total>adv['economy'][key]:raise InvalidPatch('action exceeds the director resource gain budget for '+key)
    gains[key]=total

def sync_cast(world,region):
    adv=state(world)
    if not adv:return
    for e in region['entities']:
        if e.get('actor_id') in adv['cast']:
            actor=adv['cast'][e['actor_id']];e['name']=actor['name']
            if not actor['state']['alive']:e['spent']=True

def public_view(world):
    adv=state(world)
    if not adv:return None
    return dict(missions=[dict(id=m['id'],name=m['name'],kind=m['kind'],brief=m['brief'],status=m['status']) for m in adv['missions'].values() if m['status']=='active' and visible(world,m)][-12:],
        skills=[dict(id=k,name=adv['skills'][k]['name']) for k in world.state['player'].get('abilities',[]) if k in adv['skills']])
