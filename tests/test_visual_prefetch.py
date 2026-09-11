"""Visual authoring and proactive whole-frontier contracts."""
import copy
import unittest
import threading
from unittest.mock import patch
from test_runtime import make_world,at_entity
import test_runtime as runtime_tests
from visual_fixtures import visual_fixture
from engine.demo import make_patch
from engine.schema import InvalidPatch,parse_patch
from engine.visuals import validate_visuals
from engine.visuals import freeze_sprite
from engine.world import World
from engine.storage import Store
from engine.director import Director,ChatProvider,ProviderError

class VisualTests(unittest.TestCase):
    def test_recipes_survive_compilation_and_storage(self):
        w=World(Store(':memory:'));w.start('完全不同的图形世界。')
        try:
            ctx=w.context();raw=make_patch(ctx,'region');raw['region']['visuals']=visual_fixture()
            w.apply_patch(raw,ctx)
            expected=visual_fixture();expected['sprites']['hero']=freeze_sprite(expected['sprites']['hero'],expected['palette'])
            self.assertEqual(w.snapshot()['region']['visuals'],expected)
            self.assertEqual(w.store.load_region('r0')['visuals'],expected)
            self.assertFalse(any(p['kind']=='tree' for p in w.region()['props']))
        finally:w.store.close()
    def test_player_identity_keeps_initial_shape_and_colors_between_regions(self):
        w=World(Store(':memory:'));w.start('角色外观连续性测试。')
        try:
            first=make_patch(w.context(),'region');first['region']['visuals']=visual_fixture()
            w.apply_patch(first,w.context())
            hero=copy.deepcopy(w.state['hero_visual'])
            ctx=w.context('r0a');second=make_patch(ctx,'region');second['region']['visuals']=visual_fixture()
            second['region']['visuals']['palette']['accent']='#ff0000'
            second['region']['visuals']['sprites']['hero']['layers'][0][1]=1
            w.apply_patch(second,ctx)
            self.assertEqual(w.region('r0a')['visuals']['sprites']['hero'],hero)
            self.assertEqual(w.region('r0a')['visuals']['palette']['accent'],'#ff0000')
        finally:w.store.close()
    def test_no_executable_visual_commands(self):
        for command in [['script','evil'],['load','https://example.invalid/x'],['rect',0,0,999999,2,'accent']]:
            v=visual_fixture();v['sprites']['hero']['layers'][0]=command
            with self.subTest(command=command):
                with self.assertRaises(InvalidPatch):validate_visuals(v)
    def test_named_visuals_must_exist(self):
        raw=make_patch({'setting':'星空世界','target':'r0'},'region')
        raw['region']['visuals']=visual_fixture();raw['region']['entities'][0]['sprite']='missing'
        with self.assertRaises(InvalidPatch):parse_patch(raw,'region')
    def test_nested_continuity_fields_preserve_data_but_not_model_allocated_id(self):
        raw=make_patch({'setting':'机械城市','target':'r0'},'region')
        lore=raw.pop('lore');threads=raw.pop('threads')
        raw['region'].update(id='model_guessed_id',lore=lore,threads=threads)
        result=parse_patch(raw,'region')
        self.assertEqual(result['lore'],lore)
        self.assertEqual(result['threads'],threads)
        self.assertNotIn('id',result['region'])
        raw['lore']=[{'id':'conflict','text':'different'}]
        with self.assertRaises(InvalidPatch):parse_patch(raw,'region')
    def test_motifs_are_data_not_palette_only(self):
        a=visual_fixture();b=copy.deepcopy(a)
        b['sprites']['building']['layers'][0]=['poly',[[1,1],[15,1],[8,15]],'accent']
        self.assertNotEqual(validate_visuals(a)['sprites'],validate_visuals(b)['sprites'])
    def test_custom_machine_recipes_do_not_require_a_tree_named_vegetation(self):
        v=visual_fixture()
        v['sprites']['reactor']=v['sprites'].pop('building')
        v['sprites']['antenna']=v['sprites'].pop('vegetation')
        v['sprites']['crate']=v['sprites'].pop('object')
        v['scenery']=['antenna']
        raw=make_patch({'setting':'无树的机械城市','target':'r0'},'region')
        raw['region']['visuals']=v
        raw['region']['landmarks'][0]['sprite']='reactor'
        raw['region']['entities'][3]['sprite']='crate'
        result=parse_patch(raw,'region')['region']['visuals']
        self.assertEqual(result['bindings']['building'],'reactor')
        self.assertEqual(result['bindings']['vegetation'],'antenna')
        self.assertEqual(result['bindings']['object'],'crate')

