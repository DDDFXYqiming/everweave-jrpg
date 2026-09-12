"""Real worker concurrency, causal invalidation and usable exit contracts."""
import copy
import json
import threading
import time
import unittest
from unittest.mock import patch

from content_fixtures import authored_patch
from engine.content_prompt import model_context
from engine.director import ChatProvider, Director
from engine.schema import InvalidPatch
from engine.storage import Store
from engine.world import GameError, World
from test_runtime import at_entity


def two_exits():
    raw=authored_patch()
    raw['region']['destinations'].append(dict(id='other',name='另一条路',description='独立的下一地区'))
    raw['region']['scene']['anchors']['forward_1']=[26,16]
    return raw


class GenerationSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.w=World(Store(':memory:'));self.w.start('后台预生成回归')
        self.w.apply_patch(two_exits(),self.w.context())
        self.targets=list(self.w.state['topology']['r0']['children'])
        self.d=Director(self.w)
        self.d.configure(dict(offline=False,api_key='mock-only',max_calls=2));self.d.cfg['cooldown']=0

    def tearDown(self):self.d.stop();self.w.store.close()

    def test_player_events_do_not_discard_either_in_flight_exit(self):
        both=threading.Event();release=threading.Event();mutex=threading.Lock();seen=[]
        def answer(provider,ctx,kind,repair=''):
            with mutex:
                seen.append(ctx['target'])
                if len(seen)==2:both.set()
            if not release.wait(5):raise AssertionError('request not released')
            return json.dumps(authored_patch()),{}
        try:
            with patch.object(ChatProvider,'generate',answer):
                self.d.start_worker()
                self.assertTrue(both.wait(3))
                with self.w.lock:
                    self.assertEqual(self.w.state['steps'],0)
                    self.assertFalse(self.w.state['ui'])
                    active=self.d.status()['active_tasks']
                    self.assertTrue(all(t['source']=='prefetch' and t['started_steps']==0 for t in active))
                    self.w.action({'op':'invoke','id':'tune'})
                    self.assertGreater(self.w.state['story_revision'],0)
                    self.d.paused=True
                release.set()
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    with self.w.lock:
                        if not self.d.in_flight:break
                    time.sleep(.01)
                with self.w.lock:
                    self.assertEqual((self.d.calls,self.d.accepted,self.d.stale),(2,2,0))
                    self.assertTrue(all(self.w.state['topology'][t]['ready'] for t in self.targets))
                    self.assertTrue(all(t['status']=='ready' for t in self.d.task_history))
                    self.assertTrue(all(t['request_seconds']>0 for t in self.d.task_history))
                self.assertEqual(set(seen),set(self.targets))
        finally:release.set()

    def test_worker_generates_two_hops_without_any_portal_or_player_action(self):
        self.d.cfg['max_calls']=6
        with patch.object(ChatProvider,'generate',return_value=(json.dumps(two_exits()),{})):
            self.d.start_worker()
            deadline=time.monotonic()+6
            while time.monotonic()<deadline:
                with self.w.lock:
                    if self.d.accepted==6:break
                time.sleep(.01)
            self.d.paused=True;self.d.stop()
        self.assertEqual(self.d.accepted,6)
        self.assertEqual(self.w.state['steps'],0)
        self.assertEqual(self.w.state['current'],'r0')
        self.assertTrue(all(self.w.state['topology'][t]['ready'] for t,_ in self.w.prefetch_targets()))

    def test_only_explicit_changed_outline_invalidates_its_request(self):
        contexts=[self.w.context(t) for t in self.targets]
        event,_=self.w.story('choice','选择打开水闸');self.w.persist(event=event)
        self.assertTrue(all(self.w.context_is_current(ctx) for ctx in contexts))
        update={'kind':'reaction','reaction':{'text':'第一条路被洪水改变。','future_updates':[
            {'id':self.targets[0],'description':'洪水经过的新道路'}]}}
        self.w.apply_patch(update,self.w.context(kind='reaction'))
        self.assertFalse(self.w.context_is_current(contexts[0]))
        self.assertTrue(self.w.context_is_current(contexts[1]))
        self.assertFalse(self.w.apply_patch(authored_patch(),contexts[0]))
        self.assertTrue(self.w.apply_patch(authored_patch(),contexts[1]))

    def test_explicit_refresh_keeps_prepared_map_usable_and_is_idempotent(self):
        target=self.targets[0]
        self.w.apply_patch(authored_patch(),self.w.context(target))
        original=copy.deepcopy(self.w.region(target))
        update={'kind':'reaction','reaction':{'text':'选择改变了一条后路。','future_updates':[
            {'id':'terrace','name':'洪水后的露台','description':'新出现的水路'}]}}
        self.w.apply_patch(update,self.w.context(kind='reaction'))
        node=self.w.state['topology'][target]
        self.assertTrue(node['ready']);self.assertTrue(node['needs_refresh'])
        self.assertEqual(self.w.region(target),original)
        self.w.apply_patch(update,self.w.context(kind='reaction'))
        self.assertEqual(node['generation_revision'],1)
        gate=at_entity(self.w,next(e['id'] for e in self.w.region()['entities'] if e.get('target')==target))
        self.w.action({'op':'interact','id':gate['id']})
        self.assertEqual(self.w.state['current'],target)
        self.assertEqual(node['name'],original['name'])

    def test_failed_reaction_cannot_rewrite_visited_outline(self):
        before=self.w.snapshot()
        with self.assertRaises(InvalidPatch):
            self.w.apply_patch({'kind':'reaction','reaction':{'text':'无效更新','future_updates':[
                {'id':'r0','description':'不能修改过去'}]}},self.w.context(kind='reaction'))
        self.assertEqual(self.w.snapshot(),before)

    def test_pending_exit_updates_without_reopening_or_another_request(self):
        target=self.targets[0]
        gate=at_entity(self.w,next(e['id'] for e in self.w.region()['entities'] if e.get('target')==target))
        self.w.action({'op':'interact','id':gate['id']})
        self.assertFalse(self.w.snapshot()['ui']['ready'])
        with self.assertRaises(GameError):self.w.action({'op':'enter_exit'})
        self.w.apply_patch(authored_patch(),self.w.context(target))
        self.assertTrue(self.w.snapshot()['ui']['ready'])
        self.assertEqual(self.w.state['current'],'r0')
        self.w.action({'op':'enter_exit'})
        self.assertEqual(self.w.state['current'],target)
        self.assertEqual(self.d.calls,0)

    def test_waiting_ui_does_not_allow_remote_entry(self):
        target=self.targets[0]
        gate=at_entity(self.w,next(e['id'] for e in self.w.region()['entities'] if e.get('target')==target))
        self.w.action({'op':'interact','id':gate['id']})
        self.w.apply_patch(authored_patch(),self.w.context(target))
        self.w.state['player'].update(x=4,y=10)
        with self.assertRaises(GameError):self.w.action({'op':'enter_exit'})
        self.assertEqual(self.w.state['current'],'r0')

    def test_region_model_input_drops_old_executable_content_but_keeps_story(self):
        ctx=self.w.context(self.targets[0]);ctx['rejected_response']='original rejected JSON'
        original=copy.deepcopy(ctx);result=model_context(ctx,'region')
        self.assertEqual(ctx,original)
        for key in ('current_program','current_runtime','current_scene','known_sprites'):
            self.assertNotIn(key,result)
        for key in ('destination','facts','lore','threads','rejected_response'):
            self.assertEqual(result[key],ctx[key])
        self.assertFalse(any(e['kind']=='exit' for e in result['current_region']['entities']))
        self.assertEqual(model_context(ctx,'reaction'),ctx)
        self.assertLess(len(json.dumps(result)),len(json.dumps(ctx)))


