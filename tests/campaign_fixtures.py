from content_fixtures import authored_patch

def chapter_patch(combat=False):
    spec=dict(identity='调查员' if combat else '邮差',inventory_label='携行装备',journal_label='调查记录',visual_theme='modern infection hospital' if combat else 'cozy forest post office',
        systems=dict(combat=combat,inventory=combat,equipment=False,progression=False),resources=[dict(id='hp',label='伤势',initial=90,max=90),dict(id='ammo',label='弹药',initial=6,max=30)] if combat else [])
    return dict(kind='campaign',campaign=dict(title='消失的信',premise='同一封失踪的信连接四个地点',goal='找到邮局失踪信件并查清停电原因',game_spec=spec,
      flags=dict(clue=False,power=False,secret=False,letter=False),flag_sources=dict(clue='post',power='station',secret='archive',letter='vault'),
      regions=[dict(id=k,name=n,description=n+'的相关故事',purpose=p) for k,n,p in [('post','邮局','调查后设置 clue=true'),('station','电站','修复设置 power=true'),('archive','档案室','结合邮局线索查到 secret=true'),('vault','储藏室','读取 power 后取信设置 letter=true')]],
      links=[dict(id='ps',a='post',b='station'),dict(id='pa',a='post',b='archive'),dict(id='sa',a='station',b='archive'),
       dict(id='sv',a='station',b='vault',requires=[dict(flag='power',eq=True)],blocked_reason='恢复电源才能进入'),
       dict(id='av',a='archive',b='vault',hidden=True,discover=[dict(flag='secret',eq=True)])],
      milestones=[dict(id='restore',name='恢复电源',description='电站将影响储藏室',when=[dict(flag='power',eq=True)]),dict(id='recover',name='取回信件',description='完成跨地区目标',when=[dict(flag='letter',eq=True)])],
      complete_when=[dict(flag='letter',eq=True)],continuation=dict(**{'from':'vault'},hook='寻找信件真正的收件人')))

def region_patch(world,rid):
    ctx=world.context(rid);raw=authored_patch();r=raw['region']
    r.update(name=world.state['topology'][rid]['name'],description=ctx['region_purpose'],landmarks=[],items=[],quests=[],starting_loadout=dict(inventory=[]))
    if rid!='r0':r.pop('starting_loadout')
    r.pop('destinations',None)
    r['entities']=[dict(id='console',kind='object',name='调查台',at=[5,5],sprite='object',solid=False)]
    positions=[[2,2],[24,2],[24,16],[2,16],[14,2],[14,16]]
    anchors={route['anchor']:positions[i] for i,route in enumerate(ctx['planned_routes'])}
    if ctx['reserve_chapter_gate']:anchors['chapter_gate']=[26,10]
    r['scene']=dict(size=[28,20],spawn=[3,5],base='ground',paint=[],anchors=anchors)
    actions=[]
    for flag in ctx['required_flag_writes']:
        a=dict(id='set_'+flag,label='完成'+flag,target='console',effects=[dict(op='chapter',key=flag,value=True)])
        if flag=='letter':a['when']={'get':'chapter.power'}
        if flag=='secret':a['when']={'get':'chapter.clue'}
        actions.append(a)
    r['program']=dict(summary=ctx['region_purpose'],vars={},actions=actions,hooks=[],objectives=[])
    return raw