class PrefetchTests(unittest.TestCase):
    def setUp(self):self.w,self.d=make_world()
    def tearDown(self):self.w.store.close()
    def test_two_workers_prepare_distinct_regions_with_bounded_concurrency(self):
        self.w.state['topology']['r0a']['ready']=False
        self.w.state['topology']['r0b']['ready']=False
        self.d.configure({'offline':False,'api_key':'test','max_calls':2});self.d.cfg['cooldown']=0
        both=threading.Event();release=threading.Event();mutex=threading.Lock();targets=[]
        def answer(context,kind,repair=''):
            with mutex:
                targets.append(context['target'])
                if len(targets)==2:both.set()
            release.wait(3)
            return runtime_tests.DirectorTests.answer(context,kind,repair)
        try:
            with patch.object(ChatProvider,'generate',side_effect=answer):
                self.d.start_worker()
                self.assertTrue(both.wait(3))
                with self.w.lock:
                    self.assertEqual(len(self.d.in_flight),2)
                    self.d.paused=True
                release.set();self.d.stop()
            self.assertEqual(set(targets),{'r0a','r0b'})
            self.assertEqual(self.d.calls,2)
        finally:release.set();self.d.stop()
    def test_every_exit_and_its_next_layer_is_ready_without_movement(self):
        self.assertEqual(self.w.state['steps'],0)
        horizon=self.w.prefetch_targets()
        self.assertEqual(len(horizon),6)
        self.assertTrue(all(self.w.state['topology'][rid]['ready'] for rid,_ in horizon))
        self.assertFalse(self.d.step())
        self.assertEqual(self.d.status()['prefetch_ready'],6)
    def test_entering_ready_region_has_all_outgoing_maps_already_ready(self):
        gate=next(e for e in self.w.region()['entities'] if e.get('target')=='r0a')
        at_entity(self.w,gate['id']);calls=self.d.calls
        self.w.action({'op':'interact','id':gate['id']})
        self.assertTrue(all(x['ready'] for x in self.w.snapshot()['frontier']))
        self.assertEqual(self.d.calls,calls)
    def test_choice_keeps_prepared_exit_usable_during_refresh_failure(self):
        event,deleted=self.w.story('choice','改变后续方向');self.w.persist(event=event,delete=deleted)
        self.assertEqual(deleted,[])
        self.d.configure({'offline':False,'api_key':'test'});self.d.cfg['cooldown']=0
        with patch.object(ChatProvider,'generate',side_effect=ProviderError('test failure')):self.d.step()
        gate=next(e for e in self.w.region()['entities'] if e.get('target')=='r0a')
        at_entity(self.w,gate['id']);self.w.action({'op':'interact','id':gate['id']})
        self.assertEqual(self.w.state['current'],'r0a')
    def test_failed_branch_does_not_stop_other_prefetch(self):
        self.w.state['topology']['r0a']['ready']=False
        self.w.state['topology']['r0b']['ready']=False
        self.d.failed.add(('region','r0a'))
        job=self.d._next_job()
        self.assertEqual(job[0]['target'],'r0b')
    def test_deferred_reaction_does_not_block_other_map_generation(self):
        self.w.state['ui']={'kind':'message','title':'read','lines':['read']}
        self.d.deferred=(make_patch(self.w.context(kind='reaction'),'reaction'),self.w.context(kind='reaction'),'offline_demo',self.d.generation)
        self.w.state['topology']['r0b']['ready']=False
        self.assertTrue(self.d.step())
        self.assertTrue(self.w.state['topology']['r0b']['ready'])
        self.assertIsNotNone(self.d.deferred)
    def test_parent_outline_is_available_before_player_visits(self):
        context=self.w.context('r0aa')
        self.assertEqual(context['planned_parent']['id'],'r0a')
        self.assertFalse(self.w.state['topology']['r0a']['visited'])
