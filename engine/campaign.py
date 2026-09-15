"""Persistent chapter plans, shared story state, and real bidirectional world links."""
import copy
import json
import hashlib
from collections import deque
from .diagnostics import InvalidPatch
from . import game_spec

def conditions(raw,flags):
    from .schema import arr,obj,ident
    out=[]
    for c in arr(raw,'conditions',12):
        obj(c,'condition',('flag','eq'),('flag','eq'));key=ident(c['flag'])
        if key not in flags or type(c['eq']) is not type(flags[key]):raise InvalidPatch('condition must reference a declared flag with matching type')
        out.append(copy.deepcopy(c))
    return out

def validate(raw,first=True,existing=None,corrections=None):
    from .schema import obj,arr,ident,text
    from .content import state_values,boolean
    if isinstance(raw,str):
        try:raw=json.loads(raw)
        except (ValueError,TypeError) as exc:raise InvalidPatch('campaign must be valid JSON') from exc
    obj(raw,'campaign envelope',('kind','campaign'),('kind','campaign'))
    if raw['kind']!='campaign':raise InvalidPatch('expected kind=campaign')
    candidate=raw.get('campaign')
    if first and isinstance(candidate,dict) and 'failure_mode' in candidate and isinstance(candidate.get('game_spec'),dict):
        if 'failure_mode' not in candidate['game_spec'] or candidate['game_spec']['failure_mode']==candidate['failure_mode']:
            raw=copy.deepcopy(raw);candidate=raw['campaign'];value=candidate.pop('failure_mode');candidate['game_spec']['failure_mode']=value
            if corrections is not None:corrections.append(dict(path='campaign.failure_mode',target='campaign.game_spec.failure_mode',reason='unambiguous game specification field placement'))
    r=obj(raw['campaign'],'campaign',('title','premise','goal','game_spec','flags','flag_sources','regions','links','milestones','complete_when','continuation','adventure','planning','ending_brief'),('title','premise','goal','flags','flag_sources','regions','links','milestones','complete_when','continuation'))
    rolling=r.get('planning')=='rolling'
    if r.get('planning','chapter') not in ('rolling','chapter'):raise InvalidPatch('planning must be rolling or chapter')
    out={k:text(r[k],k,500) for k in ('title','premise','goal')};out['flags']=state_values(r['flags'])
    out['planning']='rolling' if rolling else 'chapter'
    out['ending_brief']=text(r.get('ending_brief',''),'ending brief',500) if r.get('ending_brief') else ''
    if first:
        if 'game_spec' not in r:raise InvalidPatch('opening campaign needs game_spec')
        out['game_spec']=game_spec.validate(r['game_spec'])
    elif 'game_spec' in r:raise InvalidPatch('game_spec is fixed for this world; do not replace it')
    regions=[];ids=set()
    for node in arr(r['regions'],'chapter regions',4 if rolling else 8,2 if rolling else 4):
        obj(node,'chapter region',('id','name','description','purpose'),('id','name','description','purpose'))
        key=ident(node['id'])
        if len(key)>20 or key in ids:raise InvalidPatch('region IDs must be unique and at most 20 characters')
        ids.add(key);regions.append(dict(id=key,**{k:text(node[k],k,450) for k in ('name','description','purpose')}))
    out['regions']=regions;out['links']=[];pairs=set();link_ids=set();adj={key:set() for key in ids}
    sources=r['flag_sources']
    if not isinstance(sources,dict) or set(sources)!=set(out['flags']) or any(not isinstance(v,str) or v not in ids for v in sources.values()):raise InvalidPatch('flag_sources must assign every flag to one chapter region')
    out['flag_sources']=copy.deepcopy(sources)
    for link in arr(r['links'],'chapter links',14,1 if rolling else 4):
        obj(link,'chapter link',('id','a','b','hidden','discover','requires','blocked_reason','one_way'),('id','a','b'))
        key=ident(link['id']);a=ident(link['a']);b=ident(link['b']);pair=tuple(sorted((a,b)))
        if key in link_ids:raise InvalidPatch('duplicate link ID',path='campaign.links',value=key)
        if a==b or a not in ids or b not in ids:raise InvalidPatch('link endpoints must be distinct declared region IDs',path='campaign.links.'+key,value=[a,b],expected=sorted(ids))
        hidden=boolean(link.get('hidden',False));discover=conditions(link.get('discover',[]),out['flags']);requires=conditions(link.get('requires',[]),out['flags'])
        if hidden and not discover:raise InvalidPatch('a hidden route needs discover conditions')
        out['links'].append(dict(id=key,a=a,b=b,hidden=hidden,one_way=boolean(link.get('one_way',False)),discover=discover,requires=requires,blocked_reason=text(link.get('blocked_reason','这条道路尚未打通。'),'blocked reason',160)))
        link_ids.add(key);pairs.add(pair);adj[a].add(b);adj[b].add(a)
    start=regions[0]['id'];seen={start};queue=deque([start])
    while queue:
        for node in adj[queue.popleft()]-seen:seen.add(node);queue.append(node)
    if seen!=ids or not rolling and (len(pairs)<len(ids) or max(map(len,adj.values()))<3):raise InvalidPatch('chapter graph needs connected branches and at least one loop, not a linear chain')
    if max(map(len,adj.values()))>6:raise InvalidPatch('limit each location to six chapter routes')
    if any(sum(key in (e['a'],e['b']) for e in out['links'])>6 for key in ids):raise InvalidPatch('limit each location to six physical routes, including parallel routes')
    # The arrival cannot be stranded behind unknown flags.
    if not any((start==e['a'] or start==e['b'] and not e['one_way']) and not e['hidden'] and satisfied(e['requires'],out['flags']) for e in out['links']):raise InvalidPatch('arrival needs an initially usable visible route')
    directed_seen={start};queue=deque([start])
    while queue:
        source=queue.popleft()
        for edge in out['links']:
            target=edge['b'] if source==edge['a'] else edge['a'] if source==edge['b'] and not edge['one_way'] else None
            if target and target not in directed_seen:directed_seen.add(target);queue.append(target)
    if directed_seen!=ids:raise InvalidPatch('one-way routes make a planned location structurally unreachable')
    out['milestones']=[];goal_ids=set()
    for m in arr(r['milestones'],'milestones',8,1):
        obj(m,'milestone',('id','name','description','when'),('id','name','description','when'))
        key=ident(m['id']);when=conditions(m['when'],out['flags'])
        if key in goal_ids or not when:raise InvalidPatch('milestones require unique IDs and nonempty conditions')
        goal_ids.add(key);out['milestones'].append(dict(id=key,name=text(m['name'],'milestone name',100),description=text(m['description'],'milestone description',400),when=when))
    out['complete_when']=conditions(r['complete_when'],out['flags'])
    if not out['complete_when'] or satisfied(out['complete_when'],out['flags']):raise InvalidPatch('chapter must have an unfinished completion condition')
    c=obj(r['continuation'],'continuation',('from','hook'),('from','hook'))
    if not isinstance(c['from'],str) or c['from'] not in ids:raise InvalidPatch('continuation.from must be a chapter region')
    out['continuation']=dict(c,hook=text(c['hook'],'continuation hook',400))
    if 'adventure' in r:
        from .adventure import validate as validate_adventure
        out['adventure']=validate_adventure(r['adventure'],out['flags'],ids,existing)
    return out

