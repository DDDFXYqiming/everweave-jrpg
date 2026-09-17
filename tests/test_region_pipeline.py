"""The split pipeline shares one identity contract and really overlaps its workers."""
import copy
import json
import threading
import unittest
from unittest.mock import patch

from adventure_fixtures import adventure_plan,authored_adventure_region
from content_fixtures import authored_patch
from engine.director import Director
from engine.region_pipeline import PipelineError,assemble,contract,generate,worker_contexts
from engine.schema import parse_patch
from engine.storage import Store
from engine.world import World


def components(binding):
    game=authored_patch();region=game['region'];visuals=copy.deepcopy(region.pop('visuals'));audio=copy.deepcopy(region.pop('audio'))
    region['entities'][0]['sprite']='object';region['entities'][1]['sprite']='npc';region['entities'][2]['sprite']='focal';region['entities'][3]['sprite']='enemy'
    region['program']['hooks'][1]['effects'][1]['value']='object'
    for index,surface in enumerate(binding['surfaces']):
        visuals['sprites'][surface]=copy.deepcopy(visuals['sprites']['floor'])
        region['scene']['paint'].append({'rect':[18+index,2,1,1],'tile':'ground','surface':surface})
    visuals['sprites']['focal']=copy.deepcopy(visuals['sprites']['object']);visuals['sprites']['item']=copy.deepcopy(visuals['sprites']['object'])
    visuals.setdefault('bindings',{})
    for slot in binding['sprite_slots']:
        if slot not in visuals['sprites']:visuals['bindings'][slot]='object'
    audiovisual={'kind':'region_av','visuals':visuals,'audio':audio}
    return game,audiovisual


