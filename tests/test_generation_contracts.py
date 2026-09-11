"""Runtime contracts for content invented after the world has already started."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_runtime import make_world, walk_to, at_entity
from engine.demo import make_patch
from engine.director import ChatProvider, Director, ProviderError
from engine.schema import InvalidPatch
from engine.server import GameServer
from engine.storage import Store
from engine.world import World


def expansion():
    return {'kind':'reaction','reaction':{
        'text':'旅人的选择带来新的线索和一条可调查的道路。',
        'items':[{'id':'clue','name':'星图残片','kind':'key','effect':'attack','power':1}],
        'spawns':[{'id':'case','kind':'chest','name':'信使留下的匣子','zone':'south','item_id':'clue'}],
        'quests':[{'id':'find_clue','name':'检查新的线索','goal':'collect','target':'clue'}],
        'locations':[{'id':'observatory','name':'潮下观测站','description':'循残片上的星图探索一座海底观测站。'}]}}


class GenerationContracts(unittest.TestCase):
    def setUp(self): self.w,self.d=make_world()
    def tearDown(self): self.w.store.close()

    def test_new_concept_materializes_and_can_be_collected(self):
        p=self.w.state['player']; before=copy.deepcopy(p['inventory'])
        self.w.apply_patch(expansion(),self.w.context(kind='reaction'))
        self.assertEqual(p['inventory'],before)  # Creation is not an unearned reward.
        e=next(e for e in self.w.region()['entities'] if e['name']=='信使留下的匣子')
        q=next(q for q in self.w.state['quests'].values() if q['name']=='检查新的线索')
        self.assertEqual(q['target'],e['item_id'])
        walk_to(self.w,e)
        self.assertEqual(self.w.state['quests'][q['id']]['status'],'complete')
        self.assertEqual(p['inventory'][e['item_id']],1)

    def test_new_destination_outline_reaches_generator_and_return_is_stable(self):
        old_tiles=copy.deepcopy(self.w.region()['tiles'])
        self.w.apply_patch(expansion(),self.w.context(kind='reaction'))
        target=self.w.state['topology']['r0']['children'][-1]
        ctx=self.w.context(target)
        self.assertEqual(ctx['destination']['name'],'潮下观测站')
        plan=make_patch(ctx,'region'); plan['region']['name']=ctx['destination']['name']
        self.w.apply_patch(plan,ctx)
        gate=next(e for e in self.w.region()['entities'] if e.get('target')==target)
        walk_to(self.w,gate)
        self.assertEqual(self.w.state['current'],target)
        self.assertEqual(self.w.region()['name'],'潮下观测站')
        back=next(e for e in self.w.region()['entities'] if e.get('target')=='r0')
        walk_to(self.w,back)
        self.assertEqual(self.w.region()['tiles'],old_tiles)
        self.assertTrue(any(e['name']=='信使留下的匣子' for e in self.w.region()['entities']))

    def test_failed_expansion_is_atomic_in_memory_and_database(self):
        original=self.w.snapshot(); topology=copy.deepcopy(self.w.state['topology'])
        bad=expansion(); bad['reaction']['quests'][0]['target']='nonexistent'
        with self.assertRaises(InvalidPatch):self.w.apply_patch(bad,self.w.context(kind='reaction'))
        self.assertEqual(self.w.snapshot(),original)
        self.assertEqual(self.w.state['topology'],topology)
        self.assertEqual(self.w.store.load_state(),self.w.state)

    def test_generated_connection_count_is_not_fixed_at_two(self):
        ctx=self.w.context('r0a'); plan=make_patch(ctx,'region')
        self.w.state['topology']['r0a']['ready']=False
        plan['region']['destinations']=[{'id':'one_route','name':'唯一航路','description':'岛屿间唯一的航线。'}]
        self.w.apply_patch(plan,ctx)
        children=self.w.state['topology']['r0a']['children']
        self.assertEqual(len(children),1)
        self.assertEqual(self.w.state['topology'][children[0]]['name'],'唯一航路')

    def test_retry_restores_failed_reaction(self):
        event,deleted=self.w.story('choice','追查未知的信号');self.w.persist(event=event,delete=deleted)
        self.d.configure({'offline':False,'api_key':'test-only'});self.d.cfg['cooldown']=0
        with patch.object(ChatProvider,'generate',side_effect=ProviderError('network unavailable')) as model:
            self.d.step();self.d.step()
            self.assertEqual(model.call_count,1)
        self.d.retry()
        seen=[]
        def answer(ctx,kind,repair=''):
            seen.append(kind)
            return json.dumps(expansion()),{'input_tokens':10,'output_tokens':20}
        with patch.object(ChatProvider,'generate',side_effect=answer):self.d.step()
        self.assertEqual(seen,['reaction'])
        self.assertFalse(self.w.state['director_reaction_pending'])

    def test_live_mode_never_falls_back_to_demo(self):
        self.d.configure({'offline':False,'api_key':'test-only'});self.d.cfg['cooldown']=0
        event,deleted=self.w.story('choice','未知事件');self.w.persist(event=event,delete=deleted)
        with patch('engine.director.make_patch',side_effect=AssertionError('demo used in live mode')) as demo:
            with patch.object(ChatProvider,'generate',side_effect=ProviderError('network unavailable')):
                self.d.step()
        demo.assert_not_called()
        self.assertEqual(self.w.region()['revision'],0)

    def test_undefined_item_enters_single_repair_without_partial_state(self):
        event,deleted=self.w.story('choice','寻找新线索');self.w.persist(event=event,delete=deleted)
        self.d.configure({'offline':False,'api_key':'test-only'});self.d.cfg['cooldown']=0
        bad=expansion();bad['reaction']['items']=[]
        repairs=[]
        def answer(ctx,kind,repair=''):
            repairs.append(repair)
            return json.dumps(expansion() if repair else bad),{'input_tokens':1,'output_tokens':1}
        with patch.object(ChatProvider,'generate',side_effect=answer):self.d.step()
        self.assertEqual(self.d.calls,2)
        self.assertEqual(self.d.accepted,8)  # Seven prepared regions + one repaired reaction.
        self.assertIn('undefined',repairs[1])
        self.assertEqual(len([q for q in self.w.state['quests'].values() if q['name']=='检查新的线索']),1)

    def test_environment_key_is_not_reused_for_other_provider(self):
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'deepseek-test-only'}):
            with self.assertRaises(ProviderError):self.d.configure({'offline':False,'base_url':'https://example.invalid'})
            self.d.configure({'offline':False,'base_url':'http://localhost:9012','deepseek_options':False})
            self.assertEqual(self.d.cfg['api_key'],'')

    def test_thinking_default_and_invalid_configuration(self):
        self.assertEqual(self.d.cfg['reasoning_effort'],'low')
        self.d.configure({'offline':True,'reasoning_effort':'high'})
        self.assertEqual(self.d.status()['reasoning_effort'],'high')
        previous=copy.deepcopy(self.d.cfg)
        with self.assertRaises(ProviderError):self.d.configure({'offline':True,'reasoning_effort':'unknown'})
        self.assertEqual(self.d.cfg,previous)

    def test_new_world_during_response_drops_it_without_another_repair(self):
        event,deleted=self.w.story('choice','旧世界的行动');self.w.persist(event=event,delete=deleted)
        self.d.configure({'offline':False,'api_key':'test-only'});self.d.cfg['cooldown']=0
        def rebuild(ctx,kind,repair=''):
            self.w.start('雪原上的全新世界。')
            return '{}',{'input_tokens':1,'output_tokens':1}
        with patch.object(ChatProvider,'generate',side_effect=rebuild) as model:self.d.step()
        self.assertEqual(model.call_count,1)
        self.assertEqual(self.w.state['setting'],'雪原上的全新世界。')
        self.assertIsNone(self.w.region())
        self.assertEqual(self.w.state['facts'],{})

    def test_expansion_survives_restart(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'world.sqlite3';w,d=make_world(path)
            try:
                w.apply_patch(expansion(),w.context(kind='reaction'));before=w.snapshot()
            finally:w.store.close()
            restored=World(Store(path))
            try:self.assertEqual(before,restored.snapshot())
            finally:restored.store.close()


class ConfigurationPersistence(unittest.TestCase):
    def test_settings_roundtrip_without_credentials_or_auto_requests(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'world.sqlite3'
            server=GameServer(('127.0.0.1',0),path,'session')
            try:
                server.director.configure({'offline':False,'base_url':'https://example.invalid','model':'custom-model','api_key':'private-test-key','deepseek_options':False,'reasoning_effort':'medium','max_calls':7})
                server.remember_configuration()
                one=server.snapshot();two=server.snapshot()
                self.assertLess(one['snapshot_sequence'],two['snapshot_sequence'])
                self.assertNotIn('private-test-key',json.dumps(two))
                self.assertNotIn('private-test-key',(Path(td)/'settings.json').read_text())
            finally:server.server_close();server.world.store.close()
            restored=GameServer(('127.0.0.1',0),path,'session2')
            try:
                s=restored.snapshot()
                self.assertEqual(s['configuration']['model'],'custom-model')
                self.assertEqual(s['configuration']['max_calls'],7)
                self.assertEqual(s['configuration']['reasoning_effort'],'medium')
                self.assertEqual(s['director']['mode'],'not_configured')
                self.assertEqual(s['director']['calls'],0)
            finally:restored.server_close();restored.world.store.close()

    def test_old_settings_gain_low_default(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td)/'settings.json').write_text(json.dumps({'offline':False,'deepseek_options':True}),encoding='utf-8')
            server=GameServer(('127.0.0.1',0),Path(td)/'world.sqlite3','test-session')
            try:self.assertEqual(server.snapshot()['configuration']['reasoning_effort'],'low')
            finally:server.server_close();server.world.store.close()
