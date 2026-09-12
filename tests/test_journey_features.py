"""Player knowledge, authored possessions and durable history regressions."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from content_fixtures import authored_patch
from engine.director import ChatProvider,Director
from engine.storage import Store
from engine.world import World,GameError
from engine.schema import InvalidPatch
from engine.read_views import atlas,journal
from test_runtime import make_world,at_entity


def opening(item_id='leaf_salve'):
    raw=authored_patch()
    raw['region']['items']=[dict(id=item_id,name='驿站叶膏',kind='consumable',description='树脂与草叶调成的膏。',effect='heal',power=20,price=10,sprite='object'),
        dict(id='letter',name='无名收件人的信',kind='key',effect='attack',power=1,price=5,sprite='object')]
    raw['region']['starting_loadout']=dict(inventory=[dict(item_id=item_id,count=2),dict(item_id='letter',count=1)])
    return raw


class AuthoredPossessionsTests(unittest.TestCase):
    def setUp(self):
        self.w=World(Store(':memory:'));self.w.start('树上驿站',authored=True)
    def tearDown(self):self.w.store.close()
    def test_live_start_has_no_implicit_kit_and_grants_authored_items_once(self):
        self.assertEqual(self.w.state['items'],{})
        self.assertEqual(self.w.state['player']['inventory'],{})
        raw=opening();ctx=self.w.context()
        self.w.apply_patch(raw,ctx)
        self.assertEqual(self.w.state['player']['inventory'],{'r0:leaf_salve':2,'r0:letter':1})
        self.assertEqual(self.w.state['player']['weapon'],'')
        self.assertIn('icon_visual',self.w.state['items']['r0:leaf_salve'])
        self.assertFalse(self.w.apply_patch(raw,ctx))
        self.assertEqual(self.w.state['player']['inventory']['r0:leaf_salve'],2)
    def test_local_potion_is_authored_identity_not_global_default(self):
        self.w.apply_patch(opening('potion'),self.w.context())
        self.assertNotIn('potion',self.w.state['items'])
        self.assertEqual(self.w.state['items']['r0:potion']['name'],'驿站叶膏')
    def test_local_potion_chest_and_quest_keep_the_authored_identity(self):
        raw=opening('potion')
        raw['region']['entities'].append(dict(id='supply',kind='chest',name='叶膏包',at=[7,12],item_id='potion'))
        raw['region']['quests']=[dict(id='recover',name='找到叶膏',goal='collect',target='potion')]
        self.w.apply_patch(raw,self.w.context())
        e=at_entity(self.w,'supply');self.w.action(dict(op='interact',id=e['id']))
        self.assertEqual(self.w.state['player']['inventory']['r0:potion'],3)
        self.assertEqual(self.w.state['quests']['r0:recover']['status'],'complete')
        self.assertNotIn('potion',self.w.state['items'])
    def test_invalid_loadout_rolls_back_everything(self):
        raw=opening();raw['region']['starting_loadout']['weapon']='leaf_salve'
        before=copy.deepcopy(self.w.state)
        with self.assertRaises(InvalidPatch):self.w.apply_patch(raw,self.w.context())
        self.assertEqual(self.w.state,before)
        self.assertIsNone(self.w.region())
    def test_missing_loadout_enters_bounded_model_repair(self):
        d=Director(self.w);d.configure(dict(offline=False,api_key='test',max_calls=2));seen=[]
        def answer(provider,ctx,kind,repair=''):
            seen.append((ctx,repair))
            return json.dumps(opening() if repair else authored_patch()),{}
        with patch.object(ChatProvider,'generate',answer):d.step()
        self.assertEqual(d.accepted,1)
        self.assertIn('starting_loadout',seen[1][1])
        self.assertIn('rejected_response',seen[1][0])
    def test_supply_availability_matches_real_use_and_is_read_only(self):
        self.w.apply_patch(opening(),self.w.context())
        before=copy.deepcopy(self.w.state)
        item=next(i for i in self.w.snapshot()['inventory'] if i['id']=='r0:leaf_salve')
        self.assertFalse(item['usable']['enabled'])
        self.assertEqual(self.w.state,before)
        self.w.state['player']['hp']=60
        item=next(i for i in self.w.snapshot()['inventory'] if i['id']=='r0:leaf_salve')
        self.assertTrue(item['usable']['enabled'])
        self.w.action(dict(op='use',id=item['id']))
        self.assertEqual(self.w.state['player']['hp'],80)
        self.assertEqual(self.w.state['player']['inventory'][item['id']],1)
    def test_merchant_does_not_inject_legacy_defaults(self):
        raw=opening();raw['region']['entities'].append(dict(id='merchant',name='驿站商人',kind='npc',role='merchant',at=[7,12]))
        self.w.apply_patch(raw,self.w.context())
        e=at_entity(self.w,'merchant');self.w.action(dict(op='interact',id=e['id']))
        self.assertEqual(set(self.w.state['ui']['stock']),{'r0:leaf_salve','r0:letter'})
    def test_custom_condition_has_same_block_reason_without_side_effects(self):
        raw=opening();item=raw['region']['items'][0]
        item['use']=dict(label='付费调配',when={'op':'ge','args':[{'get':'player.gold'},50]},effects=[{'op':'stat','target':'player','name':'hp','delta':10}])
        self.w.apply_patch(raw,self.w.context());before=copy.deepcopy(self.w.state)
        entry=next(i for i in self.w.snapshot()['inventory'] if i['id']=='r0:leaf_salve')
        self.assertFalse(entry['usable']['enabled']);self.assertIn('金币 ×50',entry['usable']['blocked_reason'])
        with self.assertRaisesRegex(InvalidPatch,'金币'):self.w.action(dict(op='use',id=entry['id']))
        self.assertEqual(self.w.state,before)
    def test_later_regions_cannot_grant_another_starting_kit(self):
        self.w.apply_patch(opening(),self.w.context())
        target=self.w.state['topology']['r0']['children'][0]
        before=copy.deepcopy(self.w.state)
        with self.assertRaises(InvalidPatch):self.w.apply_patch(opening(),self.w.context(target))
        self.assertEqual(self.w.state,before)


class JourneyKnowledgeTests(unittest.TestCase):
    def setUp(self):self.w,self.d=make_world()
    def tearDown(self):self.w.store.close()
    def test_only_visited_and_disclosed_exits_are_visible(self):
        before=copy.deepcopy(self.w.state)
        data=atlas(self.w);nodes={n['id']:n for n in data['nodes']}
        self.assertEqual(set(nodes),{'r0','r0a','r0b'})
        self.assertTrue(nodes['r0a']['ready']);self.assertFalse(nodes['r0a']['visited'])
        self.assertIsNone(nodes['r0a']['thumbnail']);self.assertEqual(nodes['r0a']['tasks'],[])
        self.assertEqual(self.w.state,before);self.assertEqual(self.d.calls,0)
    def test_visit_reveals_connections_but_failed_exit_remains_visible(self):
        gate=at_entity(self.w,next(e['id'] for e in self.w.region()['entities'] if e.get('target')=='r0a'))
        self.w.action(dict(op='interact',id=gate['id']))
        self.w.state['topology']['r0ab']['ready']=False
        nodes={n['id']:n for n in atlas(self.w)['nodes']}
        self.assertIn('r0aa',nodes);self.assertIn('r0ab',nodes)
        self.assertFalse(nodes['r0ab']['ready'])
        self.assertNotIn('r0ba',nodes)
    def test_old_places_are_not_limited_by_model_context_window(self):
        for i in range(40):
            key='old_'+str(i);self.w.state['topology'][key]=dict(visited=True,ready=True,name=key,parent='r0',children=[])
            self.w.state['topology']['r0']['children'].append(key)
        self.assertEqual(len(atlas(self.w)['nodes']),43)
        self.assertLessEqual(len(self.w.context()['known_locations']),18)
    def test_all_active_tasks_are_pageable_without_poll_snapshot_growth(self):
        for i in range(65):self.w.state['quests']['task_'+str(i)]=dict(id='task_'+str(i),name='任务',description='说明',region='r0',status='active')
        cursor=None;ids=[]
        while True:
            page=journal(self.w,'active',cursor,13);ids.extend(e['id'] for e in page['entries']);cursor=page['next_cursor']
            if cursor is None:break
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(all('task_'+str(i) in ids for i in range(65)))
        self.assertLessEqual(len(self.w.snapshot()['quests']),20)
    def test_history_survives_recent_buffer_and_rollback(self):
        for i in range(130):self.w.note('记录 '+str(i));self.w.persist()
        cursor=None;texts=[]
        while True:
            page=journal(self.w,'history',cursor,17);texts.extend(e['description'] for e in page['entries']);cursor=page['next_cursor']
            if cursor is None:break
        self.assertIn('记录 0',texts);self.assertIn('记录 129',texts)
        self.assertEqual(len(texts),len(set(texts)))
        self.assertLessEqual(len(self.w.state['journal']),80)
        self.assertLessEqual(len(self.w.snapshot()['journal']),10)
        def abort():
            self.w.note('不可留下');self.w.persist();raise ValueError('rollback')
        from engine.gameplay import transaction
        with self.assertRaises(ValueError):transaction(self.w,abort)
        self.assertNotIn('不可留下',[e['description'] for e in journal(self.w)['entries']])
    def test_redesign_forgets_only_selected_failure(self):
        a=self.w.context('r0aa');b=self.w.context('r0ab')
        for ctx in (a,b):self.d._failure(InvalidPatch('bad'),ctx,'original failed JSON')
        self.d.retry('r0aa','region','redesign')
        self.assertNotIn(('region','r0aa'),self.d.failed_payloads)
        self.assertIn(('region','r0ab'),self.d.failed_payloads)
        with self.assertRaises(Exception):self.d.retry(None,None,'redesign')


if __name__=='__main__':unittest.main()