class RegionPipelineTests(unittest.TestCase):
    def test_worker_projection_preserves_modules_and_visual_identity_for_the_right_owner(self):
        world={'setting':'test','visual_identity':{'style':'ink','terrain':'metal','palette':{'base':'#111111'}},
               'library_candidates':{'profile':'sci_fi','images':[{'id':'image'}],'audio':[{'id':'sound'}],
                                     'materials':[{'id':'metal'}],'modules':[{'id':'trade_v1'}]}}
        binding=contract({'destination':{'name':'站台','description':'test'},'region_purpose':'test','hero_visual':{}})
        gameplay,audiovisual,_=worker_contexts(json.dumps({'world_context':world}),binding)
        game_world=json.loads(gameplay)['world_context'];av_world=json.loads(audiovisual)['world_context']
        self.assertEqual(game_world['library_candidates']['modules'],[{'id':'trade_v1'}])
        self.assertNotIn('images',game_world['library_candidates'])
        self.assertEqual(av_world['visual_identity']['terrain'],'metal')
        self.assertEqual(av_world['library_candidates']['images'],[{'id':'image'}])

    def test_slot_briefs_are_derived_without_an_extra_design_request(self):
        binding=contract({'destination':{'name':'档案站','description':'保存失踪人员记忆的档案终端'},'region_purpose':'调查档案'})
        self.assertEqual(binding['slot_briefs']['focal']['identity'],'保存失踪人员记忆的档案终端')
        self.assertIn('ground_surface',binding['slot_briefs']);self.assertIn('hero',binding['slot_briefs'])

    def test_workers_overlap_and_merge_without_duplicate_placeholder_art(self):
        context={'destination':{'name':'回声藏书馆','description':'test'},'region_purpose':'test','game_spec':{'visual_theme':'clockwork'}}
        binding=contract(context);game,audiovisual=components(binding);entered=threading.Event();lock=threading.Lock();branches=[];reserved=[]
        def request(system,user,cfg):
            with lock:
                branches.append(cfg['_request_meta']['component'])
                if len(branches)==2:entered.set()
            if not entered.wait(2):raise AssertionError('component workers did not overlap')
            value=game if cfg['_request_meta']['component']=='gameplay' else audiovisual
            return json.dumps(value),{'input_tokens':20,'output_tokens':7,'reasoning_tokens':3,'reasoning_observed':True}
        cfg={'hybrid_content':False,'_request_meta':{'kind':'region','target':'r0','call':1},'_region_subrequest':lambda component:reserved.append(component) or 2}
        with patch('engine.chatgpt_provider.generate',side_effect=request):raw,usage=generate(context,'region system',json.dumps({'world_context':context}),cfg)
        result=json.loads(raw)
        self.assertEqual(set(branches),{'gameplay','audiovisual'});self.assertEqual(reserved,['audiovisual'])
        self.assertEqual(result['region']['visuals']['sprites'],audiovisual['visuals']['sprites'])
        self.assertIn('explore',result['region']['audio']['music']);self.assertNotIn('audio',game['region']);self.assertNotIn('visuals',game['region'])
        self.assertEqual((usage['pipeline_requests'],usage['input_tokens'],usage['output_tokens'],usage['reasoning_tokens']),(2,40,14,6))

    def test_jev_asset_selection_waits_only_in_the_audiovisual_branch(self):
        context={'destination':{'name':'回声藏书馆','description':'test'},'region_purpose':'test','game_spec':{'visual_theme':'clockwork'}}
        binding=contract(context);game,audiovisual=components(binding);gameplay_started=threading.Event();events=[]
        def request(system,user,cfg):
            component=cfg['_request_meta']['component']
            if component=='gameplay':gameplay_started.set()
            value=game if component=='gameplay' else audiovisual
            return json.dumps(value),{}
        def rank_assets(region_context,region_design,fallback,cancel_event):
            self.assertTrue(gameplay_started.wait(2),'gameplay must start before semantic asset selection finishes')
            return fallback,{'status':'ranked','requests':1,'usage':{'input_tokens':10,'output_tokens':2},'gaps':[]}
        cfg={'hybrid_content':True,'jev_enabled':True,'_request_meta':{'kind':'region','target':'r0','call':1},
             '_region_subrequest':lambda component:2,'_jev_event':lambda stage,report:events.append((stage,report['status']))}
        with patch('engine.chatgpt_provider.generate',side_effect=request),patch('engine.jev_judgments.rank_assets',side_effect=rank_assets):
            raw,_=generate(context,'region system',json.dumps({'world_context':context}),cfg)
        self.assertEqual(events,[('asset_selection','ranked')]);self.assertIn('visuals',json.loads(raw)['region'])

    def test_only_failed_audiovisual_component_is_repaired(self):
        context={'destination':{'name':'回声藏书馆','description':'test'},'region_purpose':'test','hero_visual':{}}
        binding=contract(context);game,audiovisual=components(binding);bad=copy.deepcopy(audiovisual);bad['audio']['music']={}
        av_calls=[];reserved=[]
        def request(system,user,cfg):
            component=cfg['_request_meta']['component']
            if component=='gameplay':return json.dumps(game),{}
            av_calls.append(1);return json.dumps(bad if len(av_calls)==1 else audiovisual),{}
        cfg={'hybrid_content':False,'_request_meta':{'kind':'region','target':'r0','call':1},
             '_region_subrequest':lambda component:reserved.append(component) or len(reserved)+1,'_region_can_repair':lambda:True}
        with patch('engine.chatgpt_provider.generate',side_effect=request):raw,usage=generate(context,'region system',json.dumps({'world_context':context}),cfg)
        self.assertEqual((len(av_calls),reserved,usage['pipeline_requests']),(2,['audiovisual','audiovisual'],3))
        self.assertIn('explore',json.loads(raw)['region']['audio']['music'])

    def test_binding_or_surface_drift_is_rejected_before_world_validation(self):
        binding=contract({'destination':{'name':'回声藏书馆','description':'test'},'region_purpose':'test','hero_visual':{}})
        game,audiovisual=components(binding);game['region']['entities'][0]['sprite']='outside_contract'
        with self.assertRaises(PipelineError):assemble(game,audiovisual,binding,{})
        game,_=components(binding);missing=binding['surfaces'][-1];game['region']['scene']['paint']=[p for p in game['region']['scene']['paint'] if p.get('surface')!=missing]
        with self.assertRaises(PipelineError):assemble(game,audiovisual,binding,{})

    def test_audio_fields_misnested_under_music_are_unambiguously_hoisted(self):
        binding=contract({'destination':{'name':'回声藏书馆','description':'test'},'region_purpose':'test','hero_visual':{}})
        game,audiovisual=components(binding);audio=audiovisual['audio'];audio['music']['cues']={'click':{'synth':{'wave':'sine','frequency':220,'duration':.1}}};audio['music']['bindings']={'ui':'click'}
        raw=json.loads(assemble(game,audiovisual,binding,{}));self.assertEqual(raw['region']['audio']['bindings']['ui'],'click')

    def test_material_is_validated_in_component_but_expanded_only_once(self):
        binding=contract({'destination':{'name':'回声藏书馆','description':'test'},'region_purpose':'test','hero_visual':{}})
        game,audiovisual=components(binding);audiovisual['visuals']['sprites']['ground_surface']={'material':'wood_planks_v1'}
        raw=assemble(game,audiovisual,binding,{})
        self.assertEqual(json.loads(raw)['region']['visuals']['sprites']['ground_surface'],{'material':'wood_planks_v1'})
        parsed=parse_patch(raw,'region');self.assertEqual(parsed['region']['visuals']['sprites']['ground_surface']['material'],'wood_planks_v1')

    def test_boolean_object_state_written_true_gets_a_recorded_false_default(self):
        raw=authored_patch();lever=raw['region']['entities'][0];lever.pop('state')
        action=raw['region']['program']['actions'][0]
        action['when']={'op':'not','args':[{'get':'objects.lever.state.ready'}]}
        action['effects']=[{'op':'set','path':'objects.lever.state.ready','value':True}]
        corrections=[];parsed=parse_patch(raw,'region',corrections=corrections)
        self.assertFalse(parsed['region']['entities'][0]['state']['ready'])
        self.assertTrue(any(c['operation']=='boolean_state_default' for c in corrections))


