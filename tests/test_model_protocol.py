"""Model-format tolerance must preserve identity, executable behavior and safety."""
import copy
import json
import unittest
from unittest.mock import patch

from content_fixtures import authored_patch, expr, get
from engine.world import World
from engine.storage import Store
from engine.schema import parse_patch, InvalidPatch
from engine.runtime import Runtime
from engine.normalization import normalize_patch
from engine.director import Director, ChatProvider, ProviderError
from test_runtime import make_world


def item(key):
    return dict(id=key,name='诊断工具',description='原来的 r1:stim 文本应当保留',kind='tool',effect='attack',power=1,price=5)


class ModelProtocolTests(unittest.TestCase):
    def setUp(self):
        self.w=World(Store(':memory:'));self.w.start('协议身份验证')
        self.w.apply_patch(authored_patch(),self.w.context())

    def tearDown(self):self.w.store.close()

    def test_qualified_new_definitions_update_all_typed_references(self):
        raw=authored_patch();r=raw['region'];program=r['program']
        r['entities'][0]['id']='r1:lever';r['entities'][0]['sprite']='r1:object'
        r['scene']['anchors']['r1:lever']=r['scene']['anchors'].pop('lever')
        r['visuals']['sprites']['r1:object']=r['visuals']['sprites'].pop('object')
        r['visuals']['bindings']={'object':'r1:object'}
        r['items']=[item('r1:stim')]
        r['entities'].append(dict(id='r1:supply',kind='chest',name='补给匣',at=[7,12],sprite='r1:object',item_id='r1:stim'))
        program['vars']={'r1:presses':0}
        program['actions'][0].update(id='r1:tune',target='r1:lever')
        program['actions'][0]['effects'][0]['path']='vars.r1:presses'
        program['actions'].append(dict(id='r1:grant',label='取得工具',target='r1:lever',once=True,
            effects=[{'op':'item','id':'r1:stim','count':1}]))
        program['hooks'][0]['id']='r1:memory_motion'
        original=copy.deepcopy(raw)
        w=World(Store(':memory:'));w.start('新定义带前缀，但身份唯一')
        try:
            w.apply_patch(raw,w.context())
            w.action({'op':'invoke','id':'grant'})
            self.assertEqual(w.state['player']['inventory']['r0:stim'],1)
            self.assertEqual(w.state['items']['r0:stim']['description'],original['region']['items'][0]['description'])
            w.action({'op':'invoke','id':'tune'})
            self.assertEqual(w.region()['runtime']['vars']['presses'],1)
            self.assertEqual(w.region()['entities'][0]['id'],'r0:lever')
            self.assertEqual(w.region()['entities'][0]['sprite'],'object')
            self.assertTrue(any(e['operation']=='reference_id' for e in w.region()['normalizations']))
            self.assertEqual(w.store.load_region('r0')['normalizations'],w.region()['normalizations'])
            self.assertEqual(raw,original)
        finally:w.store.close()

    def test_existing_cross_region_item_reference_keeps_its_identity(self):
        for region,quantity in (('r0',4),('r1',2)):
            key=region+':stim'
            self.w.state['items'][key]=dict(item(key),origin=region,local_id='stim')
            self.w.state['player']['inventory'][key]=quantity
        patch={'kind':'reaction','reaction':{'text':'一个跨地区物品的用途。','program':{
            'actions':[{'id':'use_foreign','label':'使用原物品','target':'player','effects':[{'op':'item','id':'r1:stim','count':-1}]}]}}}
        self.w.apply_patch(patch,self.w.context(kind='reaction'))
        self.w.action({'op':'invoke','id':'use_foreign'})
        self.assertEqual(self.w.state['player']['inventory']['r1:stim'],1)
        self.assertEqual(self.w.state['player']['inventory']['r0:stim'],4)

    def test_new_region_chest_and_collect_target_preserve_existing_item_identity(self):
        self.w.state['items']['r0:stim']=dict(item('r0:stim'),origin='r0',local_id='stim')
        target=self.w.state['topology']['r0']['children'][0]
        raw=authored_patch()
        raw['region']['entities'].append(dict(id='cache',kind='chest',name='旧工具匣',at=[7,12],sprite='object',item_id='r0:stim'))
        raw['region']['quests']=[dict(id='recover',name='找回旧工具',goal='collect',target='r0:stim')]
        self.w.apply_patch(raw,self.w.context(target))
        gate=next(e for e in self.w.region()['entities'] if e.get('target')==target)
        self.w.state['player'].update(x=gate['x'],y=gate['y'])
        self.w.action({'op':'interact','id':gate['id']})
        self.w.state['player'].update(x=7,y=13)
        self.w.action({'op':'interact','id':target+':cache'})
        self.assertEqual(self.w.state['player']['inventory']['r0:stim'],1)
        self.assertNotIn(target+':r0:stim',self.w.state['items'])
        self.assertEqual(self.w.state['quests'][target+':recover']['status'],'complete')

    def test_existing_identity_cannot_be_reinterpreted_as_a_new_definition(self):
        self.w.state['items']['r1:stim']=dict(item('r1:stim'),origin='r1',local_id='stim')
        self.w.state['player']['inventory']['r1:stim']=1
        before=self.w.snapshot()
        patch={'kind':'reaction','reaction':{'text':'有歧义的新物品。','items':[item('r1:stim')]}}
        with self.assertRaises(InvalidPatch) as caught:self.w.apply_patch(patch,self.w.context(kind='reaction'))
        self.assertTrue(any(i['path']=='reaction.items[0].id' and i['category']=='reference' for i in caught.exception.issues))
        self.assertEqual(self.w.snapshot(),before)

    def test_existing_quest_identity_is_not_renamed_into_a_new_quest(self):
        raw={'kind':'reaction','reaction':{'text':'错误地重新声明已有任务。','quests':[
            {'id':'r0:align','name':'原任务','goal':'talk','target':'lever'}]}}
        with self.assertRaises(InvalidPatch) as caught:self.w.validate_patch(raw,self.w.context(kind='reaction'))
        self.assertTrue(any(e['path']=='reaction.quests[0].id' for e in caught.exception.issues))

    def test_existing_region_id_is_not_silently_allocated_as_a_new_destination(self):
        raw=authored_patch();raw['region']['destinations'][0]['id']='r0'
        w=World(Store(':memory:'));w.start('不能把已有地区当成新定义')
        try:
            with self.assertRaises(InvalidPatch) as caught:w.validate_patch(raw,w.context())
            self.assertTrue(any(e['path']=='region.destinations[0].id' for e in caught.exception.issues))
        finally:w.store.close()

    def test_two_namespaces_cannot_collapse_into_one_definition(self):
        raw=authored_patch();raw['region']['items']=[item('r1:stim'),item('r2:stim')]
        with self.assertRaises(InvalidPatch) as caught:parse_patch(raw,'region')
        locations={e['path'] for e in caught.exception.issues}
        self.assertIn('region.items[0].id',locations);self.assertIn('region.items[1].id',locations)

    def test_bare_and_qualified_definition_collision_is_rejected(self):
        raw=authored_patch();raw['region']['items']=[item('stim'),item('r1:stim')]
        with self.assertRaisesRegex(InvalidPatch,'collide'):parse_patch(raw,'region')

    def test_reference_strings_in_prose_are_never_rewritten(self):
        raw=authored_patch();raw['region']['items']=[item('r1:stim')]
        raw['region']['program']['actions'][0]['description']='不要改写文字 r1:stim'
        normalized,changes,errors=normalize_patch(raw,'region')
        self.assertFalse(errors)
        self.assertEqual(normalized['region']['items'][0]['id'],'stim')
        self.assertIn('r1:stim',normalized['region']['items'][0]['description'])
        self.assertIn('r1:stim',normalized['region']['program']['actions'][0]['description'])

    def test_known_aliases_and_envelope_relocation_are_audited(self):
        raw=authored_patch();raw['visuals']=raw['region'].pop('visuals')
        raw['program']=raw['region'].pop('program')
        e=raw['region']['entities'][0];e['sprite_id']=e.pop('sprite')
        changes=[]
        normalized=parse_patch(raw,'region',corrections=changes)
        self.assertEqual(normalized,parse_patch(authored_patch(),'region'))
        self.assertEqual({c['operation'] for c in changes},{'field_location','field_alias'})

    def test_conflicting_alias_values_are_not_guessed(self):
        raw=authored_patch();raw['region']['entities'][0]['sprite_id']='enemy'
        with self.assertRaisesRegex(InvalidPatch,'conflicting'):parse_patch(raw,'region')

    def test_multiple_independent_errors_have_paths_values_and_expectations(self):
        raw=authored_patch();raw['region']['items']=[item('good'),item('also_good'),item('9bad')]
        raw['region']['entities'][0]['id']='bad-name'
        raw['region']['visuals']['sprites']['broken']={'size':[16,16],'layers':[['rect',0,0,17,1,'ground']]*3}
        with self.assertRaises(InvalidPatch) as caught:parse_patch(raw,'region')
        issues=caught.exception.issues
        bad=next(i for i in issues if i['path']=='region.items[2].id')
        self.assertEqual(bad['value'],'9bad');self.assertIn('expected',bad)
        self.assertTrue(any('entities[0].id' in i['path'] for i in issues))
        self.assertTrue(any('visuals.sprites.broken.layers[0].width' in i['path'] for i in issues))

    def test_descriptive_style_does_not_hide_an_unrelated_sprite_error(self):
        raw=authored_patch();raw['region']['visuals']['style']='有完整视觉细节的风格说明。'*8
        self.assertGreater(len(raw['region']['visuals']['style']),80)
        parse_patch(raw,'region')
        raw['region']['entities'][0]['sprite']='missing_art'
        with self.assertRaises(InvalidPatch) as caught:parse_patch(raw,'region')
        self.assertEqual(caught.exception.issues[0]['path'],'region.entities[0].sprite')
        self.assertEqual(caught.exception.issues[0]['value'],'missing_art')

    def test_typed_field_failures_identify_item_and_entity_fields(self):
        raw=authored_patch();raw['region']['items']=[item('a'),item('b')]
        raw['region']['items'][1]['power']='not a number'
        raw['region']['entities'][0]['kind']='unsupported_kind'
        with self.assertRaises(InvalidPatch) as caught:parse_patch(raw,'region')
        paths={entry['path'] for entry in caught.exception.issues}
        self.assertIn('region.items[1].power',paths)
        self.assertIn('region.entities[0].kind',paths)

    def test_format_errors_do_not_hide_independent_missing_item_definitions(self):
        raw=authored_patch()
        raw['region']['entities'][0]['unknown_field']=True
        raw['region']['program']['actions'][0]['effects']=[{'op':'item','id':'not_defined','count':1}]
        w=World(Store(':memory:'));w.start('格式与引用同时检查')
        try:
            with self.assertRaises(InvalidPatch) as caught:w.validate_patch(raw,w.context())
            paths={entry['path'] for entry in caught.exception.issues}
            self.assertIn('region.entities[0].unknown_field',paths)
            self.assertIn('region.program.actions[0].effects[0].id',paths)
        finally:w.store.close()

    def test_animation_errors_keep_the_frame_and_layer_path(self):
        raw=authored_patch()
        raw['region']['visuals']['sprites']['npc']['frames'][1][0][3]=999
        with self.assertRaises(InvalidPatch) as caught:parse_patch(raw,'region')
        self.assertTrue(any(entry['path']=='region.visuals.sprites.npc.frames[1].layers[0].width' for entry in caught.exception.issues))

    def test_reaction_new_item_program_resolves_the_registered_item(self):
        patch={'kind':'reaction','reaction':{'text':'新工具与其操作一起进入世界。','items':[item('r1:stim')],
            'program':{'actions':[{'id':'r1:claim_stim','label':'取得新工具','target':'player','once':True,
                'effects':[{'op':'item','id':'r1:stim','count':1}]}]}}}
        self.w.apply_patch(patch,self.w.context(kind='reaction'))
        self.w.action({'op':'invoke','id':'claim_stim'})
        matches=[key for key,i in self.w.state['items'].items() if i.get('local_id')=='stim']
        self.assertEqual(len(matches),1)
        self.assertEqual(self.w.state['player']['inventory'][matches[0]],1)
        self.assertEqual(Runtime(self.w,self.w.region()).item_id('stim'),matches[0])

    def test_reference_validation_reports_multiple_missing_references(self):
        raw=authored_patch();raw['region']['program']['actions'][0]['effects']=[
            {'op':'item','id':'missing_item','count':1},
            {'op':'sprite','target':'missing_object','value':'missing_sprite'}]
        w=World(Store(':memory:'));w.start('多处悬空引用')
        try:
            with self.assertRaises(InvalidPatch) as caught:w.validate_patch(raw,w.context())
            issues=caught.exception.issues
            self.assertGreaterEqual(len(issues),3)
            self.assertTrue(all(i['category']=='reference' for i in issues))
            self.assertTrue(any(i['path']=='region.program.actions[0].effects[0].id' for i in issues))
        finally:w.store.close()


class DirectorDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.w=World(Store(':memory:'));self.w.start('导演诊断验证')
        self.d=Director(self.w)
        self.d.configure(dict(offline=False,api_key='test-only',max_calls=12))
        self.d.cfg['cooldown']=0
    def tearDown(self):self.w.store.close()

    def test_partial_retry_selector_is_rejected(self):
        with self.assertRaises(ProviderError):self.d.retry(kind='region')
        with self.assertRaises(ProviderError):self.d.retry(target='r0')

    def test_stale_failure_does_not_pollute_the_new_world_failure_list(self):
        def answer(provider,ctx,kind,repair=''):
            self.w.start('已经开始的新世界')
            raise ProviderError('late failure from previous world')
        with patch.object(ChatProvider,'generate',answer):self.d.step()
        self.assertEqual(self.d.status()['failed_tasks'],[])
        self.assertEqual(self.d.stale,1)
        self.assertEqual(self.d.error,'')

    def test_changed_story_does_not_spend_a_repair_on_stale_invalid_json(self):
        def answer(provider,ctx,kind,repair=''):
            self.w.state['story_revision']+=1
            return 'invalid JSON',{'input_tokens':1,'output_tokens':1}
        with patch.object(ChatProvider,'generate',answer) as model:self.d.step()
        self.assertEqual(self.d.calls,1)
        self.assertEqual(self.d.repair_calls,0)
        self.assertEqual(self.d.stale,1)
        self.assertFalse(self.d.failed)

    def test_entered_draft_failure_is_classified_as_stale(self):
        self.w.apply_patch(authored_patch(),self.w.context())
        target=self.w.state['topology']['r0']['children'][0]
        def answer(provider,ctx,kind,repair=''):
            # A different response/readied draft was entered while this one ran.
            self.w.state['topology'][target].update(ready=True,visited=True)
            raise ProviderError('outdated refresh failure')
        with patch.object(ChatProvider,'generate',answer):self.d.step()
        self.assertEqual(self.d.stale,1)
        self.assertFalse(self.d.failed)

    def test_local_id_and_envelope_correction_needs_no_model_repair(self):
        raw=authored_patch();raw['visuals']=raw['region'].pop('visuals')
        raw['region']['entities'][0]['id']='r1:lever'
        with patch.object(ChatProvider,'generate',return_value=(json.dumps(raw),{'input_tokens':10,'output_tokens':20})) as model:
            self.d.step()
        self.assertEqual(model.call_count,1)
        status=self.d.status()
        self.assertEqual((status['accepted'],status['repair_calls']),(1,0))
        self.assertGreater(status['normalization_count'],0)
        self.assertEqual(status['failed_tasks'],[])
        self.assertTrue(self.w.region()['normalizations'])

    def test_repair_receives_multiple_field_errors_and_original_response(self):
        bad=authored_patch();bad['region']['items']=[item('9bad')]
        bad['region']['entities'][0]['id']='not-valid'
        raw=json.dumps(bad);seen=[]
        def answer(provider,ctx,kind,repair=''):
            seen.append((copy.deepcopy(ctx),repair))
            return (raw if not repair else json.dumps(authored_patch())),{'input_tokens':10,'output_tokens':20}
        with patch.object(ChatProvider,'generate',answer):self.d.step()
        self.assertEqual(len(seen),2)
        report=json.loads(seen[1][1])
        self.assertGreaterEqual(len(report['errors']),2)
        self.assertEqual(seen[1][0]['rejected_response'],raw)
        self.assertEqual(self.d.repair_calls,1);self.assertEqual(self.d.accepted,1)

    def test_targeted_retry_preserves_other_failure_and_successful_map(self):
        root=authored_patch()
        root['region']['destinations'].append({'id':'second','name':'第二条路','description':'另一条路'})
        root['region']['scene']['anchors']['forward_1']=[26,16]
        self.w.apply_patch(root,self.w.context())
        ready=copy.deepcopy(self.w.region())
        targets=list(self.w.state['topology']['r0']['children'])
        def bad(provider,ctx,kind,repair=''):
            raw=authored_patch();raw['region']['entities'][0]['at']=[99,99]
            return json.dumps(raw),{'input_tokens':1,'output_tokens':1}
        with patch.object(ChatProvider,'generate',bad):
            self.d.step();self.d.step()
            self.assertFalse(self.d.step())
        self.assertEqual(len(self.d.status()['failed_tasks']),2)
        self.assertTrue(all(f['target'] in targets and f['name'] for f in self.d.status()['failed_tasks']))
        self.d.retry(targets[0],'region')
        seen=[]
        def fixed(provider,ctx,kind,repair=''):
            seen.append(ctx)
            return json.dumps(authored_patch()),{'input_tokens':1,'output_tokens':1}
        with patch.object(ChatProvider,'generate',fixed):self.d.step()
        self.assertEqual(len(seen),1);self.assertEqual(seen[0]['target'],targets[0])
        self.assertIn('rejected_response',seen[0])
        self.assertEqual(self.d.failed,{('region',targets[1])})
        self.assertEqual(self.w.region('r0'),ready)
        self.assertTrue(self.w.state['topology'][targets[0]]['ready'])

    def test_semantic_reaction_error_enters_one_repair_before_commit(self):
        w,d=make_world()
        try:
            event,_=w.story('choice','检查新出现的装置');w.persist(event=event)
            d.configure(dict(offline=False,api_key='test-only',max_calls=2));d.cfg['cooldown']=0
            before=w.state['player']['gold'];reports=[]
            def answer(provider,ctx,kind,repair=''):
                reports.append(repair)
                effect={'op':'item','id':'unknown_item','count':1} if not repair else {'op':'stat','target':'player','name':'gold','delta':3}
                return json.dumps({'kind':'reaction','reaction':{'text':'一个可操作装置。','program':{
                    'actions':[{'id':'use_device','label':'使用装置','effects':[effect]}]}}}),{'input_tokens':1,'output_tokens':1}
            with patch.object(ChatProvider,'generate',answer):d.step()
            self.assertEqual(d.calls,2);self.assertEqual(d.repair_calls,1)
            self.assertIn('unknown_item',reports[1])
            self.assertEqual(w.state['player']['gold'],before)
            w.action({'op':'invoke','id':'use_device'})
            self.assertEqual(w.state['player']['gold'],before+3)
        finally:w.store.close()


if __name__=='__main__':unittest.main()
