"""Executable contract tests, with a real local HTTP mock provider and no paid calls."""
from __future__ import annotations
from collections import deque
import copy
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import random
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from engine import catalog as C
from engine.demo import make_patch
from engine.director import ChatProvider, Director, ProviderError, validate_url
from engine.pcg import build_region, reachable
from engine.schema import InvalidPatch, parse_patch
from engine.server import GameServer
from engine.storage import Store
from engine.world import GameError, World
from visual_fixtures import visual_fixture

SETTING = '一个永远下雨的蒸汽朋克岛国，我是失忆的逃兵。'


def make_world(path=':memory:'):
    w = World(Store(path))
    w.start(SETTING)
    d = Director(w)
    d.configure({'offline': True})
    d.cfg['cooldown'] = 0
    for _ in range(7):
        assert d.step()
    return w, d


def at_entity(w, entity_id):
    """Fixture placement only: actions under test still pass through World.action."""
    e = next(e for e in w.region()['entities'] if e.get('local_id') == entity_id or e['id'] == entity_id)
    for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        x, y = e['x']+dx, e['y']+dy
        if w.region()['tiles'][y][x] not in C.BLOCKED:
            w.state['player'].update(x=x, y=y, facing=[-dx, -dy])
            return e
    raise AssertionError('entity has no approach')


def walk_to(w, e):
    """Real keyboard-equivalent movement, avoiding occupants, to an interaction cell."""
    r = w.region()
    start = (w.state['player']['x'], w.state['player']['y'])
    occupied = {(x['x'], x['y']) for x in r['entities'] if not x['spent'] and x['kind'] != 'exit'}
    targets = {(e['x']+dx, e['y']+dy) for dx,dy in ((0,1),(0,-1),(1,0),(-1,0))}
    q = deque([start]); parents = {start: None}; end = None
    while q:
        pos = q.popleft()
        if pos in targets:
            end = pos
            break
        for dx,dy in ((0,1),(0,-1),(1,0),(-1,0)):
            p = (pos[0]+dx, pos[1]+dy)
            if p in parents or p in occupied or not (0 <= p[0] < r['width'] and 0 <= p[1] < r['height']): continue
            if r['tiles'][p[1]][p[0]] in C.BLOCKED: continue
            parents[p] = pos; q.append(p)
    if end is None: raise AssertionError('interaction inaccessible with actual occupants')
    path = []
    while parents[end] is not None: path.append(end); end=parents[end]
    for x,y in reversed(path):
        p=w.state['player']; w.action({'op':'move','dx':x-p['x'],'dy':y-p['y']})
        assert w.state['battle'] is None
    w.action({'op':'interact','id':e['id']})


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.context = {'setting': SETTING, 'target':'r0','target_depth':0,'story_revision':0}
        self.raw = make_patch(self.context,'region')

    def test_valid_region(self):
        p=parse_patch(self.raw,'region')
        self.assertEqual(p['region']['biome'],'industrial')
        self.assertEqual(len(p['region']['quests']),3)

    def test_fenced_json(self):
        self.assertEqual(parse_patch('```json\n'+json.dumps(self.raw)+'\n```','region')['kind'],'region')

    def test_no_arbitrary_code_or_hard_state(self):
        for name in ('script','exec','hp','gold','player','filename','scene_path'):
            with self.subTest(name=name):
                p=copy.deepcopy(self.raw); p[name]='malicious'
                with self.assertRaises(InvalidPatch): parse_patch(p,'region')

    def test_unknown_enum(self):
        p=copy.deepcopy(self.raw);p['region']['rule']='delete_all_enemies'
        with self.assertRaises(InvalidPatch):parse_patch(p,'region')

    def test_budget_clamps(self):
        p=copy.deepcopy(self.raw);p['region']['items'][0].update(power=999999,price=-500)
        normalized=parse_patch(p,'region')['region']['items'][0]
        self.assertEqual(normalized['power'],8);self.assertEqual(normalized['price'],5)

    def test_invalid_number_types(self):
        for n in (True,'100',float('nan'),float('inf')):
            with self.subTest(n=n):
                p=copy.deepcopy(self.raw);p['region']['items'][0]['power']=n
                with self.assertRaises(InvalidPatch):parse_patch(p,'region')

    def test_reserved_item(self):
        p=copy.deepcopy(self.raw);p['region']['items'][0]['id']='potion'
        with self.assertRaises(InvalidPatch):parse_patch(p,'region')

    def test_duplicate_entity(self):
        p=copy.deepcopy(self.raw);p['region']['entities'].append(copy.deepcopy(p['region']['entities'][0]))
        with self.assertRaises(InvalidPatch):parse_patch(p,'region')

    def test_incompatible_effect(self):
        p=copy.deepcopy(self.raw);p['region']['items'][0].update(kind='consumable',effect='burn')
        with self.assertRaises(InvalidPatch):parse_patch(p,'region')

    def test_dangling_quest(self):
        for goal,target in [('talk','ghost'),('talk','warden'),('defeat','witness'),('collect','ether')]:
            with self.subTest(goal=goal,target=target):
                p=copy.deepcopy(self.raw);p['region']['quests'][0].update(goal=goal,target=target)
                with self.assertRaises(InvalidPatch):parse_patch(p,'region')

    def test_chest_must_reference_item(self):
        p=copy.deepcopy(self.raw);p['region']['entities'][3]['item_id']='made_up'
        with self.assertRaises(InvalidPatch):parse_patch(p,'region')

    def test_no_paths_in_id(self):
        p=copy.deepcopy(self.raw);p['region']['entities'][0]['id']='../../save'
        with self.assertRaises(InvalidPatch):parse_patch(p,'region')

    def test_reaction_cannot_replace_map(self):
        p={'kind':'reaction','reaction':{'text':'你好'},'region':self.raw['region']}
        with self.assertRaises(InvalidPatch):parse_patch(p,'reaction')

    def test_response_bounds_and_wrong_kind(self):
        with self.assertRaises(InvalidPatch):parse_patch(' '*128001,'region')
        with self.assertRaises(InvalidPatch):parse_patch(self.raw,'reaction')
        with self.assertRaises(InvalidPatch):parse_patch({'kind':'region'},'region')