class DirectorPipelineTests(unittest.TestCase):
    def setUp(self):
        self.world=World(Store(':memory:'));self.world.start('调查与同行',authored=True,planned=True)
        self.world.apply_patch(adventure_plan(),self.world.context(kind='campaign'))
    def tearDown(self):self.world.store.close()

    def test_two_actual_requests_are_counted_as_one_accepted_region(self):
        director=Director(self.world);director.configure({'provider':'chatgpt_subscription','offline':False,'max_calls':2});director.cfg['cooldown']=0
        def pipeline(context,system,user,cfg):
            cfg['_region_subrequest']('audiovisual')
            return json.dumps(authored_adventure_region(self.world,context['target'])),{'input_tokens':30,'output_tokens':20,'pipeline_requests':2}
        with patch('engine.region_pipeline.generate',side_effect=pipeline):self.assertTrue(director.step())
        self.assertEqual((director.calls,director.accepted,director.tokens_in,director.tokens_out),(2,1,30,20))
        self.assertEqual(director.task_history[-1]['status'],'ready')

    def test_insufficient_budget_uses_the_original_single_request(self):
        director=Director(self.world);director.configure({'provider':'chatgpt_subscription','offline':False,'max_calls':1});director.cfg['cooldown']=0
        raw=json.dumps(authored_adventure_region(self.world,'r0'))
        with patch('engine.chatgpt_provider.generate',return_value=(raw,{})) as direct,patch('engine.region_pipeline.generate',side_effect=AssertionError('must not split')):
            self.assertTrue(director.step())
        self.assertEqual((director.calls,director.accepted,direct.call_count),(1,1,1))

    def test_semantic_review_is_separately_metered_and_does_not_block_delivery(self):
        director=Director(self.world);director.configure({'provider':'chatgpt_subscription','offline':False,'max_calls':2,'jev_enabled':True});director.cfg['cooldown']=0
        def pipeline(context,system,user,cfg):
            cfg['_region_subrequest']('audiovisual')
            return json.dumps(authored_adventure_region(self.world,context['target'])),{'input_tokens':30,'output_tokens':20,'pipeline_requests':2}
        report={'status':'reviewed','requests':1,'model':'jev-1.13.0','usage':{'input_tokens':80,'output_tokens':12},
                'concerns':[{'path':'region.program.actions[0]','verdict':'insufficient'}]}
        with patch('engine.region_pipeline.generate',side_effect=pipeline),patch('engine.semantic_review.review',return_value=report):
            self.assertTrue(director.step())
        self.assertEqual((director.calls,director.accepted),(2,1))
        self.assertEqual((director.jev_requests,director.jev_tokens_in,director.jev_tokens_out,director.jev_concerns),(1,80,12,1))
        self.assertEqual(director.status()['jev_reports'][-1]['stage'],'content_review')

    def test_cached_jev_result_does_not_double_count_tokens(self):
        director=Director(self.world);ctx={'kind':'region','target':'r0'};job=('epoch','region','r0')
        director._record_jev('asset_selection',{'status':'ranked','requests':1,'usage':{'input_tokens':80,'output_tokens':12}},ctx,job)
        director._record_jev('asset_selection',{'status':'ranked','requests':0,'cached':True,'usage':{'input_tokens':80,'output_tokens':12}},ctx,job)
        self.assertEqual((director.jev_requests,director.jev_tokens_in,director.jev_tokens_out),(1,80,12))


if __name__=='__main__':unittest.main()
