"""Test-authored programs. Never imported by live generation or used as fallback."""
import copy
from visual_fixtures import visual_fixture


def add_scene(raw, ctx):
    r = raw['region']; anchors = dict(forward_0=[6, 5], forward_1=[45, 5], back=[26, 33])
    for n, entity in enumerate(r['entities']): anchors[entity['id']] = [8+n*5, 18]
    for n, landmark in enumerate(r.get('landmarks', [])): landmark.update(id='scenery_'+str(n), at=[8+n*12, 10])
    r['scene'] = dict(size=[52,36], spawn=[26,31], base='ground', paint=[], anchors=anchors, summary='test open courtyard')
    r['program'] = dict(summary='test input contract', vars={}, actions=[], hooks=[], objectives=[])
    return raw


def expr(op, *args): return dict(op=op, args=list(args))
def get(path): return {'get': path}


def authored_patch():
    art = visual_fixture()
    art['sprites']['gate'] = copy.deepcopy(art['sprites']['building'])
    art['sprites']['opened'] = copy.deepcopy(art['sprites']['building'])
    art['sprites']['opened']['layers'][0] = ['rect',0,0,2,12,'accent']
    art['sprites']['floor'] = dict(size=[16,16],layers=[['rect',0,0,16,16,'ground'],['rect',3,2,2,12,'accent'],['rect',10,2,2,12,'path']])
    art['sprites']['npc']['frames'] = [art['sprites']['npc']['layers'], [['rect',1,0,8,12,'accent'],['rect',2,4,6,4,'path'],['rect',3,2,4,2,'shadow']]]
    art['sprites']['npc']['frame_ms'] = 220
    art['scenery'] = []
    return dict(kind='region',world_title='逻辑来自数据的试验世界',region=dict(
        name='回声藏书馆', description='操作控制器，影子重复过去的动作。', biome='clockwork_archive',layout='split_hall',weather='clear',rule='normal',
        scene=dict(size=[28,20],spawn=[4,10],base='ground',summary='偏心双厅：控制器、回声与实体门',
            paint=[{'rect':[0,0,28,20],'tile':'ground','surface':'floor'}, {'line':[[12,0],[12,19]],'tile':'wall','width':1}, {'rect':[12,10,1,1],'tile':'path'}],
            anchors=dict(lever=[5,10],shadow=[3,10],door=[12,10],foe=[20,8],forward_0=[24,16],back=[2,16])),
        landmarks=[],entities=[
            dict(id='lever',kind='object',name='余光控制器',sprite='object',description='连续校准两次会打开门。',solid=False,state={'charge':0}),
            dict(id='shadow',kind='object',name='两步之前的影子',sprite='npc',solid=False),
            dict(id='door',kind='object',name='实体门',sprite='gate',solid=True),
            dict(id='foe',kind='enemy',name='等待被理解的机关兽',sprite='enemy',monster='sentinel',tier=1,move='strike',stats={'hp':45,'attack':4})],
        items=[],quests=[],destinations=[{'id':'terrace','name':'朝向昨日的露台','description':'一段未来的旅程。'}],visuals=art,
        program=dict(summary='历史位置驱动影子；状态条件开门；不同于单目标任务的合取条件',vars={'presses':0},
            actions=[
                dict(id='tune',label='校准余光',target='lever',scope='explore',when=expr('lt',get('vars.presses'),2),effects=[{'op':'change','path':'vars.presses','value':1}]),
                dict(id='resonate',label='逆向共振',target='player',scope='combat',when=expr('ge',get('player.mp'),3),effects=[{'op':'stat','target':'player','name':'mp','delta':-3},{'op':'stat','target':'enemy','name':'hp','delta':-15}])],
            hooks=[
                dict(id='memory_motion',on='move',effects=[{'op':'move','target':'shadow','to':[{'history':2,'field':'x'},{'history':2,'field':'y'}]}]),
                dict(id='open',on='invoke',when=expr('ge',get('vars.presses'),2),once=True,effects=[{'op':'solid','target':'door','value':False},{'op':'sprite','target':'door','value':'opened'}]),
                dict(id='foe_logic',on='enemy_turn',effects=[{'op':'stat','target':'player','name':'hp','delta':expr('sub',0,get('battle.turn'))}])],
            objectives=[dict(id='align',name='校准且跨过中线',when=expr('and',expr('ge',get('vars.presses'),2),expr('gt',get('player.x'),12)),reward=[{'op':'stat','target':'player','name':'gold','delta':17}])]
        )))
