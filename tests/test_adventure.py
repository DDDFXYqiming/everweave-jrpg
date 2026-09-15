import copy
import unittest
from unittest.mock import patch
from engine.world import World
from engine.storage import Store
from engine.runtime import Runtime
from engine.schema import InvalidPatch
from engine import adventure,campaign
from engine.director import Director,ChatProvider
from adventure_fixtures import adventure_plan,authored_adventure_region
from hybrid_fixtures import hybrid_patch

class AdventureTests(unittest.TestCase):
    def setUp(self):
        self.w=World(Store(':memory:'));self.w.start('调查与同行',authored=True,planned=True)
        self.w.apply_patch(adventure_plan(),self.w.context(kind='campaign'))
    def tearDown(self):self.w.store.close()
    def generate(self,rid='r0'):self.w.apply_patch(authored_adventure_region(self.w,rid),self.w.context(rid))
    def talk(self):
        self.w.state['player'].update(x=4,y=5)
        self.w.action(dict(op='invoke',id='meet_mira'))
        self.w.action(dict(op='content_action',id='scene:meeting:help'))
    def test_route_author_receives_gate_conditions_and_producers(self):
        ctx=self.w.context('c1_station');gate=next(r for r in ctx['planned_routes'] if r['target']=='c1_vault')
        self.assertEqual(gate['requires'],[dict(flag='power',eq=True)])
        self.assertEqual(gate['condition_sources']['power'],'c1_station')
        self.assertNotIn('condition_sources',campaign.routes(self.w.state,'c1_station')[0])
    def test_scene_choices_change_relationship_and_grant_portable_ability(self):
        self.generate();self.talk();adv=adventure.state(self.w)
        self.assertEqual(adv['cast']['mira']['state']['trust'],5)
        self.assertIn('listen',self.w.state['player']['abilities'])
        self.assertEqual(adv['missions']['c1_meet']['status'],'complete')
        self.generate('c1_station');self.w.state['current']='c1_station';self.w.state['ui']={}
        self.assertIn('ability:listen',{a['id'] for a in Runtime(self.w,self.w.region()).available()})
        self.w.action(dict(op='invoke',id='ability:listen'))
        self.assertEqual(self.w.state['player']['resources']['focus'],2)
    def test_missing_skill_is_reported_with_independent_rule_errors(self):
        raw=authored_adventure_region(self.w,'r0');raw['region'].pop('abilities')
        raw['region']['program']['actions'][0]['when']={'op':'not_a_real_operator','args':[]}
        with self.assertRaises(InvalidPatch) as caught:self.w.validate_patch(raw,self.w.context('r0'))
        issues=caught.exception.issues
        self.assertTrue(any('operator' in i['message'] for i in issues))
        self.assertTrue(any(i['path']=='region.abilities' and i['value']=='listen' for i in issues))
        self.assertTrue(any('.choices[0].effects[1].id' in i['path'] for i in issues))
    def test_director_cannot_mutate_facts_or_retroactively_complete_missions(self):
        self.generate()
        for data in [dict(reason='bad',player={'gold':999}),dict(reason='bad',additions={'cast':[dict(id='mira',name='Else',role='x',motive='y',state={'alive':True})]})]:
            with self.assertRaises(InvalidPatch):self.w.validate_patch(dict(kind='direction',direction=data),self.w.context(kind='direction'))
        self.talk()
        with self.assertRaises(InvalidPatch):self.w.validate_patch(dict(kind='direction',direction=dict(reason='retroactive',additions={'missions':[dict(id='free',name='free',kind='side',region='r0',brief='free',when=[dict(flag='clue',eq=True)])]})),self.w.context(kind='direction'))
    def test_director_adds_a_real_reserved_connection_atomically(self):
        self.generate();self.generate('c1_vault')
        ctx=self.w.context(kind='direction')
        self.w.apply_patch(dict(kind='direction',direction=dict(reason='打开已探索地点之间的捷径',links=[dict(id='shortcut',a='r0',b='c1_vault')])),ctx)
        self.assertIn('c1_vault',campaign.neighbors(self.w.state,'r0'))
        gate=next(e for e in self.w.region()['entities'] if e.get('target')=='c1_vault')
        self.assertEqual([gate['x'],gate['y']],[26,4])
        before=copy.deepcopy(self.w.state)
        with self.assertRaises(InvalidPatch):self.w.apply_patch(dict(kind='direction',direction=dict(reason='invalid',links=[dict(id='bad',a='r0',b='absent')])),self.w.context(kind='direction'))
        self.assertEqual(self.w.state,before)
    def test_reward_budget_rolls_back_scene_and_cast_changes(self):
        self.generate();self.w.state['player'].update(x=4,y=5)
        r=self.w.region();r['program']['actions'].append(dict(id='excess',label='too much',scope='explore',target='player',when=True,once=False,description='x',effects=[dict(op='actor',id='mira',key='trust',value=50),dict(op='resource',id='focus',delta=3)]))
        before=copy.deepcopy(self.w.state)
        with self.assertRaises(InvalidPatch):self.w.action(dict(op='invoke',id='excess'))
        self.assertEqual(self.w.state,before)
    def test_director_rechecks_reserved_gate_after_runtime_geometry_changes(self):
        self.generate();self.generate('c1_vault')
        self.w.region()['props'].append(dict(id='new_wall',x=25,y=4,footprint=[2,1],solid=True))
        before=copy.deepcopy(self.w.state)
        with self.assertRaises(InvalidPatch):
            self.w.apply_patch(dict(kind='direction',direction=dict(reason='blocked',links=[dict(id='shortcut',a='r0',b='c1_vault')])),self.w.context(kind='direction'))
        self.assertEqual(self.w.state,before)
    def test_director_review_runs_after_committed_events_not_each_step(self):
        self.generate();self.talk();adv=adventure.state(self.w)
        for rid in list(self.w.state['topology']):
            if rid!='r0':self.generate(rid)
        adv['event_seq']=adv['reviewed_seq']+3;adv['important_seq']=adv['event_seq'];self.w.state['ui']={}
        d=Director(self.w);d.configure(dict(offline=False,api_key='test',base_url='https://example.test',model='test',max_calls=4));d.cfg['cooldown']=0
        seen=[]
        def reply(_,ctx,kind,repair=''):
            seen.append(kind);return dict(kind='direction',direction=dict(reason='目前计划仍合理，无需追加内容')),{}
        with patch.object(ChatProvider,'generate',reply):d.step()
        self.assertEqual(seen,['direction']);self.assertFalse(adventure.review_due(self.w))
    def test_final_outcome_is_driven_by_committed_missions(self):
        self.generate();self.talk();c=campaign.chapter(self.w.state,'r0')
        c['flags']['letter']=True;self.w.state['ui']={}
        self.w.action(dict(op='wait'))
        self.assertTrue(self.w.state.get('game_over'));self.assertEqual(self.w.state['ui']['title'],'共同的旅途')
    def test_scene_choice_reply_is_shown_and_dead_cast_stays_dead(self):
        self.generate();self.w.region()['scenes'][0]['choices'][0]['effects'].append(dict(op='message',text='米拉答应与你同行。'))
        self.talk();self.assertIn('米拉答应与你同行。',self.w.state['ui']['lines'])
        adv=adventure.state(self.w);adv['cast']['mira']['state']['alive']=False
        with self.assertRaises(InvalidPatch):Runtime(self.w,self.w.region()).run([dict(op='actor',id='mira',key='alive',value=True)])
    def test_new_side_content_flows_director_to_worker_to_player(self):
        self.generate();before=self.w.state['player']['resources']['focus']
        change=dict(reason='加入与同行有关的支线',new_flags=[dict(id='extra_clue',initial=False,source='r0')],additions=dict(
            missions=[dict(id='extra',name='遗落的线索',kind='side',region='r0',brief='调查后才有结果',when=[dict(flag='extra_clue',eq=True)])],
            commissions=[dict(id='extra_job',kind='quest',region='r0',brief='提供一次有代价的调查',missions=['extra'])]))
        self.w.apply_patch(dict(kind='direction',direction=change),self.w.context(kind='direction'))
        self.assertFalse(campaign.chapter(self.w.state,'r0')['flags']['extra_clue'])
        ctx=self.w.context(kind='reaction');ctx['commission_ids']=[j['id'] for j in ctx['content_contract']['commissions']]
        invalid=dict(kind='reaction',reaction=dict(text='不能直接移除人物',object_updates=[dict(id='r0:console',remove=True)]))
        with self.assertRaises(InvalidPatch):self.w.validate_patch(invalid,ctx)
        work=dict(kind='reaction',reaction=dict(text='留在码头的新线索',program=dict(actions=[dict(id='find_extra',label='调查遗落的箱子',effects=[dict(op='chapter',key='extra_clue',value=True),dict(op='resource',id='focus',delta=1)])])))
        self.w.apply_patch(work,ctx)
        self.assertEqual(self.w.state['player']['resources']['focus'],before)
        self.w.action(dict(op='invoke',id='find_extra'))
        self.assertTrue(campaign.chapter(self.w.state,'r0')['flags']['extra_clue'])
        self.assertEqual(self.w.state['player']['resources']['focus'],before+1)
    def test_one_way_new_route_is_not_a_reverse_exit(self):
        self.generate();self.generate('c1_vault')
        self.w.apply_patch(dict(kind='direction',direction=dict(reason='单向滑道',links=[dict(id='slide',a='r0',b='c1_vault',one_way=True)])),self.w.context(kind='direction'))
        self.assertIn('c1_vault',campaign.neighbors(self.w.state,'r0'))
        self.assertNotIn('r0',campaign.neighbors(self.w.state,'c1_vault'))
        self.assertTrue(next(e for e in self.w.region('c1_vault')['entities'] if e.get('target')=='r0')['spent'])

