import copy
import unittest
from unittest.mock import patch
from engine.world import World
from engine.storage import Store
from engine.director import Director,ChatProvider
from engine import adventure,campaign,encounters
from engine.schema import InvalidPatch
from engine.read_views import journal,atlas
from adventure_fixtures import adventure_plan,authored_adventure_region

class PacingTests(unittest.TestCase):
    def setUp(self):
        self.w=World(Store(':memory:'));self.w.start('人物、风险和探索',authored=True,planned=True)
        self.w.apply_patch(adventure_plan(),self.w.context(kind='campaign'))
        self.generate('r0')
    def tearDown(self):self.w.store.close()
    def generate(self,rid):self.w.apply_patch(authored_adventure_region(self.w,rid),self.w.context(rid))
    def director(self):
        d=Director(self.w);d.configure(dict(offline=False,api_key='test',base_url='https://example.test',model='test',max_calls=4));d.cfg['cooldown']=0;return d
    def test_no_change_review_does_not_cancel_inflight_region(self):
        ctx=self.w.context('c1_station');revision=self.w.state['adventure']['revision']
        self.w.apply_patch(dict(kind='direction',direction=dict(reason='保持当前计划')),self.w.context(kind='direction'))
        self.assertEqual(self.w.state['adventure']['revision'],revision)
        self.assertTrue(self.w.apply_patch(authored_adventure_region(self.w,'c1_station'),ctx))
    def test_actual_worker_finishes_after_a_noop_review_during_request(self):
        d=self.director();seen=[]
        def reply(provider,ctx,kind,repair=''):
            seen.append(kind)
            self.w.apply_patch(dict(kind='direction',direction=dict(reason='不必改动')),self.w.context(kind='direction'))
            return authored_adventure_region(self.w,ctx['target']),{}
        with patch.object(ChatProvider,'generate',reply):d.step()
        self.assertEqual((d.calls,d.accepted,d.stale),(1,1,0));self.assertEqual(seen,['region'])
    def test_review_acknowledges_batch_while_later_events_remain_pending(self):
        adv=adventure.state(self.w);adv['event_seq']=8;ctx=self.w.context(kind='direction')
        adventure.record(self.w,dict(type='choice',text='新的选择'))
        self.assertTrue(self.w.apply_patch(dict(kind='direction',direction=dict(reason='前一批已看完')),ctx))
        self.assertEqual(adv['reviewed_seq'],8);self.assertTrue(adventure.review_due(self.w))
    def test_unrelated_cast_addition_keeps_region_work(self):
        ctx=self.w.context('c1_station')
        self.w.apply_patch(dict(kind='direction',direction=dict(reason='以后出现的人',additions=dict(cast=[dict(id='other',name='新人物',role='向导',motive='等候')]))),self.w.context(kind='direction'))
        self.assertTrue(self.w.context_is_current(ctx))
    def test_death_of_relevant_cast_invalidates_old_author_context(self):
        adv=adventure.state(self.w)
        job=copy.deepcopy(next(iter(adv['jobs'].values())));job.update(id='later',region='c1_station',status='queued');adv['jobs']['later']=job
        ctx=self.w.context('c1_station');adv['cast']['mira']['state']['alive']=False
        self.assertFalse(self.w.context_is_current(ctx))
    def test_repeated_inspection_does_not_request_global_review(self):
        for _ in range(20):adventure.record(self.w,dict(type='interaction',text='查看门',region='r0'))
        self.assertFalse(adventure.review_due(self.w));self.assertEqual(adventure.state(self.w)['event_seq'],1)
    def test_waiting_exit_and_nearby_buffer_precede_global_review(self):
        d=self.director();adv=adventure.state(self.w);adv.update(event_seq=3,important_seq=3)
        self.w.state['ui']=dict(kind='pending_exit',target='c1_archive')
        self.assertEqual(d._next_job()[0]['target'],'c1_archive')
        self.w.state['ui']={};ctx=d._next_job()[0];self.assertEqual(ctx['kind'],'region')
        d.in_flight[(self.w.state['epoch'],'region',ctx['target'])]='generating'
        self.assertEqual(d._next_job()[0]['kind'],'direction')
    def test_future_mission_is_absent_in_all_player_views(self):
        adv=adventure.state(self.w)
        hidden=dict(id='secret',name='SPOILER_FINALE',brief='SPOILER_SOLUTION',kind='main',region='c1_vault',chapter_id='c1',status='active',depends=['c1_meet'],when=[dict(flag='letter',eq=True)],fail_when=[])
        adv['missions']['secret']=hidden
        self.w.state['quests']['secret']=dict(id='secret',name=hidden['name'],description=hidden['brief'],goal='adventure',status='active',region='c1_vault')
        self.assertNotIn('SPOILER',str(self.w.snapshot()['quests'])+str(journal(self.w,'active'))+str(atlas(self.w))+str(campaign.overview(self.w.state)))
        self.w.state['campaign']['chapters']['c1']['flags']['clue']=True;self.w.persist()
        self.assertTrue(any(q['id']=='secret' for q in self.w.snapshot()['quests']))
    def test_director_adds_playable_middle_location_and_actual_connection(self):
        raw=dict(kind='direction',direction=dict(reason='玩家发现支路',new_regions=[dict(id='c1_foundry',name='铸造间',description='新发现的铸造间',purpose='商谈换取材料')],links=[dict(id='new_path',a='r0',b='c1_foundry')]))
        self.w.apply_patch(raw,self.w.context(kind='direction'))
        self.assertIn('c1_foundry',campaign.neighbors(self.w.state,'r0'))
        self.generate('c1_foundry');self.assertTrue(self.w.state['topology']['c1_foundry']['ready'])
        self.assertFalse(self.w.state['topology']['c1_foundry']['visited'])
    def test_disconnected_new_location_rolls_back(self):
        before=copy.deepcopy(self.w.state)
        with self.assertRaises(InvalidPatch):self.w.apply_patch(dict(kind='direction',direction=dict(reason='wrong',new_regions=[dict(id='lonely',name='孤岛',description='孤岛',purpose='孤岛')])),self.w.context(kind='direction'))
        self.assertEqual(self.w.state,before)
    def test_rolling_opening_can_leave_middle_undecided(self):
        p=adventure_plan();c=p['campaign'];c.pop('adventure');c['planning']='rolling';c['ending_brief']='最后决定是否把信交还失主'
        c['regions']=c['regions'][:2];c['links']=c['links'][:1];c['flags']={'clue':False,'power':False};c['flag_sources']={'clue':'post','power':'station'}
        c['milestones']=c['milestones'][:1];c['complete_when']=[dict(flag='power',eq=True)];c['continuation']['from']='station'
        parsed=campaign.validate(p);self.assertEqual(len(parsed['regions']),2)
    def test_misplaced_failure_mode_moves_only_when_unambiguous(self):
        p=adventure_plan();p['campaign']['failure_mode']='none';changes=[]
        parsed=campaign.validate(p,corrections=changes)
        self.assertEqual(parsed['game_spec']['failure_mode'],'none');self.assertEqual(len(changes),1)
        p['campaign']['game_spec']['failure_mode']='end'
        with self.assertRaises(InvalidPatch):campaign.validate(p)
    def test_inline_sound_options_preserve_different_volumes(self):
        from hybrid_fixtures import hybrid_patch
        from engine.schema import parse_patch
        raw=hybrid_patch();audio=raw['region']['audio']
        audio['bindings'].update(move={'asset':'ui_v1_click_001','volume':0.2},interact={'asset':'ui_v1_click_001','volume':0.8})
        parsed=parse_patch(raw,'region')['region']['audio']
        a,b=(parsed['bindings'][k] for k in ('move','interact'))
        self.assertNotEqual(a,b);self.assertEqual(parsed['cues'][a]['volume'],0.2);self.assertEqual(parsed['cues'][b]['volume'],0.8)
    def enemy(self,mode='hunt',at=(12,5),footprint=None):
        s=self.w.state;s['game_spec']['systems']['combat']=True;s['game_spec']['resources'].append(dict(id='hp',label='体力',initial=24,max=24,display='bar'));s['player'].update(hp=24,max_hp=24,x=9,y=5)
        r=self.w.region();e=dict(id='r0:guard',local_id='guard',kind='enemy',name='警卫',monster='sentinel',tier=1,move='strike',x=at[0],y=at[1],spent=False,solid=True,behavior=encounters.validate(dict(mode=mode,radius=6,pace=1,patrol=[[12,5],[18,5]])))
        if footprint:e['footprint']=footprint
        r['entities'].append(e);self.w.persist(r);return e
    def test_enemy_pursues_and_starts_real_battle_without_click(self):
        e=self.enemy();self.w.action(dict(op='wait'));self.assertEqual(e['x'],11);self.assertTrue(e['alerted'])
        self.w.action(dict(op='wait'));self.assertEqual(self.w.state['battle']['id'],e['id'])
    def test_wall_blocks_detection_and_pursuit(self):
        e=self.enemy();self.w.region()['tiles'][5][10]=3
        self.w.action(dict(op='wait'));self.assertFalse(e['alerted']);self.assertEqual(e['x'],12);self.assertIsNone(self.w.state['battle'])
    def test_large_enemy_respects_footprint_collision(self):
        e=self.enemy(at=(12,6),footprint=[2,2]);r=self.w.region()
        r['tiles'][6][11]=3
        self.w.action(dict(op='wait'))
        for x,y in encounters.cells_for(e):self.assertNotEqual(r['tiles'][y][x],3)

if __name__=='__main__':unittest.main()