class MapTests(unittest.TestCase):
    def test_deterministic_placement(self):
        raw=make_patch({'setting':SETTING,'target':'r0'},'region')
        plan=parse_patch(raw,'region')['region']
        links=[{'target':'r0a','direction':'forward','label':'出口'}]
        self.assertEqual(build_region(plan,'r0',123,0,links),build_region(plan,'r0',123,0,links))
        self.assertNotEqual(build_region(plan,'r0',123,0,links)['tiles'],build_region(plan,'r0',456,0,links)['tiles'])

    def test_252_generated_maps_are_reachable(self):
        plan=parse_patch(make_patch({'setting':SETTING,'target':'r0'},'region'),'region')['region']
        links=[{'target':'r0a','direction':'forward','label':'前方'},{'target':'parent','direction':'back','label':'返回'}]
        for layout in C.LAYOUTS:
            for biome in C.BIOMES:
                for seed in range(6):
                    with self.subTest(layout=layout,biome=biome,seed=seed):
                        p=copy.deepcopy(plan);p.update(layout=layout,biome=biome)
                        r=build_region(p,'test',seed,2,links)
                        area=reachable(r['tiles'],r['spawn'])
                        self.assertTrue(all((e['x'],e['y']) in area for e in r['entities']))
                        for e in r['entities']:
                            if e['kind']=='exit':self.assertIn((e['x'],e['y']-1),area)

    def test_entities_can_be_approached_through_actual_collision(self):
        w,d=make_world()
        try:
            e=next(e for e in w.region()['entities'] if e.get('local_id')=='witness')
            walk_to(w,e)
            self.assertEqual(w.state['ui']['kind'],'dialogue')
            self.assertEqual(d.calls,0)
        finally:w.store.close()


