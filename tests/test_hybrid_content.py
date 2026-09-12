import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from hybrid_fixtures import hybrid_patch
from engine.storage import Store
from engine.world import World
from engine.schema import InvalidPatch,parse_patch
from engine.library import catalog,resolve,candidates
from engine.content_prompt import model_context

class HybridContentTests(unittest.TestCase):
    def setUp(self):
        self.w=World(Store(':memory:'));self.w.start('林间邮局',authored=True)
    def tearDown(self):self.w.store.close()
    def enter(self):self.w.apply_patch(hybrid_patch(),self.w.context())
    def test_all_shipped_library_entries_are_pinned_and_available(self):
        self.assertGreater(len(catalog()),400)
        for key in catalog():self.assertEqual(resolve(key)['sha256'],catalog()[key]['sha256'])
    def test_one_region_mixes_library_parts_original_pixels_and_modules(self):
        raw=hybrid_patch();before=copy.deepcopy(raw);self.w.apply_patch(raw,self.w.context())
        self.assertEqual(raw,before)
        r=self.w.region()
        self.assertIn('asset_hash',r['visuals']['sprites']['hero'])
        self.assertIn('parts',r['visuals']['sprites']['beacon'])
        self.assertNotIn('asset',r['visuals']['sprites']['original_glow'])
        self.assertEqual(len(r['module_sources']),2)
        self.assertTrue(any(a['id']=='duel_strike' for a in r['program']['actions']))
        self.assertIn('asset_hash',self.w.state['items']['r0:leaf_gel']['icon_visual'])
    def test_unknown_asset_wrong_hash_and_file_paths_are_rejected(self):
        for value in ({'asset':'https://example.invalid/a.png'}, {'asset':'../private'},
                      {'asset':'town_v1_grass','asset_hash':'0'*64}):
            raw=hybrid_patch();raw['region']['visuals']['sprites']['floor']=value
            with self.subTest(value=value):
                with self.assertRaises(InvalidPatch):self.w.apply_patch(raw,self.w.context())
            self.assertIsNone(self.w.region())
    def test_media_types_and_composition_bounds_are_checked(self):
        raw=hybrid_patch();raw['region']['visuals']['sprites']['floor']={'asset':'music_v1_peaceful_ville'}
        with self.assertRaises(InvalidPatch):self.w.validate_patch(raw,self.w.context())
        raw=hybrid_patch();raw['region']['visuals']['sprites']['beacon']['parts'][0]['at']=[30,30]
        with self.assertRaises(InvalidPatch):self.w.validate_patch(raw,self.w.context())
    def test_direct_library_ids_and_unary_not_normalize_without_a_model_retry(self):
        raw=hybrid_patch()
        raw['region']['items'][0]['sprite']='dungeon_v1_red_flask'
        raw['region']['scene']['paint'][0]['surface']='town_v1_grass'
        raw['region']['audio']['bindings']['move']='rpg_v1_footstep00'
        raw['region']['program']['actions'][0]['when']={'not':False}
        before=copy.deepcopy(raw)
        self.w.apply_patch(raw,self.w.context())
        self.assertEqual(raw,before)
        self.assertEqual(self.w.region()['visuals']['sprites']['town_v1_grass']['asset'],'town_v1_grass')
        self.assertIn('rpg_v1_footstep00',self.w.region()['audio']['cues'])
        self.w.action({'op':'invoke','id':'tune'})
        self.assertEqual(self.w.region()['runtime']['vars']['presses'],1)
    def test_aliases_scenery_short_frames_and_audio_options_keep_their_meaning(self):
        raw=hybrid_patch();r=raw['region']
        raw['starting_loadout']=r.pop('starting_loadout')
        r['visuals']['scenery']=['town_v1_flowers']
        r['visuals']['bindings']['living_mailbox']='object'
        r['visuals']['sprites']['original_glow']['frames']=[[['rect',1,1,3,3,'accent']]]
        r['audio']['cues']['beep']={'synth':{'wave':'sine','frequency':600,'duration':.1,'delay_ms':40}}
        self.w.apply_patch(raw,self.w.context())
        self.assertEqual(self.w.region()['audio']['cues']['beep']['delay_ms'],40)
        self.assertEqual(self.w.region()['visuals']['scenery'],['town_v1_flowers'])
        self.assertTrue(self.w.state['loadout_applied'])
    def test_module_changes_actual_door_and_combat_not_just_labels(self):
        self.enter();self.w.action({'op':'invoke','id':'switch_open'})
        door=next(e for e in self.w.region()['entities'] if e['local_id']=='door')
        self.assertFalse(door['solid']);self.assertEqual(door['sprite'],'opened')
        self.w.state['player'].update(x=19,y=8)
        self.w.action({'op':'interact','id':'r0:foe'})
        self.w.action({'op':'combat','move':'rule:duel_skill'})
        self.assertEqual(self.w.state['battle']['hp'],23)
        self.assertEqual(self.w.state['player']['mp'],21)
    def test_opening_hero_alias_is_frozen_and_missing_hero_fails_before_apply(self):
        raw=hybrid_patch();v=raw['region']['visuals']
        v['sprites']['courier']=v['sprites'].pop('hero')
        with self.assertRaises(InvalidPatch):self.w.validate_patch(raw,self.w.context())
        self.assertIsNone(self.w.region())
        v['bindings']['hero']='courier'
        self.w.apply_patch(raw,self.w.context())
        self.assertEqual(self.w.state['hero_visual']['asset'],'dungeon_v1_adventurer')
    def test_refresh_of_opening_omits_hero_and_retains_existing_identity(self):
        self.enter();hero=copy.deepcopy(self.w.state['hero_visual'])
        raw=hybrid_patch();raw['region']['visuals']['sprites'].pop('hero')
        self.w.apply_patch(raw,self.w.context())
        self.assertEqual(self.w.state['hero_visual'],hero)
        self.assertEqual(self.w.region()['visuals']['sprites']['hero'],hero)
    def test_frames_only_base_and_scored_music_cue_survive_real_application(self):
        raw=hybrid_patch();r=raw['region']
        glow=r['visuals']['sprites']['original_glow']
        glow['frames']=[glow.pop('layers')]
        r['audio']['cues']['alarm']=r['audio']['music'].pop('echo')
        r['program']['actions'][0]['effects'].append(dict(op='music',cue='alarm'))
        self.w.apply_patch(raw,self.w.context())
        self.w.action({'op':'invoke','id':'tune'})
        self.assertEqual(self.w.region()['runtime']['audio_music'],'alarm')
        self.assertEqual(self.w.region()['visuals']['sprites']['original_glow']['layers'],glow['frames'][0])
    def test_optional_trade_and_lift_expand_without_forcing_a_world_template(self):
        raw=hybrid_patch();raw['region']['modules'] += [
          dict(module='trade_v1',id='shop',args=dict(merchant='lever',item='leaf_gel',price=8,label='买敷剂')),
          dict(module='lift_v1',id='lift',args=dict(lower_control='lever',upper_control='shadow',lower=[4,10],upper=[6,12],up_label='升起',down_label='降下'))]
        self.w.apply_patch(raw,self.w.context());self.w.action({'op':'invoke','id':'shop_buy'})
        self.assertEqual(self.w.state['player']['gold'],27)
        self.assertEqual(self.w.state['player']['inventory']['r0:leaf_gel'],3)
        self.w.action({'op':'invoke','id':'lift_up'})
        self.assertEqual((self.w.state['player']['x'],self.w.state['player']['y']),(6,12))
    def test_module_namespace_collisions_and_unknown_arguments_fail(self):
        for change in ('duplicate','argument','module'):
            raw=hybrid_patch()
            if change=='duplicate':raw['region']['modules'].append(copy.deepcopy(raw['region']['modules'][0]))
            elif change=='argument':raw['region']['modules'][0]['args']['execute']='python'
            else:raw['region']['modules'][0]['module']='unknown_v1'
            with self.subTest(change=change):
                with self.assertRaises(InvalidPatch):self.w.validate_patch(raw,self.w.context())
    def test_audio_events_are_committed_once_and_rollback_with_the_action(self):
        self.enter();before=self.w.state.get('audio_seq',0)
        self.w.action({'op':'move','dx':0,'dy':1})
        self.assertEqual(self.w.state['audio_seq'],before+1)
        old=copy.deepcopy(self.w.state)
        def failed():
            self.w.queue_audio('machine');self.w.state['player']['gold']-=5
            raise ValueError('action failed')
        from engine.gameplay import transaction
        with self.assertRaises(ValueError):transaction(self.w,failed)
        self.assertEqual(self.w.state,old)
    def test_sound_definition_is_frozen_in_the_event_and_special_music_executes(self):
        self.enter();self.w.action({'op':'invoke','id':'ring_beacon'})
        emitted=copy.deepcopy(self.w.state['audio_events'][-1]['sound'])
        self.w.region()['audio']['cues']['machine']={'synth':{'wave':'noise','frequency':50,'duration':.1}}
        self.assertEqual(self.w.state['audio_events'][-1]['sound'],emitted)
        from engine.runtime import Runtime
        Runtime(self.w,self.w.region()).run([{'op':'music','cue':'echo'}])
        self.assertEqual(self.w.region()['runtime']['audio_music'],'echo')
        Runtime(self.w,self.w.region()).run([{'op':'music','cue':'default'}])
        self.assertEqual(self.w.region()['runtime']['audio_music'],'')
    def test_retrieval_is_bounded_and_never_mutates_full_context(self):
        ctx=self.w.context();original=copy.deepcopy(ctx)
        projected=model_context(ctx,'region',hybrid=True)
        selected=projected['library_candidates']
        self.assertLessEqual(len(selected['images']),32)
        self.assertLess(len(json.dumps(selected)),18000)
        self.assertEqual(ctx,original)
        self.assertNotIn('"file":',json.dumps(selected))
        self.assertNotIn('res://',json.dumps(selected))
        self.assertEqual(candidates(dict(ctx,setting='火星科幻气象站'))['images'],[])
        ids={x['id'] for x in candidates(dict(ctx,setting='森林小镇'))['images']}
        self.assertIn('town_v2_pine',ids)
        self.assertNotIn('town_v1_large_tree',ids)
    def test_saved_world_has_expanded_rules_and_pinned_assets_after_reload(self):
        self.enter()
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'world.sqlite3');store.commit(self.w.state,[self.w.region()]);store.close()
            restored=World(Store(Path(td)/'world.sqlite3'))
            try:
                with patch('engine.modules.definitions',side_effect=AssertionError('should not re-expand on load')):
                    restored.action({'op':'invoke','id':'switch_open'})
                self.assertFalse(next(e for e in restored.region()['entities'] if e['local_id']=='door')['solid'])
            finally:restored.store.close()

if __name__=='__main__':unittest.main()