def satisfied(conditions,flags):return all(flags.get(c['flag'])==c['eq'] for c in conditions)
def book(state):return state.get('campaign')
def chapter(state,rid):
    node=state['topology'].get(rid,{})
    return (book(state) or {}).get('chapters',{}).get(node.get('chapter_id'))

def links(state,rid,visible=False):
    result=[]
    for c in (book(state) or {}).get('chapters',{}).values():
        for edge in c['links']:
            if rid in (edge['a'],edge['b']) and (not visible or edge['revealed']):result.append(edge)
    return result

def neighbors(state,rid,visible=False):return [e['b'] if e['a']==rid else e['a'] for e in links(state,rid,visible) if rid==e['a'] or not e.get('one_way')]
def routes(state,rid):
    return [dict(target=e['b'] if e['a']==rid else e['a'],direction='forward',label=state['topology'][e['b'] if e['a']==rid else e['a']]['name'],anchor=e.get('anchor_a' if e['a']==rid else 'anchor_b','link_'+hashlib.sha256(e['id'].encode()).hexdigest()[:12]),link_id=e['id']) for e in links(state,rid)]

def apply(world,plan):
    s=world.state;b=s['campaign'];number=len(b['chapters'])+1;cid='c'+str(number)
    old=b['chapters'].get(b.get('active'));mapping={r['id']:('r0' if number==1 and i==0 else cid+'_'+r['id']) for i,r in enumerate(plan['regions'])}
    if number==1:game_spec.install(s,plan['game_spec']);s['title']=plan['title']
    for i,r in enumerate(plan['regions']):
        rid=mapping[r['id']]
        if rid=='r0':node=s['topology'][rid];node.update(name=r['name'],outline=copy.deepcopy(r))
        else:
            parent='r0' if number==1 else mapping[plan['regions'][0]['id']] if i else old['continuation']['from']
            node=dict(parent=parent,depth=number,ready=False,visited=False,name=r['name'],outline=copy.deepcopy(r),children=[])
            s['topology'][rid]=node
        node['chapter_id']=cid
    c=copy.deepcopy(plan);c.pop('game_spec',None);c.update(id=cid,complete=False)
    c['regions']=[dict(r,id=mapping[r['id']]) for r in plan['regions']]
    c['flag_sources']={k:mapping[v] for k,v in c['flag_sources'].items()}
    c['continuation']['from']=mapping[c['continuation']['from']]
    c['links']=[dict(e,id=cid+'_'+e['id'],a=mapping[e['a']],b=mapping[e['b']],chapter_id=cid,revealed=not e['hidden']) for e in plan['links']]
    if old:
        first=mapping[plan['regions'][0]['id']]
        c['links'].append(dict(id=cid+'_arrival',a=old['continuation']['from'],b=first,anchor_a='chapter_gate',chapter_id=cid,revealed=True,hidden=False,discover=[],requires=[],blocked_reason=''))
    b['chapters'][cid]=c;b.update(active=cid,pending=False,revision=b['revision']+1)
    if plan.get('adventure'):
        from .adventure import install
        install(world,plan['adventure'],mapping,cid,cid)
    for m in c['milestones']:
        s['quests'][cid+':'+m['id']]=dict(id=cid+':'+m['id'],name=m['name'],description=m['description'],status='active',goal='campaign',region='',reward=0)
    world.note(plan['goal']);world.persist()
    if old:
        region=world.region(old['continuation']['from'])
        if region:sync_gates(world,region);world.persist(region)

