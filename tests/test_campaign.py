import copy
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from engine.world import World
from engine.storage import Store
from engine import campaign,game_spec
from engine.runtime import Runtime
from engine.schema import InvalidPatch
from engine.read_views import atlas
from engine.library import candidates
from engine.director import Director,ChatProvider
from campaign_fixtures import chapter_patch,region_patch

class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.w=World(Store(':memory:'));self.w.start('调查失踪信',authored=True,planned=True)
    def tearDown(self):self.w.store.close()
    def planned(self,combat=False):self.w.apply_patch(chapter_patch(combat),self.w.context(kind='campaign'))
    def generated(self):
        self.planned()
        for rid in list(self.w.state['topology']):self.w.apply_patch(region_patch(self.w,rid),self.w.context(rid))
    def flag(self,rid,key):
        self.w.state['current']=rid;self.w.state['player'].update(x=4,y=5);self.w.state['ui']={}
        self.w.action(dict(op='invoke',id='set_'+key))
    def test_graph_is_connected_branched_and_rejects_linear_design(self):
        p=chapter_patch();self.planned();s=self.w.state
        self.assertEqual(len(s['topology']),4);self.assertEqual(len(campaign.neighbors(s,'c1_station')),3)
        p['campaign']['links']=p['campaign']['links'][:2]
        with self.assertRaises(InvalidPatch):campaign.validate(p)
    def test_shared_clues_unlock_routes_and_hidden_links_without_leaking_prefetch(self):
        self.generated();w=self.w
        self.assertEqual(len(atlas(w)['nodes']),3)
        gate=next(e for e in w.region('c1_station')['entities'] if e.get('target')=='c1_vault')
        self.assertTrue(gate['locked'])
        w.state['current']='c1_station'
        with self.assertRaises(ValueError):w.interact(gate)
        self.flag('r0','clue');self.flag('c1_station','power')
        self.assertFalse(next(e for e in w.region('c1_station')['entities'] if e.get('target')=='c1_vault')['locked'])
        self.assertEqual(len(campaign.neighbors(w.state,'c1_archive',True)),2)
        self.flag('c1_archive','secret')
        self.assertEqual(len(campaign.neighbors(w.state,'c1_archive',True)),3)
        self.flag('c1_vault','letter')
        self.assertTrue(w.state['campaign']['pending']);self.assertEqual(w.state['quests']['c1:recover']['status'],'complete')
    def test_disabled_systems_have_no_hidden_costs_and_custom_resources_work(self):
        self.planned(True);self.w.apply_patch(region_patch(self.w,'r0'),self.w.context())
        s=self.w.state;self.assertFalse(game_spec.active(s,'mp'));self.assertFalse(game_spec.active(s,'gold'))
        vm=Runtime(self.w,self.w.region());vm.run([dict(op='resource',id='ammo',delta=-2)])
        self.assertEqual(vm.expr({'get':'resources.ammo'}),4)
        with self.assertRaises(InvalidPatch):vm.run([dict(op='stat',target='player',name='mp',delta=2)])
        snap=self.w.snapshot();self.assertEqual([r['id'] for r in snap['game_spec']['resources']],['hp','ammo'])
    def test_no_health_no_combat_and_full_plan_apply_rollback(self):
        self.planned();raw=region_patch(self.w,'r0')
        raw['region']['program']['actions'][0]['effects'].append(dict(op='stat',target='player',name='hp',delta=-1))
        with self.assertRaises(InvalidPatch):self.w.apply_patch(raw,self.w.context())
        self.assertIsNone(self.w.region())
    def test_modern_setting_does_not_receive_medieval_art_even_underground(self):
        c=candidates(dict(setting='生化危机，感染医院与地下实验室',destination={'name':'地下档案馆'}))
        self.assertEqual(c['profile'],'modern');self.assertEqual(c['images'],[])
    def test_planner_runs_before_region_and_only_once(self):
        d=Director(self.w);d.configure(dict(offline=False,api_key='test',base_url='https://example.test',model='test',max_calls=5));d.cfg['cooldown']=0
        seen=[]
        def generate(_,ctx,kind,repair=''):
            seen.append(kind)
            return (chapter_patch() if kind=='campaign' else region_patch(self.w,ctx['target'])),{}
        with patch.object(ChatProvider,'generate',generate):d.step();d.step()
        self.assertEqual(seen,['campaign','region']);self.assertIsNotNone(self.w.region())
    def test_chapter_continuation_preserves_previous_world_and_returns(self):
        self.generated()
        for rid,key in [('r0','clue'),('c1_station','power'),('c1_archive','secret'),('c1_vault','letter')]:self.flag(rid,key)
        p=chapter_patch();p['campaign'].pop('game_spec');self.w.apply_patch(p,self.w.context(kind='campaign'))
        self.assertEqual(len(self.w.state['topology']),8)
        self.assertTrue(any(e.get('target')=='c2_post' for e in self.w.region('c1_vault')['entities']))
        self.w.apply_patch(region_patch(self.w,'c2_post'),self.w.context('c2_post'))
        self.assertTrue(any(e.get('target')=='c1_vault' for e in self.w.region('c2_post')['entities']))
        self.assertTrue(campaign.chapter(self.w.state,'c1_station')['flags']['power'])
    def test_real_exit_actions_traverse_a_loop_without_recreating_regions(self):
        self.generated();w=self.w;sequence=['c1_station','c1_archive','r0']
        for target in sequence:
            region=w.region();gate=next(e for e in region['entities'] if e.get('target')==target)
            w.state['ui']={};w.state['player'].update(x=gate['x'],y=gate['y'])
            w.action(dict(op='interact',id=gate['id']))
            self.assertEqual(w.state['current'],target)
        self.assertEqual(w.region()['visits'],2)
        self.assertEqual(len(w.state['topology']),4)
    def test_chapter_flags_resources_and_graph_survive_reload(self):
        self.generated();self.flag('r0','clue');self.flag('c1_archive','secret')
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'world.sqlite3');store.commit(self.w.state,list(self.w.cache.values()));store.close()
            loaded=World(Store(Path(temp)/'world.sqlite3'))
            try:
                self.assertTrue(campaign.chapter(loaded.state,'r0')['flags']['secret'])
                self.assertEqual(len(campaign.neighbors(loaded.state,'c1_archive',True)),3)
                self.assertEqual(loaded.snapshot()['game_spec']['resources'],[])
            finally:loaded.store.close()
    def test_parallel_hidden_route_uses_its_own_return_anchor(self):
        p=chapter_patch();p['campaign']['links'].append(dict(id='hidden_alternate_entrance_long_name',a='post',b='station',hidden=True,discover=[dict(flag='clue',eq=True)]))
        self.w.apply_patch(p,self.w.context(kind='campaign'))
        for rid in list(self.w.state['topology']):self.w.apply_patch(region_patch(self.w,rid),self.w.context(rid))
        self.flag('r0','clue')
        gate=next(e for e in self.w.region()['entities'] if 'long_name' in e.get('link_id',''))
        self.w.state['ui']={};self.w.state['player'].update(x=gate['x'],y=gate['y'])
        self.w.action(dict(op='interact',id=gate['id']))
        back=next(e for e in self.w.region()['entities'] if e.get('link_id')==gate['link_id'])
        self.assertEqual([self.w.state['player']['x'],self.w.state['player']['y']],[back['x'],back['y']])
    def test_explicit_run_end_applies_to_damage_outside_combat(self):
        p=chapter_patch(True);p['campaign']['game_spec']['failure_mode']='end'
        self.w.apply_patch(p,self.w.context(kind='campaign'));r=region_patch(self.w,'r0')
        r['region']['program']['actions'][0]['effects'].append(dict(op='stat',target='player',name='hp',delta=-100))
        self.w.apply_patch(r,self.w.context());self.w.state['player'].update(x=4,y=5)
        self.w.action(dict(op='invoke',id='set_clue'))
        self.assertTrue(self.w.state['game_over'])
        with self.assertRaises(ValueError):self.w.action(dict(op='move',dx=1,dy=0))
    def test_low_notes_long_held_notes_and_synth_ambience_remain_bounded(self):
        from engine.audio import validate_audio
        a=validate_audio(dict(music=dict(explore=dict(score=dict(bpm=72,voices=[dict(wave='sine',notes=[[34,6],[33,6],[36,6]])]))),ambience=dict(synth=dict(wave='noise',frequency=130,duration=1))))
        self.assertEqual(a['music']['explore']['score']['voices'][0]['notes'][0],[34,6])
        with self.assertRaises(InvalidPatch):validate_audio(dict(music=dict(explore=dict(score=dict(bpm=60,voices=[dict(wave='sine',notes=[[34,16],[36,16]])])))))