class RuntimeTests(unittest.TestCase):
    def setUp(self):self.w,self.d=make_world()
    def tearDown(self):self.w.store.close()

    def test_single_model_horizon_is_bounded(self):
        self.assertFalse(self.d.step())
        self.assertEqual(self.d.accepted,7)
        self.assertEqual(self.d.calls,0)
        self.assertEqual(sum(n['ready'] for n in self.w.state['topology'].values()),7)
        self.assertEqual(len(self.w.state['topology']),15)

    def test_prefetched_future_items_and_facts_are_not_canonical(self):
        s=self.w.state
        self.assertFalse(any(k.startswith('r0a:') for k in s['items']))
        self.assertFalse(s['topology']['r0a']['visited'])
        self.assertNotIn('visited:r0a',s['facts'])

    def test_walking_never_requests_llm(self):
        for _ in range(40):
            self.w.action({'op':'move','dx':0,'dy':-1})
            if self.w.state['battle']:break
            self.d.step()
        self.assertEqual(self.d.accepted,7)
        self.assertFalse(self.w.reaction_needed)

    def test_teleport_action_rejected(self):
        before=copy.deepcopy(self.w.state['player'])
        with self.assertRaises(GameError):self.w.action({'op':'move','dx':10,'dy':0})
        self.assertEqual(before,self.w.state['player'])

    def test_walls_block_movement(self):
        self.w.state['player'].update(x=2,y=2)
        self.w.action({'op':'move','dx':-1,'dy':0})
        self.assertEqual(self.w.state['player']['x'],2)

    def test_distant_interaction_does_not_open_chest(self):
        e=next(e for e in self.w.region()['entities'] if e['kind']=='chest')
        self.w.action({'op':'interact','id':e['id']})
        self.assertFalse(e['spent'])

    def test_chest_and_quest_are_once_only(self):
        e=at_entity(self.w,'cache')
        self.w.action({'op':'interact','id':e['id']})
        self.assertTrue(e['spent'])
        qty=self.w.state['player']['inventory'][e['item_id']]
        gold=self.w.state['player']['gold']
        self.w.action({'op':'close'})
        self.w.action({'op':'interact','id':e['id']})
        self.assertEqual(self.w.state['player']['inventory'][e['item_id']],qty)
        self.assertEqual(self.w.state['player']['gold'],gold)

    def test_generated_weapon_equips(self):
        e=at_entity(self.w,'cache');self.w.action({'op':'interact','id':e['id']});self.w.action({'op':'close'})
        self.w.action({'op':'use','id':e['item_id']})
        self.assertEqual(self.w.state['player']['weapon'],e['item_id'])

    def test_choice_changes_future_but_not_existing_geometry(self):
        original=copy.deepcopy(self.w.region()['tiles'])
        e=at_entity(self.w,'witness');self.w.action({'op':'interact','id':e['id']})
        self.w.action({'op':'choice','id':'mercy'})
        self.assertTrue(self.w.state['topology']['r0a']['ready'])
        self.assertTrue(self.w.state['topology']['r0a']['needs_refresh'])
        self.w.action({'op':'close'})
        for _ in range(4):self.d.step()
        self.assertEqual(original,self.w.region()['tiles'])
        self.assertIn('归人避难所',self.w.region('r0a')['name'])
        self.assertEqual(self.w.state['story_revision'],1)
        self.assertTrue(any('mercy' in str(f) for f in self.w.state['facts'].values()))

    def test_repeated_choice_cannot_be_reawarded(self):
        e=at_entity(self.w,'witness');self.w.action({'op':'interact','id':e['id']});self.w.action({'op':'choice','id':'mercy'})
        with self.assertRaises(GameError):self.w.action({'op':'choice','id':'mercy'})

    def test_stale_patch_is_discarded(self):
        ctx=self.w.context('r0aa');raw=make_patch(ctx,'region')
        self.w.state['story_revision']+=1
        self.assertFalse(self.w.apply_patch(raw,ctx))
        self.assertTrue(self.w.state['topology']['r0aa']['ready'])

    def test_old_world_response_is_discarded(self):
        ctx=self.w.context('r0aa');raw=make_patch(ctx,'region')
        self.w.start('另一个世界，只有海与星。')
        self.assertFalse(self.w.apply_patch(raw,ctx))

    def test_visited_map_cannot_be_replaced(self):
        ctx=self.w.context('r0');raw=make_patch(ctx,'region')
        self.assertFalse(self.w.apply_patch(raw,ctx))

    def test_reaction_cannot_mutate_stats(self):
        ctx=self.w.context('r0','reaction');before=copy.deepcopy(self.w.state['player'])
        raw={'kind':'reaction','reaction':{'text':'世界起了风','gold':9999}}
        with self.assertRaises(InvalidPatch):self.w.apply_patch(raw,ctx)
        self.assertEqual(before,self.w.state['player'])

    def test_bad_npc_update_rolls_back_entire_patch(self):
        ctx=self.w.context('r0','reaction');before=copy.deepcopy(self.w.region());state_before=copy.deepcopy(self.w.state)
        raw={'kind':'reaction','reaction':{'text':'错误补丁','weather':'snow','npc_lines':[{'id':'not_here','dialogue':['你好']} ]}}
        with self.assertRaises(InvalidPatch):self.w.apply_patch(raw,ctx)
        self.assertEqual(before,self.w.region())
        self.assertEqual(state_before,self.w.state)

    def test_merchant_uses_actual_gold(self):
        e=at_entity(self.w,'trader');self.w.action({'op':'interact','id':e['id']})
        self.w.action({'op':'buy','id':'potion'})
        self.assertEqual(self.w.state['player']['gold'],23)
        self.assertEqual(self.w.state['player']['inventory']['potion'],4)
        self.w.state['player']['gold']=0
        with self.assertRaises(GameError):self.w.action({'op':'buy','id':'potion'})
        self.assertEqual(self.w.state['player']['gold'],0)

    def test_no_buy_outside_shop(self):
        with self.assertRaises(GameError):self.w.action({'op':'buy','id':'potion'})

    def test_healing_cannot_exceed_max(self):
        self.w.state['player']['hp']=89
        self.w.action({'op':'use','id':'potion'})
        self.assertEqual(self.w.state['player']['hp'],90)
        qty=self.w.state['player']['inventory']['potion']
        with self.assertRaises(GameError):self.w.action({'op':'use','id':'potion'})
        self.assertEqual(self.w.state['player']['inventory']['potion'],qty)

    def test_battle_local_and_rewards_persist(self):
        e=at_entity(self.w,'watcher');self.w.action({'op':'interact','id':e['id']})
        self.assertIsNotNone(self.w.state['battle'])
        for _ in range(30):
            if self.w.state['battle'] is None:break
            p=self.w.state['player']
            move='potion' if p['hp']<25 and p['inventory'].get('potion',0) else 'skill' if p['mp']>=5 else 'attack'
            self.w.action({'op':'combat','move':move})
        self.assertIsNone(self.w.state['battle'])
        self.assertTrue(self.w.state['facts'].get('defeated:'+e['id']))
        self.assertEqual(self.d.calls,0)
        self.assertTrue(self.w.reaction_needed)

    def test_no_magic_rule_is_mechanical(self):
        self.w.region()['rule']='no_magic'
        e=at_entity(self.w,'watcher');self.w.action({'op':'interact','id':e['id']})
        mp=self.w.state['player']['mp']
        with self.assertRaises(GameError):self.w.action({'op':'combat','move':'skill'})
        self.assertEqual(self.w.state['player']['mp'],mp)
        self.assertEqual(self.w.state['battle']['turn'],0)

    def test_battle_cannot_be_closed_like_dialogue(self):
        e=at_entity(self.w,'watcher');self.w.action({'op':'interact','id':e['id']})
        with self.assertRaises(GameError):self.w.action({'op':'close'})

    def test_return_to_existing_map_is_identical(self):
        original=copy.deepcopy(self.w.region()['tiles'])
        e=next(e for e in self.w.region()['entities'] if e['kind']=='exit' and e['target']=='r0a')
        at_entity(self.w,e['id']);self.w.action({'op':'interact','id':e['id']})
        self.assertEqual(self.w.state['current'],'r0a')
        self.assertTrue(any(k.startswith('r0a:') for k in self.w.state['items']))
        back=next(e for e in self.w.region()['entities'] if e['kind']=='exit' and e['target']=='r0')
        at_entity(self.w,back['id']);self.w.action({'op':'interact','id':back['id']})
        self.assertEqual(self.w.state['current'],'r0')
        self.assertEqual(self.w.region()['tiles'],original)

    def test_pending_exit_does_not_teleport(self):
        target='r0a';self.w.state['topology'][target]['ready']=False
        e=next(e for e in self.w.region()['entities'] if e.get('target')==target)
        at_entity(self.w,e['id']);self.w.action({'op':'interact','id':e['id']})
        self.assertEqual(self.w.state['current'],'r0')
        self.assertEqual(self.w.state['ui']['kind'],'message')

    def test_map_cache_is_bounded(self):
        for _ in range(10):
            for _ in range(3):self.d.step()
            e=next(e for e in self.w.region()['entities'] if e['kind']=='exit' and e['direction']=='forward')
            at_entity(self.w,e['id']);self.w.action({'op':'interact','id':e['id']})
        self.assertLessEqual(len(self.w.cache),6)
        self.assertEqual(self.w.snapshot()['map_count'],11)


