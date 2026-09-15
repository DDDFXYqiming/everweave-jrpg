from campaign_fixtures import chapter_patch,region_patch

def adventure_plan():
    p=chapter_patch();c=p['campaign']
    c['game_spec']['resources']=[dict(id='focus',label='专注',initial=3,max=5,display='number')]
    c['adventure']=dict(
        cast=[dict(id='mira',name='米拉',role='同行调查员',motive='找到失踪的姐姐',state=dict(alive=True,trust=0))],
        skills=[dict(id='listen',name='集中聆听',description='花费一点专注辨别线索',scope='explore')],
        missions=[dict(id='meet',name='建立信任',kind='main',region='post',brief='与米拉决定如何合作',when=[dict(flag='clue',eq=True)]),
                  dict(id='recover',name='共同取回信件',kind='side',region='vault',brief='用前面的线索取回信件',depends=['meet'],when=[dict(flag='letter',eq=True)])],
        endings=[dict(id='together',name='共同的旅途',description='米拉读完了信，决定与你同行。',requires=['recover'],final=True)],
        economy=dict(focus=2),
        commissions=[dict(id='welcome',kind='scene',region='post',brief='米拉提出合作并教会聆听，选择改变信任和进展',cast=['mira'],skills=['listen'],missions=['meet'])])
    return p

def authored_adventure_region(world,rid):
    raw=region_patch(world,rid);r=raw['region']
    r['scene']['anchors'].update(director_gate_0=[26,4],director_gate_1=[26,7])
    if rid=='r0':
        r['entities'][0].update(actor_id='mira',name='米拉',sprite='npc')
        r['abilities']=[dict(id='listen',label='集中聆听',scope='explore',target='player',when=dict(op='ge',args=[{'get':'resources.focus'},1]),effects=[dict(op='resource',id='focus',delta=-1),dict(op='message',text='远处的电站传来了断续的回声。')])]
        r['scenes']=[dict(id='meeting',title='共同的线索',lines=[dict(speaker='mira',text='我在寻找姐姐。你愿意一起查下去吗？')],choices=[dict(id='help',label='一起调查',effects=[dict(op='actor',id='mira',key='trust',value=5),dict(op='learn',id='listen'),dict(op='chapter',key='clue',value=True)])])]
        r['program']['actions'].append(dict(id='meet_mira',label='听米拉说',target='console',effects=[dict(op='scene',id='meeting')]))
    return raw