def refresh(world):
    s=world.state;b=book(s)
    if not b:return
    for cid,c in b['chapters'].items():
        for e in c['links']:
            if e['hidden'] and not e['revealed'] and satisfied(e['discover'],c['flags']):e['revealed']=True
        for m in c['milestones']:
            q=s['quests'][cid+':'+m['id']]
            if q['status']=='active' and satisfied(m['when'],c['flags']):
                q['status']='complete'
                if not s.get('adventure'):world.note(m['name'])
        if not c['complete'] and satisfied(c['complete_when'],c['flags']):
            c['complete']=True
            if cid==b['active']:b['pending']=True;b['revision']+=1;world.note(c['continuation']['hook'])

def sync_gates(world,region):
    s=world.state
    if not chapter(s,region['id']):return
    existing={e.get('link_id'):e for e in region['entities'] if e['kind']=='exit'}
    for route in routes(s,region['id']):
        key=route['link_id'];edge=next(e for e in links(s,region['id']) if e['id']==key)
        if key not in existing:
            pos=region['scene']['anchors'].get(route['anchor'])
            if pos is None:raise InvalidPatch('missing reserved chapter route anchor '+route['anchor'])
            if any((e['x'],e['y'])==tuple(pos) for e in region['entities']):raise InvalidPatch('chapter route anchor is occupied')
            region['entities'].append(dict(id=region['id']+':gate_'+key,kind='exit',x=pos[0],y=pos[1],spent=False,solid=False,**route));existing[key]=region['entities'][-1]
        e=existing[key];e.update(name=route['label'],spent=not edge['revealed'] or bool(edge.get('one_way') and region['id']==edge['b']),locked=not satisfied(edge['requires'],s['campaign']['chapters'][edge['chapter_id']]['flags']),blocked_reason=edge['blocked_reason'])

def context(world,rid):
    s=world.state;c=chapter(s,rid)
    if not c:return {}
    authored_routes=routes(s,rid)
    for route in authored_routes:
        edge=next(e for e in links(s,rid) if e['id']==route['link_id'])
        route.update({k:copy.deepcopy(edge.get(k,False if k=='one_way' else [] if k in ('requires','discover') else '')) for k in ('hidden','discover','requires','blocked_reason','one_way')})
        owner=s['campaign']['chapters'][edge['chapter_id']]
        route['condition_sources']={v['flag']:owner['flag_sources'].get(v['flag']) for v in edge['requires']+edge['discover']}
        route['outbound']=rid==edge['a'] or not edge.get('one_way')
    return dict(game_spec=s['game_spec'],chapter_plan={k:copy.deepcopy(c[k]) for k in ('id','title','premise','goal','flags','flag_sources','regions','milestones','complete_when')},region_purpose=s['topology'][rid]['outline']['purpose'],planned_routes=authored_routes,required_flag_writes=[k for k,v in c['flag_sources'].items() if v==rid],
                reserve_chapter_gate=rid==c['continuation']['from'])

def overview(state):
    b=book(state)
    if not b:return None
    c=b['chapters'].get(b.get('active'))
    if not c:return dict(title='',goal='正在规划冒险目标与章节路线。',milestones=[])
    if state.get('adventure'):
        missions=[m for m in state['adventure']['missions'].values() if m.get('discovered') and m['status']=='active']
        return dict(title=c['title'],goal=missions[0]['brief'] if missions else '留意身边的人与新的消息。',complete=c['complete'],milestones=[])
    shown=[]
    for m in c['milestones']:
        done=state['quests'][c['id']+':'+m['id']]['status']=='complete';shown.append(dict(name=m['name'],complete=done))
        if not done:break
    return dict(title=c['title'],goal=next((m['description'] for m in c['milestones'] if state['quests'][c['id']+':'+m['id']]['status']=='active'),'阶段目标已经完成。'),complete=c['complete'],milestones=shown)