class PersistenceTests(unittest.TestCase):
    def test_save_reload_has_same_map_inventory_and_battle(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'world.sqlite3';w,d=make_world(path)
            e=at_entity(w,'cache');w.action({'op':'interact','id':e['id']});w.action({'op':'close'})
            e=at_entity(w,'watcher');w.action({'op':'interact','id':e['id']});w.action({'op':'combat','move':'attack'})
            before=w.snapshot();w.store.close()
            new=World(Store(path));self.assertEqual(before,new.snapshot());new.store.close()

    def test_sqlite_never_contains_api_key(self):
        with tempfile.TemporaryDirectory() as td:
            w,d=make_world(Path(td)/'world.sqlite3')
            d.configure({'offline':False,'api_key':'not-a-real-key-for-testing-privacy'})
            w.persist();w.store.close()
            for f in Path(td).iterdir():
                self.assertNotIn(b'not-a-real-key-for-testing-privacy',f.read_bytes())


class DirectorTests(unittest.TestCase):
    def setUp(self):
        self.w=World(Store(':memory:'));self.w.start(SETTING);self.d=Director(self.w)
        self.d.configure({'offline':False,'api_key':'not-a-real-key','max_calls':10});self.d.cfg['cooldown']=0
    def tearDown(self):self.d.stop();self.w.store.close()
    @staticmethod
    def answer(ctx,kind,repair=''):
        result=make_patch(ctx,kind)
        if kind=='region':
            result['region']['destinations']=[{'id':'next','name':'下一片区域','description':'测试模型生成的区域概要。'}]
            result['region']['visuals']=visual_fixture()
        return json.dumps(result,ensure_ascii=False),{'input_tokens':111,'output_tokens':222}

    def test_live_contract_and_usage_accounting(self):
        with patch.object(ChatProvider,'generate',side_effect=self.answer):
            self.assertTrue(self.d.step())
        self.assertEqual(self.d.calls,1);self.assertEqual(self.d.tokens_in,111);self.assertEqual(self.d.tokens_out,222)
        self.assertEqual(self.w.region()['source'],'llm')

    def test_schema_failure_allows_only_one_repair(self):
        with patch.object(ChatProvider,'generate',return_value=('{}',{'input_tokens':1,'output_tokens':1})) as mock:
            self.d.step();self.d.step()
        self.assertEqual(mock.call_count,2);self.assertEqual(self.d.calls,2)
        self.assertEqual(self.d.accepted,0);self.assertTrue(self.d.error)

    def test_network_errors_do_not_retry_automatically(self):
        with patch.object(ChatProvider,'generate',side_effect=ProviderError('offline')) as mock:
            for _ in range(4):self.d.step()
        self.assertEqual(mock.call_count,1)
        self.assertIsNone(self.w.region())

    def test_hard_request_budget(self):
        self.d.cfg['max_calls']=1
        with patch.object(ChatProvider,'generate',side_effect=self.answer) as mock:
            for _ in range(5):self.d.step()
        self.assertEqual(mock.call_count,1)
        self.assertEqual(self.d.calls,1)

    def test_schema_retry_respects_budget(self):
        self.d.cfg['max_calls']=1
        with patch.object(ChatProvider,'generate',return_value=('{}',{'input_tokens':1,'output_tokens':1})) as mock:self.d.step()
        self.assertEqual(mock.call_count,1)

    def test_pause_stops_new_requests(self):
        self.d.paused=True
        with patch.object(ChatProvider,'generate',side_effect=self.answer) as mock:self.assertFalse(self.d.step())
        self.assertEqual(mock.call_count,0)

    def test_reconfigure_does_not_reset_budget_or_lose_key(self):
        self.d.calls=6
        self.d.configure({'offline':False,'api_key':'','max_calls':8})
        self.assertEqual(self.d.calls,6)
        self.assertEqual(self.d.cfg['api_key'],'not-a-real-key')

    def test_response_from_old_config_is_not_applied(self):
        def change(ctx,kind,repair=''):
            self.d.configure({'offline':True})
            return self.answer(ctx,kind)
        with patch.object(ChatProvider,'generate',side_effect=change):self.d.step()
        self.assertIsNone(self.w.region())

    def test_reaction_is_deferred_until_modal_closed(self):
        with patch.object(ChatProvider,'generate',side_effect=self.answer):
            self.d.step()
            self.d.step()
        self.w.reaction_needed=True
        before=self.w.region()['revision']
        def interrupt(ctx,kind,repair=''):
            self.w.state['ui']={'kind':'message','title':'Busy','lines':['Blocking conversation']}
            return self.answer(ctx,kind)
        with patch.object(ChatProvider,'generate',side_effect=interrupt):self.d.step()
        self.assertIsNotNone(self.d.deferred)
        self.assertEqual(self.w.region()['revision'],before)
        self.w.action({'op':'close'});self.d.step()
        self.assertGreater(self.w.region()['revision'],before)


class MockChatHandler(BaseHTTPRequestHandler):
    mode='ok'
    last=None
    def log_message(self,*args):pass
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        MockChatHandler.last=data
        user=json.loads(data['messages'][-1]['content'])
        raw=make_patch(user['world_context'],user['requested_kind'])
        if self.mode=='redirect':
            self.send_response(302);self.send_header('Location','https://example.invalid/steal');self.end_headers();return
        body=json.dumps({'choices':[{'finish_reason':'length' if self.mode=='truncated' else 'stop','message':{'content':json.dumps(raw,ensure_ascii=False)}}],'usage':{'prompt_tokens':123,'completion_tokens':456}}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


class ProviderHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),MockChatHandler)
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.worker.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.worker.join()
    def setUp(self):
        MockChatHandler.mode='ok'
        self.cfg={'base_url':f'http://127.0.0.1:{self.server.server_port}/v1','model':'test-only','api_key':'fake-local-test-key','deepseek_options':True}
    def test_real_http_chat_completions_json_protocol(self):
        raw,usage=ChatProvider(self.cfg).generate({'setting':SETTING,'target':'r0'},'region')
        self.assertEqual(parse_patch(raw,'region')['kind'],'region');self.assertEqual(usage['output_tokens'],456)
        self.assertEqual(MockChatHandler.last['thinking'],{'type':'enabled'})
        self.assertEqual(MockChatHandler.last['reasoning_effort'],'low')
        self.assertEqual(MockChatHandler.last['max_tokens'],16384)
        self.assertEqual(MockChatHandler.last['response_format'],{'type':'json_object'})
        self.assertNotIn('fake-local-test-key',json.dumps(MockChatHandler.last))
    def test_generic_compatibility_omits_provider_option(self):
        self.cfg['deepseek_options']=False
        self.cfg['reasoning_effort']='default'
        ChatProvider(self.cfg).generate({'setting':SETTING,'target':'r0'},'region')
        self.assertNotIn('thinking',MockChatHandler.last)
        self.assertNotIn('reasoning_effort',MockChatHandler.last)
    def test_thinking_levels_reach_actual_http_payload(self):
        for effort in ('low','high','max','none'):
            with self.subTest(effort=effort):
                self.cfg['reasoning_effort']=effort
                ChatProvider(self.cfg).generate({'setting':SETTING,'target':'r0'},'reaction')
                self.assertEqual(MockChatHandler.last['reasoning_effort'],effort)
                self.assertEqual(MockChatHandler.last['thinking']['type'],'disabled' if effort=='none' else 'enabled')
                self.assertEqual(MockChatHandler.last['max_tokens'],1500 if effort=='none' else 32768 if effort=='max' else 16384 if effort=='high' else 8192)
    def test_custom_service_can_set_effort_without_deepseek_extension(self):
        self.cfg.update(deepseek_options=False,reasoning_effort='medium')
        ChatProvider(self.cfg).generate({'setting':SETTING,'target':'r0'},'region')
        self.assertEqual(MockChatHandler.last['reasoning_effort'],'medium')
        self.assertNotIn('thinking',MockChatHandler.last)
    def test_truncated_response_rejected(self):
        MockChatHandler.mode='truncated'
        with self.assertRaises(ProviderError):ChatProvider(self.cfg).generate({'setting':SETTING,'target':'r0'},'region')
    def test_redirect_cannot_leak_key(self):
        MockChatHandler.mode='redirect'
        with self.assertRaises(ProviderError):ChatProvider(self.cfg).generate({'setting':SETTING,'target':'r0'},'region')
    def test_remote_http_and_credential_urls_rejected(self):
        for url in ('http://example.com','file:///tmp/data','https://name:pass@api.deepseek.com','https://api.deepseek.com?key=x'):
            with self.subTest(url=url):
                with self.assertRaises(ProviderError):validate_url(url)


class ServerHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server=GameServer(('127.0.0.1',0),':memory:','test-session-only')
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()
    def tearDown(self):
        self.server.director.stop();self.server.shutdown();self.server.server_close();self.worker.join();self.server.world.store.close()
    def request(self,path='/state',data=None,token='test-session-only',extra=None,request_id=''):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        headers={'Authorization':'Bearer '+token}
        if data is not None:headers['Content-Type']='application/json'
        if request_id:headers['X-Request-ID']=request_id
        headers.update(extra or {})
        conn.request('GET' if data is None else 'POST',path,body=None if data is None else json.dumps(data),headers=headers)
        r=conn.getresponse();body=json.loads(r.read());status=r.status;conn.close();return status,body
    def start_demo(self):
        self.assertEqual(self.request('/start',{'setting':SETTING,'offline':True})[0],200)
        self.server.director.cfg['cooldown']=0
        for _ in range(3):self.server.director.step()
    def test_unauthenticated_requests_rejected(self):self.assertEqual(self.request(token='wrong')[0],401)
    def test_browser_origin_rejected(self):self.assertEqual(self.request(extra={'Origin':'https://evil.invalid'})[0],401)
    def test_new_save_needs_explicit_replace(self):
        self.start_demo()
        status,_=self.request('/start',{'setting':'另一个世界','offline':True})
        self.assertEqual(status,400)
        self.assertEqual(self.server.world.state['setting'],SETTING)
    def test_no_key_in_snapshot(self):
        self.request('/configure',{'offline':False,'api_key':'never-expose-this-key'})
        self.assertNotIn('never-expose-this-key',json.dumps(self.request()[1]))
    def test_request_id_is_idempotent(self):
        self.start_demo()
        with self.server.world.lock:
            w=self.server.world;e=at_entity(w,'trader');w.action({'op':'interact','id':e['id']})
        for _ in range(2):self.assertEqual(self.request('/action',{'op':'buy','id':'potion'},request_id='one-purchase')[0],200)
        self.assertEqual(self.server.world.state['player']['inventory']['potion'],4)
    def test_body_limit(self):self.assertEqual(self.request('/action',{'op':'x'*20000})[0],413)
    def test_bad_action_does_not_crash_server(self):
        self.start_demo()
        self.assertEqual(self.request('/action',{'op':'exec','script':'rm everything'})[0],400)
        self.assertEqual(self.request()[0],200)
    def test_only_loopback_bindings(self):
        with self.assertRaises(ValueError):GameServer(('0.0.0.0',0),':memory:','x')


if __name__=='__main__':unittest.main()
