import copy
import unittest
from unittest.mock import patch

from engine import jev_judgments
from engine.library import candidate_pool,candidates
from engine.semantic_review import evidence


class JevAssetTests(unittest.TestCase):
    def test_slot_choice_keeps_only_known_assets_and_allows_original_gap(self):
        context={'setting':'太空轨道气象站','destination':{'name':'云层观测站','description':'用终端读取风暴档案'}}
        fallback=candidates(context);pool=candidate_pool(context)
        object_id=next(v['id'] for v in pool['images'] if 'object' in v['roles'])
        design={'name':'云层观测站','description':'用终端读取风暴档案','visual_direction':'industrial science fiction',
                'slot_briefs':{'focal':{'identity':'档案终端'},'enemy':{'identity':'风暴防卫体'}}}
        def response(version,state,questions,cancel_event=None):
            answers={}
            for key,question in questions.items():
                options=list(question.criteria)
                choice=object_id if object_id in options else 'draw_original'
                answers[key]={'choice':choice,'confidence':.9,'probabilities':{option:(.9 if option==choice else .1/(len(options)-1)) for option in options}}
            return {'model':'jev-1.13.0','answers':answers,'usage':{'input_tokens':120,'output_tokens':20},'cached':False}
        with patch.object(jev_judgments,'capability',return_value={'ready':True}),patch.object(jev_judgments,'_request',side_effect=response):
            ranked,report=jev_judgments.rank_assets(context,design,fallback)
        self.assertEqual(report['status'],'ranked');self.assertEqual(report['requests'],1)
        self.assertEqual(ranked['audio'],fallback['audio']);self.assertEqual(ranked['modules'],fallback['modules'])
        self.assertIn('enemy',ranked['semantic_selection']['gaps'])
        self.assertTrue(any(v['id']==object_id and v['recommended_for']=='focal' for v in ranked['images']))
        self.assertTrue(all(v['id'] in {x['id'] for x in pool['images']} for v in ranked['images']))

    def test_missing_service_is_an_explicit_fallback_not_a_pass(self):
        fallback={'images':[{'id':'safe'}],'audio':[]}
        with patch.object(jev_judgments,'capability',return_value={'ready':False,'reason':'missing_api_key'}):
            ranked,report=jev_judgments.rank_assets({}, {'slot_briefs':{}}, fallback)
        self.assertEqual(ranked,fallback);self.assertEqual(report['status'],'unavailable');self.assertEqual(report['requests'],0)

    def test_service_error_keeps_the_original_catalog(self):
        context={'setting':'太空站','destination':{'name':'站台','description':'终端'}};fallback=candidates(context)
        design={'slot_briefs':{'focal':{'identity':'终端'}}}
        with patch.object(jev_judgments,'capability',return_value={'ready':True}),patch.object(jev_judgments,'_request',side_effect=TimeoutError('temporary')):
            ranked,report=jev_judgments.rank_assets(context,design,fallback)
        self.assertEqual(ranked,fallback);self.assertEqual(report['status'],'error');self.assertEqual(report['reason'],'TimeoutError')


class JevSemanticTests(unittest.TestCase):
    def test_evidence_covers_actions_story_choices_and_npc_choices(self):
        region={'program':{'actions':[{'id':'pay','label':'交出一张票','description':'通过闸门','blocked_hint':'需要一张票','target':'gate','scope':'explore','when':{'item':'ticket'},'effects':[{'op':'item','id':'ticket','count':-1},{'op':'scene','id':'archive'}]}],
                           'hooks':[{'id':'open','on':'invoke','target':'player','when':True,'effects':[{'op':'set','path':'vars.open','value':True}],'once':True}],
                           'objectives':[{'id':'leave','name':'离站','description':'离站','when':{'get':'vars.open'},'fail_when':False,'reward':[]} ]},
                'items':[{'id':'ticket','name':'通行票','kind':'key','description':'一次通行'}],
                'entities':[{'id':'clerk','name':'站务员','kind':'npc','dialogue':['风暴将至。'],'choices':[{'id':'ask','text':'询问出口','reply':'闸门在北边。','tag':'asked'}]}],
                'scenes':[{'id':'archive','title':'档案','lines':['记录仍可读取。'],'choices':[{'id':'erase','label':'删除记录','when':True,'effects':[{'op':'set','path':'vars.erased','value':True}]}]}]}
        result=evidence({'region':region},{'target':'r_test'});kinds={v['kind'] for v in result['units']}
        self.assertEqual(kinds,{'action','scene_choice','npc_choice'})
        action=next(v for v in result['units'] if v['kind']=='action')
        self.assertEqual(action['path'],'region.program.actions[0]');self.assertEqual(action['triggered_hooks'][0]['id'],'open')
        self.assertEqual(action['referenced_scenes'][0]['id'],'archive');self.assertEqual(action['execution_context']['target'],'gate')
        npc=next(v for v in result['units'] if v['kind']=='npc_choice')
        self.assertEqual(npc['direct_effects'][0]['value'],'asked')

    def test_review_returns_located_concern_and_uncertain_item(self):
        state={'region_id':'r_test','units':[
            {'content_id':'pay','path':'region.program.actions[0]','kind':'action','player_text':{'label':'交一张票'},'blocked_hint':'需要一张票','when':{'item':'ticket'},'direct_effects':[{'op':'item','id':'ticket','count':-2}],'triggered_hooks':[],'objectives':[],'definitions':[]},
        ]}
        def response(version,payload,questions,cancel_event=None):
            answers={key:{'choice':('contradicted' if key.startswith('effect') else 'insufficient'),'confidence':.8,
                          'probabilities':{'consistent':.1,'contradicted':.8 if key.startswith('effect') else .1,'insufficient':.1 if key.startswith('effect') else .8}}
                     for key in questions}
            return {'model':'jev-1.13.0','answers':answers,'usage':{'input_tokens':90,'output_tokens':18},'cached':False}
        with patch.object(jev_judgments,'capability',return_value={'ready':True}),patch.object(jev_judgments,'_request',side_effect=response):
            report=jev_judgments.review_semantics(state)
        self.assertEqual(report['status'],'reviewed');self.assertEqual(len(report['concerns']),2)
        self.assertTrue(all(v['path']=='region.program.actions[0]' for v in report['concerns']))
        self.assertEqual({v['verdict'] for v in report['concerns']},{'contradicted','insufficient'})


if __name__=='__main__':unittest.main()
