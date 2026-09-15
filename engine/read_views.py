"""Player knowledge views, independent of LLM context windows and generation."""
import copy


def map_card(region):
    palette=region.get('visuals',{}).get('palette',{})
    colors=[palette.get(k,fallback) for k,fallback in zip(('ground','path','water','wall','path'),
            ('#506044','#b49b68','#395e67','#26352a','#b49b68'))]
    width,height=20,12
    pixels=[[region['tiles'][min(region['height']-1,y*region['height']//height)]
                              [min(region['width']-1,x*region['width']//width)] for x in range(width)] for y in range(height)]
    return dict(description=region.get('description',''),thumbnail=dict(colors=colors,pixels=pixels))


def atlas(world):
    s=world.state
    if not s:return dict(epoch='',current='',nodes=[],edges=[])
    topology=s['topology'];visited={k for k,n in topology.items() if n['visited']}
    visible=set(visited);pairs=set()
    for rid in visited:
        node=topology[rid]
        from .campaign import neighbors,book
        for target in (neighbors(s,rid,True) if book(s) else node['children']+([node['parent']] if node.get('parent') else [])):
            if target in topology:
                visible.add(target);pairs.add(tuple(sorted((rid,target))))
    cache=getattr(world,'_map_cards',{})
    if cache.get('epoch')!=s['epoch']:cache={'epoch':s['epoch'],'cards':{}};world._map_cards=cache
    quests={}
    for q in s['quests'].values():
        if q.get('status')=='active' and q.get('region') in visited:
            quests.setdefault(q['region'],[]).append({k:q.get(k,'') for k in ('id','name','description','status')})
    nodes=[]
    for rid,n in topology.items():
        if rid not in visible:continue
        card={}
        if rid in visited:
            if rid not in cache['cards']:
                r=world.region(rid)
                cache['cards'][rid]=map_card(r) if r else {}
            card=cache['cards'][rid]
        nodes.append(dict(id=rid,name=n['name'] if rid in visited else (n.get('outline') or {}).get('name',n['name']),
                          visited=rid in visited,ready=bool(n['ready']),parent=n.get('parent') if n.get('parent') in visible else '',
                          description=card.get('description','尚未到访。你已发现通往这里的道路。'),
                          thumbnail=card.get('thumbnail'),tasks=quests.get(rid,[])))
    edges=[dict(a=a,b=b) for a,b in sorted(pairs)]
    if s.get('campaign'):
        from .campaign import links,satisfied
        for e in edges:
            sources=[link for link in links(s,e['a'],True) if e['b'] in (link['a'],link['b'])]
            e['locked']=all(not satisfied(source['requires'],s['campaign']['chapters'][source['chapter_id']]['flags']) for source in sources)
            e['blocked_reason']=' / '.join(source['blocked_reason'] for source in sources) if e['locked'] else ''
            origins=set();allowed=set()
            for source in sources:
                directions={source['a']} if source.get('one_way') else {source['a'],source['b']}
                origins.update(directions)
                if satisfied(source['requires'],s['campaign']['chapters'][source['chapter_id']]['flags']):allowed.update(directions)
            e.update(allowed_from=sorted(allowed),one_way=len(origins)==1,from_id=next(iter(origins)) if len(origins)==1 else '')
    return copy.deepcopy(dict(epoch=s['epoch'],current=s['current'],nodes=nodes,edges=edges))


def journal(world,tab='history',before=None,limit=30):
    if tab not in ('history','active','complete','threads'):raise ValueError('未知手记分类')
    if type(limit) is not int or not 1<=limit<=50:raise ValueError('手记页大小应在 1..50')
    if before is not None and (type(before) is not int or not 0<=before<2**63):raise ValueError('无效手记游标')
    s=world.state or {}
    if tab=='history':result=world.store.journal_page(before,limit)
    else:
        source=list(s.get('threads' if tab=='threads' else 'quests',{}).values())
        ceiling=len(source) if before is None else min(before,len(source))
        rows=[]
        for index in range(ceiling-1,-1,-1):
            entry=source[index]
            if tab!='threads' and (entry.get('status','active')=='active')!=(tab=='active'):continue
            item={key:entry.get(key,'') for key in ('id','name','description','region','status')}
            if tab=='threads':item.update(name=entry.get('title',''),description=entry.get('note',''))
            rows.append((index,item))
            if len(rows)>limit:break
        result=dict(entries=[r[1] for r in rows[:limit]],next_cursor=rows[limit-1][0] if len(rows)>limit else None)
    return dict(result,epoch=s.get('epoch',''),tab=tab)
