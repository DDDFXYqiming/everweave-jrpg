"""六项审查缺陷的故障注入、隔离执行和真实动作回归。"""
import copy
import json
import tempfile
import threading
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import patch

from engine.world import World
from engine.storage import Store
from engine.director import Director,ChatProvider
from engine.schema import InvalidPatch,parse_patch
from engine.runtime import Runtime,RuleError
from engine.region_pipeline import generate,contract,PipelineError
from engine.chatgpt_provider import DirectError
from engine.playability import replay,RegionEntryError
from engine.scene import solid_at,cells_for
from campaign_fixtures import chapter_patch,region_patch
from content_fixtures import authored_patch
from test_region_pipeline import components


def walk_to(world,entity):
    """通过碰撞地图找路，并逐步执行正常移动。"""
    region=world.region();p=world.state['player'];start=(p['x'],p['y'])
    cells=cells_for(entity);parents={start:None};queue=deque([start]);end=None
    while queue:
        at=queue.popleft()
        if min(abs(at[0]-x)+abs(at[1]-y) for x,y in cells)<=1:end=at;break
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            point=(at[0]+dx,at[1]+dy)
            if point in parents or not (0<=point[0]<region['width'] and 0<=point[1]<region['height']):continue
            if region['tiles'][point[1]][point[0]] in (2,3) or solid_at(region,*point):continue
            parents[point]=at;queue.append(point)
    if end is None:raise AssertionError('测试路线不可达')
    route=[]
    while parents[end] is not None:
        previous=parents[end];route.append(dict(op='move',dx=end[0]-previous[0],dy=end[1]-previous[1]));end=previous
    route.reverse()
    for action in route:world.action(action)
    return route


class EntryAndProgressTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(':memory:');self.w=World(self.store)
        self.w.start('隔离验收',authored=True,planned=True)
        self.w.apply_patch(chapter_patch(),self.w.context(kind='campaign'))
        self.w.apply_patch(region_patch(self.w,'r0'),self.w.context())
    def tearDown(self):self.store.close()
    def other_regions(self):
        for rid in ('c1_station','c1_archive'):self.w.apply_patch(region_patch(self.w,rid),self.w.context(rid))
    def bad_entry(self):
        raw=region_patch(self.w,'c1_station')
        raw['region']['program']['vars'].update(denominator=0,result=0)
        raw['region']['program']['hooks']=[dict(id='broken',on='enter',effects=[
            dict(op='set',path='vars.result',value=dict(op='div',args=[1,{'get':'vars.denominator'}]))])]
        return raw
    def test_bad_background_enter_is_rejected_without_mutating_world(self):
        before=copy.deepcopy(self.w.state)
        with self.assertRaisesRegex(InvalidPatch,'division by zero'):
            self.w.apply_patch(self.bad_entry(),self.w.context('c1_station'))
        self.assertEqual(self.w.state,before);self.assertEqual(self.store.load_state(),before)
        self.assertIsNone(self.store.load_region('c1_station'))
    def test_all_arrival_anchors_are_executed(self):
        raw=self.bad_entry()
        raw['region']['program']['hooks'][0]['effects'][0]['value']['args'][1]={'op':'sub','args':[{'get':'player.x'},2]}
        with self.assertRaisesRegex(InvalidPatch,'division by zero'):
            self.w.apply_patch(raw,self.w.context('c1_station'))
    def test_enter_effects_stay_in_probe_until_actual_arrival(self):
        raw=region_patch(self.w,'c1_station')
        raw['region']['program']['vars']={'arrivals':0}
        raw['region']['program']['hooks']=[dict(id='arrival',on='enter',effects=[dict(op='change',path='vars.arrivals',value=1)])]
        self.w.apply_patch(raw,self.w.context('c1_station'))
        self.assertEqual(self.w.region('c1_station')['runtime']['vars']['arrivals'],0)
        gate=next(e for e in self.w.region()['entities'] if e.get('target')=='c1_station')
        walk_to(self.w,gate);self.w.action(dict(op='interact',id=gate['id']))
        self.assertEqual(self.w.region()['runtime']['vars']['arrivals'],1)
    def test_legacy_ready_failure_survives_reload_and_has_working_repair(self):
        good=region_patch(self.w,'c1_station');self.w.apply_patch(good,self.w.context('c1_station'))
        raw=self.bad_entry();region=self.w.region('c1_station')
        region['program']=parse_patch(raw,'region')['region']['program'];region['runtime']['vars'].update(denominator=0,result=0)
        region['_generation_raw']=raw;self.w.persist(region)
        gate=next(e for e in self.w.region()['entities'] if e.get('target')=='c1_station')
        walk_to(self.w,gate);before=copy.deepcopy(self.w.state['player'])
        with self.assertRaises(RegionEntryError):self.w.action(dict(op='interact',id=gate['id']))
        self.assertEqual(self.w.state['current'],'r0');self.assertEqual(self.w.state['player'],before)
        self.assertFalse(self.w.state['topology']['c1_station']['ready'])
        restored=World(self.store);director=Director(restored)
        director.configure(dict(offline=False,api_key='test',base_url='https://example.test',model='test',max_calls=2));director.cfg['cooldown']=0
        self.assertEqual(director.status()['failed_tasks'][0]['target'],'c1_station')
        director.retry('c1_station','region')
        def respond(provider,ctx,kind,repair=''):
            self.assertEqual(ctx['target'],'c1_station');self.assertIn('division by zero',repair)
            self.assertIn('rejected_response',ctx)
            return good,{}
        with patch.object(ChatProvider,'generate',respond):director.step()
        self.assertTrue(restored.state['topology']['c1_station']['ready']);self.assertEqual(director.accepted,1)
        restored.action(dict(op='interact',id=gate['id']));self.assertEqual(restored.state['current'],'c1_station')
        self.assertNotIn('generation_raw',restored.snapshot()['region'])
    def test_self_locked_required_flag_is_rejected(self):
        self.other_regions();raw=region_patch(self.w,'c1_vault')
        raw['region']['program']['actions'][0]['when']={'get':'chapter.letter'}
        with self.assertRaisesRegex(InvalidPatch,'letter'):self.w.apply_patch(raw,self.w.context('c1_vault'))
    def test_flag_behind_its_own_locked_routes_is_rejected(self):
        self.other_regions();chapter=self.w.state['campaign']['chapters']['c1']
        for edge in chapter['links']:
            if 'c1_vault' in (edge['a'],edge['b']):edge['requires']=[{'flag':'letter','eq':True}]
        with self.assertRaisesRegex(InvalidPatch,'letter'):
            self.w.apply_patch(region_patch(self.w,'c1_vault'),self.w.context('c1_vault'))
    def test_key_without_producer_is_rejected(self):
        self.other_regions();self.w.state['game_spec']['systems']['inventory']=True
        raw=region_patch(self.w,'c1_vault')
        raw['region']['items']=[dict(id='key',name='钥匙',description='钥匙',kind='key',effect='attack',power=1,price=5)]
        raw['region']['program']['actions'][0]['when']={'op':'ge','args':[{'item':'key'},1]}
        with self.assertRaisesRegex(InvalidPatch,'letter'):self.w.apply_patch(raw,self.w.context('c1_vault'))
    def test_resource_bootstrap_deadlock_is_rejected_but_funding_works(self):
        self.other_regions();s=self.w.state
        s['game_spec']['resources'].append(dict(id='focus',label='专注',initial=0,max=5,display='number'));s['player']['resources']['focus']=0
        raw=region_patch(self.w,'c1_vault');raw['region']['program']['actions'][0]['costs']={'focus':1}
        with self.assertRaisesRegex(InvalidPatch,'letter'):self.w.apply_patch(raw,self.w.context('c1_vault'))
        s=self.w.state;s['player']['resources']['focus']=1
        self.assertTrue(self.w.apply_patch(raw,self.w.context('c1_vault')))
    def test_normal_chapter_has_a_real_action_completion_witness(self):
        self.other_regions();self.w.apply_patch(region_patch(self.w,'c1_vault'),self.w.context('c1_vault'))
        original=copy.deepcopy(self.w.state);route=[]
        from engine.playability import clone
        probe=clone(self.w)
        try:
            for target,flag in [('r0','clue'),('c1_station','power'),('c1_vault','letter')]:
                if probe.state['current']!=target:
                    gate=next(e for e in probe.region()['entities'] if e.get('target')==target)
                    route+=walk_to(probe,gate);action=dict(op='interact',id=gate['id']);probe.action(action);route.append(action)
                console=next(e for e in probe.region()['entities'] if e.get('local_id')=='console')
                route+=walk_to(probe,console);action=dict(op='invoke',id='set_'+flag);probe.action(action);route.append(action)
            result=replay(self.w,route,lambda w:w.state['campaign']['chapters']['c1']['complete'])
            self.assertEqual(result['status'],'verified');self.assertGreater(result['actions'],10)
            self.assertEqual(self.w.state,original)
        finally:probe.store.close()


