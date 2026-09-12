"""Behavioral acceptance tests: no model service and no puzzle-specific engine code."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from content_fixtures import authored_patch, expr, get
from engine.world import World
from engine.storage import Store
from engine.schema import parse_patch, InvalidPatch
from engine.content import program
from engine.runtime import Runtime, RuleError
from engine.director import Director, ChatProvider
from engine.scene import build, paint


class ExecutableTests(unittest.TestCase):
    def setUp(self):
        self.w=World(Store(':memory:'));self.w.start('一个由规则程序构成的世界。')
        self.w.apply_patch(authored_patch(),self.w.context())
    def tearDown(self): self.w.store.close()
    def close(self):
        if self.w.state['ui']: self.w.action({'op':'close'})
    def invoke(self,key='tune'):
        self.close();self.w.action({'op':'invoke','id':key})
    def test_variable_scene_shape_and_authored_surfaces(self):
        r=self.w.region();self.assertEqual((r['width'],r['height']),(28,20))
        self.assertEqual(r['surfaces'][1][1],'floor');self.assertEqual(r['tiles'][9][12],3)
        self.assertEqual(r['tiles'][10][12],1)
    def test_distinct_object_drawing_and_animation_survive_save(self):
        art=self.w.region()['visuals']
        self.assertNotEqual(art['sprites']['gate'],art['sprites']['opened'])
        self.assertEqual(len(art['sprites']['npc']['frames']),2)
        self.assertEqual(self.w.store.load_region('r0')['visuals'],art)
    def test_actual_interaction_menu_invokes_data_action(self):
        self.w.action({'op':'interact','id':'r0:lever'})
        self.assertEqual(self.w.state['ui']['kind'],'actions')
        self.assertEqual(self.w.state['ui']['actions'][0]['label'],'校准余光')
        self.w.action({'op':'content_action','id':'tune'})
        self.assertEqual(self.w.region()['runtime']['vars']['presses'],1)
    def test_no_canned_quest_enum_required_for_completion(self):
        self.invoke();self.invoke()
        door=next(e for e in self.w.region()['entities'] if e['local_id']=='door')
        self.assertFalse(door['solid']);self.assertEqual(door['sprite'],'opened')
        before=self.w.state['player']['gold']
        for _ in range(9):self.w.action({'op':'move','dx':1,'dy':0})
        self.assertEqual(self.w.state['quests']['r0:align']['status'],'complete')
        self.assertEqual(self.w.state['player']['gold'],before+17)
        self.w.action({'op':'wait'});self.assertEqual(self.w.state['player']['gold'],before+17)
    def test_closed_door_really_blocks_movement(self):
        self.w.state['player'].update(x=11,y=10)
        self.w.action({'op':'move','dx':1,'dy':0})
        self.assertEqual(self.w.state['player']['x'],11)
    def test_history_drives_shadow_without_a_shadow_engine_primitive(self):
        for _ in range(3):self.w.action({'op':'move','dx':1,'dy':0})
        shadow=next(e for e in self.w.region()['entities'] if e['local_id']=='shadow')
        self.assertEqual((shadow['x'],shadow['y']),(5,10))
    def test_distant_actions_cannot_be_invoked(self):
        self.w.state['player'].update(x=20,y=14)
        with self.assertRaises(RuleError):self.invoke()
    def test_disabled_actions_explain_public_resources_without_puzzle_state(self):
        a=self.w.region()['program']['actions'][0]
        a['when']=expr('ge',get('player.gold'),50)
        option=Runtime(self.w,self.w.region()).available()[0]
        self.assertFalse(option['enabled']);self.assertIn('金币 ×50',option['blocked_reason'])
        self.assertIn('当前 35',option['blocked_reason'])
        a['when']=expr('eq',get('vars.presses'),17)
        option=Runtime(self.w,self.w.region()).available()[0]
        self.assertNotIn('17',option['blocked_reason']);self.assertNotIn('presses',option['blocked_reason'])
        a['blocked_hint']='先寻找控制器上的刻度线索。'
        self.assertEqual(Runtime(self.w,self.w.region()).available()[0]['blocked_reason'],a['blocked_hint'])
    def test_custom_combat_replaces_fixed_spell(self):
        self.w.state['player'].update(x=19,y=8)
        self.w.action({'op':'interact','id':'r0:foe'})
        actions=self.w.snapshot()['available_actions']
        self.assertEqual([a['label'] for a in actions],['逆向共振'])
        self.w.action({'op':'combat','move':'rule:resonate'})
        self.assertEqual(self.w.state['battle']['hp'],30)
        self.assertEqual(self.w.state['player']['mp'],21)
        self.assertEqual(self.w.state['player']['hp'],89) # authored turn-dependent opponent
        for _ in range(2):self.w.action({'op':'combat','move':'rule:resonate'})
        self.assertIsNone(self.w.state['battle'])
        self.assertTrue(self.w.state['facts']['defeated:r0:foe'])
    def test_enemy_turn_and_victory_filters_use_authored_entity_ids(self):
        r=self.w.region()
        hook=next(h for h in r['program']['hooks'] if h['id']=='foe_logic')
        hook['when']=expr('eq',get('event.target'),'foe')
        r['program']['hooks'].append({'id':'filter_win','on':'victory','target':'player','once':True,
            'when':expr('eq',get('event.target'),'foe'),
            'effects':[{'op':'set','path':'vars.won','value':True}]})
        self.w.state['player'].update(x=19,y=8)
        self.w.action({'op':'interact','id':'r0:foe'})
        self.w.action({'op':'combat','move':'rule:resonate'})
        self.assertEqual(self.w.state['player']['hp'],89)
        for _ in range(2):self.w.action({'op':'combat','move':'rule:resonate'})
        self.assertTrue(r['runtime']['vars']['won'])
    def test_nearest_interaction_reports_the_actual_object(self):
        r=self.w.region()
        r['program']['hooks'].append({'id':'observe_target','on':'interact','target':'player','once':False,'when':True,
            'effects':[{'op':'set','path':'vars.target','value':get('event.target')},
                       {'op':'set','path':'vars.canonical','value':get('event.canonical_target')}]})
        self.w.action({'op':'interact'})
        self.assertEqual(r['runtime']['vars']['target'],'lever')
        self.assertEqual(r['runtime']['vars']['canonical'],'r0:lever')
    def test_invalid_runtime_expression_rolls_back_all_effects(self):
        r=self.w.region();r['program']['actions'][0]['effects']=[
            {'op':'stat','target':'player','name':'gold','delta':20},
            {'op':'set','path':'vars.presses','value':expr('div',1,0)}]
        self.w.persist(r);before=copy.deepcopy(self.w.state);region=copy.deepcopy(r)
        with self.assertRaises(RuleError):self.invoke()
        self.assertEqual(self.w.state,before);self.assertEqual(self.w.region(),region)
        self.assertEqual(self.w.store.load_state(),before);self.assertEqual(self.w.store.load_region('r0'),region)
    def test_action_cannot_paint_player_into_wall(self):
        self.w.region()['program']['actions'][0]['effects']=[{'op':'paint','rect':[4,10,1,1],'tile':3}]
        before=copy.deepcopy(self.w.region()['tiles'])
        with self.assertRaises(InvalidPatch):self.invoke()
        self.assertEqual(self.w.region()['tiles'],before)
    def test_causal_geometry_patch_changes_current_map_and_survives_restart(self):
        patch={'kind':'reaction','reaction':{'text':'墙面在震动中打开。','paint':[{'rect':[12,5,1,1],'tile':'path'}]}}
        self.w.apply_patch(patch,self.w.context(kind='reaction'))
        self.assertEqual(self.w.region()['tiles'][5][12],1)
        restored=World(self.w.store)
        self.assertEqual(restored.region()['tiles'][5][12],1)
    def test_bad_geometry_patch_rolls_back(self):
        before=self.w.snapshot()
        with self.assertRaises(InvalidPatch):self.w.apply_patch({'kind':'reaction','reaction':{'text':'错误','paint':[{'rect':[4,10,1,1],'tile':'wall'}]}},self.w.context(kind='reaction'))
        self.assertEqual(self.w.snapshot(),before)
    def test_new_drawing_and_interaction_can_be_added_to_visited_map(self):
        art=copy.deepcopy(self.w.region()['visuals']);art['sprites']={'lens':art['sprites']['object']};art['scenery']=[];art.pop('bindings',None)
        p={'kind':'reaction','reaction':{'text':'地上长出了一只可以转动的镜头。','visuals':art,
            'spawns':[{'id':'lens_device','kind':'object','name':'镜头','sprite':'lens','at':[4,9]}],
            'program':{'vars':{'lens_turns':0},'actions':[{'id':'rotate','label':'转动镜头','target':'lens_device','effects':[{'op':'change','path':'vars.lens_turns','value':1}]}]}}}
        self.w.apply_patch(p,self.w.context(kind='reaction'));self.invoke('rotate')
        self.assertIn('lens',self.w.region()['visuals']['sprites'])
        self.assertEqual(self.w.region()['runtime']['vars']['lens_turns'],1)
    def test_installed_rules_cannot_be_silently_replaced(self):
        p={'kind':'reaction','reaction':{'text':'修改规则','program':{'actions':[{'id':'tune','label':'不同','effects':[]}]}}}
        before=self.w.snapshot()
        with self.assertRaises(RuleError):self.w.apply_patch(p,self.w.context(kind='reaction'))
        self.assertEqual(self.w.snapshot(),before)
    def test_timers_use_actions_not_polling_and_persist(self):
        p={'kind':'reaction','reaction':{'text':'一个计时机关出现。','program':{
            'vars':{'rang':False},'actions':[{'id':'start_timer','label':'启动倒计时','target':'player','once':True,'effects':[{'op':'timer','id':'alarm','after':2,'event':'signal_alarm'}]}],
            'hooks':[{'id':'alarm_ring','on':'signal_alarm','effects':[{'op':'set','path':'vars.rang','value':True}]}]}}}
        self.w.apply_patch(p,self.w.context(kind='reaction'));self.invoke('start_timer')
        for _ in range(5):self.w.snapshot()
        self.assertFalse(self.w.region()['runtime']['vars']['rang'])
        restored=World(self.w.store);restored.action({'op':'wait'})
        self.assertTrue(restored.region()['runtime']['vars']['rang'])
    def test_event_recursion_is_bounded_and_atomic(self):
        p={'kind':'reaction','reaction':{'text':'循环测试','program':{'actions':[{'id':'loop','label':'循环','effects':[{'op':'emit','event':'signal_loop'}]}],
            'hooks':[{'id':'loop','on':'signal_loop','effects':[{'op':'emit','event':'signal_loop'}]}]}}}
        self.w.apply_patch(p,self.w.context(kind='reaction'));before=self.w.snapshot()
        with self.assertRaisesRegex(RuleError,'cascade'):self.invoke('loop')
        self.assertEqual(self.w.snapshot(),before)
    def test_future_regions_can_omit_redundant_hero_recipe(self):
        target=self.w.state['topology']['r0']['children'][0];c=self.w.context(target)
        raw=authored_patch();raw['region']['visuals']['sprites'].pop('hero')
        self.w.apply_patch(raw,c)
        self.assertEqual(self.w.region(target)['visuals']['sprites']['hero'],self.w.state['hero_visual'])
    def test_design_history_enters_next_prompt(self):
        c=self.w.context();self.assertIn('偏心双厅',c['design_history'][0]['space'])
        self.assertIn('历史位置',c['design_history'][0]['gameplay'])
    def test_program_objectives_state_survives_readback(self):
        self.invoke();self.invoke()
        restored=World(self.w.store)
        self.assertEqual(restored.region()['runtime']['vars']['presses'],2)
        self.assertEqual(restored.region()['runtime']['used'],self.w.region()['runtime']['used'])
    def test_wait_and_ui_do_not_require_a_model(self):
        with patch.object(ChatProvider,'generate',side_effect=AssertionError('unexpected cloud call')):
            self.w.action({'op':'wait'});self.w.action({'op':'actions'});self.close();self.invoke()
    def test_host_code_and_paths_are_not_exposed(self):
        for p in [{'actions':[{'id':'x','label':'x','effects':[{'op':'exec','code':'bad'}]}]},
                  {'actions':[{'id':'x','label':'x','effects':[{'op':'set','path':'player.gold','value':9}]}]},
                  {'actions':[{'id':'x','label':'x','when':{'get':'__class__.__dict__'},'effects':[]}]}]:
            with self.subTest(program=p),self.assertRaises(InvalidPatch):program(p)
    def test_malformed_event_is_a_repairable_validation_error(self):
        for event in ([], {}, None, 123):
            with self.subTest(event=event), self.assertRaises(InvalidPatch):
                program({'hooks':[{'id':'test','on':event,'effects':[]}]})
    def test_legacy_solid_scenery_without_id_is_not_ignored(self):
        from engine.scene import solid_at
        r=self.w.region()
        r['props'].append({'kind':'rock','x':5,'y':10,'solid':True})
        self.assertTrue(solid_at(r,5,10))
        self.w.action({'op':'move','dx':1,'dy':0})
        self.assertEqual(self.w.state['player']['x'],4)
    def test_schema_rejects_duplicate_actions(self):
        p={'actions':[{'id':'a','label':'a','effects':[]}]*2}
        with self.assertRaises(InvalidPatch):program(p)
    def test_unknown_action_reference_rejected_before_use(self):
        p={'kind':'reaction','reaction':{'text':'错误引用','program':{'actions':[{'id':'missing','label':'操作','target':'not_here','effects':[]}]}}}
        with self.assertRaises(InvalidPatch) as caught:self.w.apply_patch(p,self.w.context(kind='reaction'))
        self.assertTrue(any(e['category']=='reference' and e['path']=='reaction.program.actions[0].target' for e in caught.exception.issues))
    def test_scene_footprints_checked(self):
        p=authored_patch();p['region']['entities'][0].update(at=[27,1],footprint=[3,3])
        w=World(Store(':memory:'));w.start('测试越界')
        try:
            with self.assertRaises(InvalidPatch):w.apply_patch(p,w.context())
            self.assertIsNone(w.region())
        finally:w.store.close()
    def test_undefined_surface_rejected(self):
        p=authored_patch();p['region']['scene']['paint'][0]['surface']='unknown'
        w=World(Store(':memory:'));w.start('测试地面')
        try:
            with self.assertRaises(InvalidPatch):w.apply_patch(p,w.context())
        finally:w.store.close()
    def test_snapshot_does_not_advance_runtime(self):
        before=copy.deepcopy(self.w.region()['runtime'])
        for _ in range(10):self.w.snapshot()
        self.assertEqual(before,self.w.region()['runtime'])
    def test_a_positive_objective_is_not_reissued_on_return(self):
        self.invoke();self.invoke()
        for _ in range(9):self.w.action({'op':'move','dx':1,'dy':0})
        before=self.w.state['player']['gold']
        from engine.gameplay import enter
        enter(self.w,self.w.region())
        self.assertEqual(self.w.state['player']['gold'],before)
    def test_online_v2_rejects_legacy_map_fallback(self):
        from test_runtime import DirectorTests
        w=World(Store(':memory:'));w.start('在线契约');d=Director(w)
        d.configure({'offline':False,'api_key':'test-only','max_calls':2});d.cfg['cooldown']=0
        def legacy(c,k,repair=''):
            raw,usage=DirectorTests.answer(c,k,repair);raw=json.loads(raw);raw['region'].pop('scene');return json.dumps(raw),usage
        try:
            with patch.object(ChatProvider,'generate',side_effect=legacy):d.step()
            self.assertIsNone(w.region());self.assertEqual(d.calls,2)
            self.assertIn('content v2',d.error)
        finally:w.store.close()

    def test_renaming_a_puzzle_does_not_fake_structural_novelty(self):
        from engine.runtime import design_record
        a=authored_patch()['region'];b=copy.deepcopy(a)
        b['name']='全新的名字';b['program']['summary']='描述不同'
        b['program']['actions'][0]['label']='名字更漂亮但还是同一个按钮'
        self.assertEqual(design_record(a)['logic'],design_record(b)['logic'])
        b['program']['actions'][0]['effects'][0]['value']=3
        self.assertNotEqual(design_record(a)['logic'],design_record(b)['logic'])
    def test_spatial_validation_enters_one_paid_repair_not_silent_fallback(self):
        w=World(Store(':memory:'));w.start('测试地图修复')
        d=Director(w);d.configure({'offline':False,'api_key':'test-only','max_calls':2});d.cfg['cooldown']=0
        seen=[]; rejected=[]
        def answer(c,k,repair=''):
            seen.append(repair);p=authored_patch()
            if not repair:
                self.assertNotIn('rejected_response',c)
                p['region']['scene']['paint'].append({'rect':[4,10,1,1],'tile':'wall'})
                rejected.append(json.dumps(p))
            else:self.assertEqual(c['rejected_response'],rejected[0])
            return json.dumps(p),{'input_tokens':1,'output_tokens':1}
        try:
            with patch.object(ChatProvider,'generate',side_effect=answer):d.step()
            self.assertEqual(d.calls,2);self.assertTrue(seen[1]);self.assertIsNotNone(w.region())
            self.assertEqual(w.region()['width'],28)
        finally:w.store.close()
    def test_drawing_error_identifies_the_recipe_layer_and_dimension(self):
        p=authored_patch()
        p['region']['visuals']['sprites']['bad_art']={'size':[16,16],'layers':[
            ['rect',0,0,16,16,'ground'],['rect',0,0,2,2,'accent'],['ellipse',2,15,4,2,'shadow']]}
        with self.assertRaisesRegex(InvalidPatch,r'bad_art.layers\[2\].height'):
            parse_patch(p,'region')
    def test_top_level_region_art_is_normalized_without_changing_content(self):
        expected=authored_patch();raw=copy.deepcopy(expected)
        raw['visuals']=raw['region'].pop('visuals')
        before=copy.deepcopy(raw)
        self.assertEqual(parse_patch(raw,'region'),parse_patch(expected,'region'))
        self.assertEqual(raw,before)
    def test_top_level_reaction_art_can_create_a_new_drawn_object(self):
        art=copy.deepcopy(self.w.region()['visuals'])
        art['sprites']={'new_lens':art['sprites']['object']};art['scenery']=[];art.pop('bindings',None)
        raw={'kind':'reaction','visuals':art,'reaction':{'text':'新镜片升起。',
            'spawns':[{'id':'new_lens','kind':'object','name':'镜片','sprite':'new_lens','at':[4,9]}]}}
        self.w.apply_patch(raw,self.w.context(kind='reaction'))
        self.assertIn('new_lens',self.w.region()['visuals']['sprites'])
        self.assertTrue(any(e.get('local_id')=='new_lens' for e in self.w.region()['entities']))
    def test_top_level_art_conflicts_and_invalid_geometry_still_fail(self):
        raw=authored_patch();raw['visuals']=copy.deepcopy(raw['region']['visuals'])
        raw['visuals']['style']='conflicting art'
        with self.assertRaisesRegex(InvalidPatch,'conflicting'):parse_patch(raw,'region')
        raw=authored_patch();raw['visuals']=raw['region'].pop('visuals')
        raw['visuals']['sprites']['bad']={'size':[16,16],'layers':[['rect',0,0,99,99,'ground']]*3}
        with self.assertRaisesRegex(InvalidPatch,'bad.layers'):parse_patch(raw,'region')
    def test_landmark_footprint_does_not_require_an_optional_id(self):
        raw=authored_patch()
        raw['region']['landmarks']=[{'type':'house','zone':'east','at':[25,5],'sprite':'building','footprint':[2,2]}]
        w=World(Store(':memory:'));w.start('地标占地验证')
        try:
            w.apply_patch(raw,w.context())
            self.assertEqual(w.region()['props'][0]['footprint'],[2,2])
        finally:w.store.close()
    def test_undefined_variable_is_rejected_during_blueprint_validation(self):
        bad={'kind':'reaction','reaction':{'text':'测试','program':{'actions':[{'id':'bad','label':'坏引用','when':get('vars.not_declared'),'effects':[]}]}}}
        with self.assertRaises(InvalidPatch):self.w.apply_patch(bad,self.w.context(kind='reaction'))


if __name__=='__main__':unittest.main()