class EnemyTurnTests(unittest.TestCase):
    def run_case(self,hook):
        w=World(Store(':memory:'));w.start('enemies',authored=True)
        raw=hybrid_patch();r=raw['region'];r['modules']=[r['modules'][0]]
        r['program']['hooks']=[hook]
        # Remove the generic duel hook so the test isolates actual applicability.
        r['modules']=[];r['program']['actions']=[dict(id='guard',label='观察',target='player',scope='combat',effects=[dict(op='message',text='保持距离。')])]
        r['entities'].append(dict(id='other',kind='enemy',name='另一只守卫',at=[20,12],sprite='enemy',monster='sentinel',tier=1,move='strike',stats=dict(hp=40,attack=7)))
        w.apply_patch(raw,w.context());w.state['player'].update(x=19,y=12);w.action(dict(op='interact',id='r0:other'))
        w.action(dict(op='combat',move='rule:guard'));hp=w.state['player']['hp'];w.store.close();return hp
    def test_foreign_and_unmatched_hooks_do_not_cancel_current_enemy(self):
        self.assertEqual(self.run_case(dict(id='foreign',on='enemy_turn',target='foe',effects=[dict(op='stat',target='player',name='hp',delta=-30)])),83)
        self.assertEqual(self.run_case(dict(id='unmatched',on='enemy_turn',target='other',when=False,effects=[dict(op='stat',target='player',name='hp',delta=-30)])),83)
    def test_explicit_charge_turn_counts_as_an_action(self):
        self.assertEqual(self.run_case(dict(id='charge',on='enemy_turn',target='other',effects=[dict(op='message',text='守卫正在蓄力。')])),90)