class CostTests(unittest.TestCase):
    def setUp(self):
        self.w=World(Store(':memory:'));self.w.start('支付测试');self.w.apply_patch(authored_patch(),self.w.context())
    def tearDown(self):self.w.store.close()
    def add(self,costs=None,effects=None):
        action=dict(id='pay',label='付款',description='付款',target='player',scope='explore',once=False,when=True,
                    effects=effects or [{'op':'change','path':'vars.presses','value':1}])
        if costs is not None:action['costs']=costs
        self.w.region()['program']['actions'].append(action)
        return action
    def test_explicit_costs_disable_unaffordable_action_and_charge_once(self):
        self.add({'gold':40,'mp':2});option=next(x for x in Runtime(self.w,self.w.region()).available() if x['id']=='pay')
        self.assertFalse(option['enabled']);self.assertIn('金币',option['blocked_reason'])
        before=copy.deepcopy(self.w.state)
        with self.assertRaises(InvalidPatch):self.w.action(dict(op='invoke',id='pay'))
        self.assertEqual(self.w.state,before)
        self.w.state['player']['gold']=40;self.w.action(dict(op='invoke',id='pay'))
        self.assertEqual((self.w.state['player']['gold'],self.w.state['player']['mp']),(0,22))
        self.assertEqual(self.w.region()['runtime']['vars']['presses'],1)
    def test_legacy_missing_guard_cannot_spend_below_zero(self):
        self.w.state['player']['mp']=0
        self.add(effects=[dict(op='stat',target='player',name='mp',delta=-1),dict(op='change',path='vars.presses',value=1)])
        with self.assertRaises(InvalidPatch):self.w.action(dict(op='invoke',id='pay'))
        self.assertEqual(self.w.region()['runtime']['vars']['presses'],0)
    def test_later_conditional_payment_rolls_back_prior_effects(self):
        self.w.state['player']['mp']=0
        self.add(effects=[dict(op='change',path='vars.presses',value=1),dict(op='if',when=True,then=[dict(op='stat',target='player',name='mp',delta=-1)],**{'else':[]})])
        with self.assertRaises(InvalidPatch):self.w.action(dict(op='invoke',id='pay'))
        self.assertEqual(self.w.region()['runtime']['vars']['presses'],0)
    def test_declared_cost_rolls_back_on_effect_failure(self):
        self.add({'gold':5},[dict(op='set',path='vars.presses',value={'op':'div','args':[1,0]})])
        with self.assertRaises(InvalidPatch):self.w.action(dict(op='invoke',id='pay'))
        self.assertEqual(self.w.state['player']['gold'],35)
    def test_environmental_damage_retains_saturation(self):
        vm=Runtime(self.w,self.w.region());vm.run([dict(op='stat',target='player',name='mp',delta=-100)])
        self.assertEqual(self.w.state['player']['mp'],0)
    def test_cost_grammar_rejects_negative_and_constant_zero_division(self):
        raw=authored_patch();raw['region']['program']['actions'][0]['costs']={'mp':-1}
        with self.assertRaises(InvalidPatch):parse_patch(raw,'region')
        raw=authored_patch();raw['region']['program']['actions'][0]['when']={'op':'div','args':[1,0]}
        with self.assertRaisesRegex(InvalidPatch,'division by zero'):parse_patch(raw,'region')
    def test_undefined_cost_resource_is_rejected_before_publishing(self):
        from engine.game_spec import check_plan
        with self.assertRaisesRegex(InvalidPatch,'undefined'):
            check_plan(self.w.state,{'program':{'actions':[{'costs':{'nonexistent':1}}]}})
    def test_scene_and_item_costs_use_same_payment_and_availability(self):
        from engine.story_content import parse_scenes,show,choose
        from engine.content import item_use
        from engine.gameplay import item_availability
        r=self.w.region();scene=parse_scenes([dict(id='pay_scene',title='支付',lines=[dict(speaker='narrator',text='支付五枚金币。')],
            choices=[dict(id='yes',label='支付',costs={'gold':5},effects=[])])])[0]
        r['scenes']=[scene];vm=Runtime(self.w,r);show(vm,'pay_scene')
        self.assertTrue(self.w.state['ui']['actions'][0]['enabled'])
        self.assertIn('金币',self.w.state['ui']['actions'][0]['description'])
        from engine.gameplay import transaction
        transaction(self.w,lambda:choose(self.w,'scene:pay_scene:yes'))
        self.assertEqual(self.w.state['player']['gold'],30)
        item=dict(id='paid_tool',name='工具',kind='tool',origin='r0',use=item_use(dict(costs={'gold':31},consume=0,effects=[])))
        self.w.state['items'][item['id']]=item;self.w.state['player']['inventory'][item['id']]=1
        self.assertFalse(item_availability(self.w,item)['enabled'])
        before=self.w.state['player']['gold']
        with self.assertRaises(InvalidPatch):self.w.action(dict(op='use',id=item['id']))
        self.assertEqual(self.w.state['player']['gold'],before)


class PipelineRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.context={'destination':{'name':'回声藏书馆','description':'test'},'region_purpose':'test'}
        self.game,self.av=components(contract(self.context));self.calls=[]
        self.cfg={'hybrid_content':False,'jev_enabled':False,'_request_meta':{'kind':'region','target':'r0','call':1},
                  '_region_subrequest':lambda component:2,'_region_can_repair':lambda:True}
    def generate(self):return generate(self.context,'system',json.dumps({'world_context':self.context}),self.cfg)
    def test_successful_component_and_usage_survive_sibling_failure_and_restart(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'world.sqlite3';store=Store(path);lock=threading.Lock()
            def attach():
                self.cfg['_region_checkpoint_load']=store.components
                def save(key,component,raw):
                    with lock:store.save_component(key,component,'epoch','r0',raw)
                self.cfg['_region_checkpoint_save']=save
            attach()
            def failed(system,user,cfg):
                component=cfg['_request_meta']['component'];self.calls.append(component)
                if component=='audiovisual':raise DirectError('失败',usage={'input_tokens':11,'output_tokens':7})
                return json.dumps(self.game),{'input_tokens':100,'output_tokens':50}
            try:
                with patch('engine.chatgpt_provider.generate',side_effect=failed),self.assertRaises(DirectError) as error:self.generate()
                self.assertEqual(error.exception.usage['input_tokens'],111)
                store.close();store=Store(path);attach()
                def recover(system,user,cfg):
                    self.calls.append(cfg['_request_meta']['component']);return json.dumps(self.av),{'input_tokens':20,'output_tokens':8}
                with patch('engine.chatgpt_provider.generate',side_effect=recover):raw,usage=self.generate()
                self.assertEqual(self.calls.count('gameplay'),1);self.assertEqual(self.calls.count('audiovisual'),2)
                self.assertEqual((usage['pipeline_requests'],usage['input_tokens']),(1,20));self.assertIn('visuals',json.loads(raw)['region'])
            finally:store.close()
    def test_invalid_json_is_repaired_as_raw_text(self):
        def request(system,user,cfg):
            component=cfg['_request_meta']['component'];self.calls.append(component)
            if component=='gameplay':return json.dumps(self.game),{}
            if self.calls.count('audiovisual')==1:return '{',{}
            self.assertEqual(json.loads(user)['rejected_component_text'],'{');return json.dumps(self.av),{}
        with patch('engine.chatgpt_provider.generate',side_effect=request):raw,usage=self.generate()
        self.assertEqual(usage['pipeline_requests'],3);self.assertIn('visuals',json.loads(raw)['region'])
    def test_both_components_can_each_be_repaired_once(self):
        bad_game=copy.deepcopy(self.game);bad_game['region']['name']='错误'
        bad_av=copy.deepcopy(self.av);bad_av['audio']['music']={}
        def request(system,user,cfg):
            component=cfg['_request_meta']['component'];self.calls.append(component)
            value=(bad_game if self.calls.count(component)==1 else self.game) if component=='gameplay' else (bad_av if self.calls.count(component)==1 else self.av)
            return json.dumps(value),{}
        with patch('engine.chatgpt_provider.generate',side_effect=request):_,usage=self.generate()
        self.assertEqual(usage['pipeline_requests'],4)
    def test_missing_gameplay_audio_repairs_only_av_with_exact_cue(self):
        self.game['region']['program']['actions'][0]['effects'].append(dict(op='sound',cue='gate_open'))
        repaired=copy.deepcopy(self.av);repaired['audio']['cues']={'gate_open':{'synth':{'wave':'sine','frequency':220,'duration':.1}}}
        def request(system,user,cfg):
            component=cfg['_request_meta']['component'];self.calls.append(component)
            if component=='gameplay':return json.dumps(self.game),{}
            if self.calls.count(component)==1:return json.dumps(self.av),{}
            self.assertEqual(json.loads(user)['required_audio_references'][0]['cue'],'gate_open')
            return json.dumps(repaired),{}
        with patch('engine.chatgpt_provider.generate',side_effect=request):raw,usage=self.generate()
        self.assertEqual(self.calls.count('gameplay'),1);self.assertEqual(usage['pipeline_requests'],3)
        self.assertIn('gate_open',json.loads(raw)['region']['audio']['cues'])


class DirectorCheckpointTests(unittest.TestCase):
    def make_world(self,path):
        w=World(Store(path));w.start('持久组件续作',authored=True,planned=True)
        w.apply_patch(chapter_patch(),w.context(kind='campaign'))
        return w
    def director(self,w,budget):
        d=Director(w);d.configure(dict(provider='chatgpt_subscription',offline=False,hybrid_content=False,jev_enabled=False,max_calls=budget));d.cfg['cooldown']=0
        return d
    def parts(self,w):
        ctx=w.context();binding=contract(ctx);raw=region_patch(w,'r0');body=raw['region']
        art=body.pop('visuals');audio=body.pop('audio')
        for slot in binding['sprite_slots']+binding['surfaces']:
            if slot not in art['sprites']:art['sprites'][slot]=copy.deepcopy(art['sprites']['object'])
        for i,surface in enumerate(binding['surfaces']):body['scene']['paint'].append(dict(rect=[10+i,3,1,1],tile='ground',surface=surface))
        return raw,dict(kind='region_av',visuals=art,audio=audio)
    def test_restart_reuses_gameplay_with_one_remaining_request_and_exact_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'world.sqlite3';w=self.make_world(path);game,av=self.parts(w);d=self.director(w,2);calls=[]
            def failed(system,user,cfg):
                component=cfg['_request_meta']['component'];calls.append(component)
                if component=='audiovisual':raise DirectError('temporary',usage={'input_tokens':11,'output_tokens':7})
                return json.dumps(game),dict(input_tokens=100,output_tokens=50)
            try:
                with patch('engine.chatgpt_provider.generate',side_effect=failed):d.step()
                self.assertEqual((d.calls,d.tokens_in,d.tokens_out),(2,111,57))
                self.assertEqual(w.store.db.execute('SELECT COUNT(*) FROM generation_requests').fetchone()[0],2)
                w.store.close();w=World(Store(path));d=self.director(w,1)
                def recovered(system,user,cfg):
                    calls.append(cfg['_request_meta']['component']);return json.dumps(av),dict(input_tokens=20,output_tokens=8)
                with patch('engine.chatgpt_provider.generate',side_effect=recovered):d.step()
                self.assertEqual((d.calls,d.accepted,d.tokens_in),(1,1,20))
                self.assertEqual(calls.count('gameplay'),1)
                entries=[json.loads(row[0]) for row in w.store.db.execute('SELECT body FROM generation_requests')]
                self.assertEqual(sum(e['usage'].get('input_tokens',0) for e in entries),131)
                self.assertFalse(w.store.has_components(w.state['epoch'],'r0'))
            finally:w.store.close()
    def test_dependency_change_invalidates_completed_component(self):
        w=self.make_world(':memory:');game,av=self.parts(w);d=self.director(w,2);calls=[]
        def failed(system,user,cfg):
            component=cfg['_request_meta']['component'];calls.append(component)
            if component=='audiovisual':raise DirectError('temporary')
            return json.dumps(game),{}
        try:
            with patch('engine.chatgpt_provider.generate',side_effect=failed):d.step()
            w.state['topology']['r0']['generation_revision']=1
            d=self.director(w,2)
            def success(system,user,cfg):
                component=cfg['_request_meta']['component'];calls.append(component)
                return json.dumps(game if component=='gameplay' else av),{}
            with patch('engine.chatgpt_provider.generate',side_effect=success):d.step()
            self.assertEqual((d.calls,d.accepted),(2,1));self.assertEqual(calls.count('gameplay'),2)
        finally:w.store.close()
    def test_complete_checkpoints_can_publish_without_phantom_requests(self):
        w=self.make_world(':memory:');game,av=self.parts(w);d=self.director(w,2)
        def request(system,user,cfg):return json.dumps(game if cfg['_request_meta']['component']=='gameplay' else av),{'input_tokens':5}
        try:
            with patch('engine.chatgpt_provider.generate',side_effect=request),patch('engine.region_pipeline.assemble',side_effect=RuntimeError('模拟发布前中断')):d.step()
            self.assertEqual(d.calls,2);self.assertTrue(w.store.has_components(w.state['epoch'],'r0'))
            d=self.director(w,1)
            with patch('engine.chatgpt_provider.generate',side_effect=AssertionError('缓存恢复不应发请求')):d.step()
            self.assertEqual((d.calls,d.accepted,d.tokens_in),(0,1,0))
        finally:w.store.close()


if __name__=='__main__':unittest.main()