class FootprintApproachTests(unittest.TestCase):
    def test_material_confusion_reports_base_and_paint_together(self):
        from engine.schema import parse_patch
        raw=authored_patch();raw['region']['scene']['base']='metal'
        raw['region']['scene']['paint'][0]['tile']='wood'
        with self.assertRaises(InvalidPatch) as caught:parse_patch(raw,'region')
        paths={i['path'] for i in caught.exception.issues}
        self.assertIn('region.scene.base',paths)
        self.assertIn('region.scene.paint[0].tile',paths)

    def test_interaction_at_far_edge_matches_the_geometry_validator(self):
        w=World(Store(':memory:'));w.start('大型装置边缘可交互')
        try:
            raw=authored_patch();r=raw['region'];r['scene']['paint'].append({'rect':[4,3,4,4],'tile':'water'})
            r['entities'][0].update(at=[5,5],footprint=[3,2],solid=True)
            w.apply_patch(raw,w.context())
            w.state['player'].update(x=8,y=4)
            w.action({'op':'invoke','id':'tune'})
            self.assertEqual(w.region()['runtime']['vars']['presses'],1)
        finally:w.store.close()

    def test_truly_inaccessible_footprint_has_a_precise_error_path(self):
        w=World(Store(':memory:'));w.start('不可达装置仍须拒绝')
        try:
            raw=authored_patch();r=raw['region'];r['scene']['paint'].append({'rect':[3,2,7,6],'tile':'water'})
            r['entities'][0].update(at=[5,5],footprint=[3,2],solid=True)
            with self.assertRaises(InvalidPatch) as caught:w.apply_patch(raw,w.context())
            self.assertTrue(any(i['path']=='region.entities[0].at' and i['category']=='gameplay' for i in caught.exception.issues))
            self.assertIsNone(w.region())
        finally:w.store.close()


if __name__=='__main__':unittest.main()
