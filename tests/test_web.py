"""Web 包装层的同源边界、玩家投影与正常动作检查。"""
import http.client
import json
import threading
import unittest
from unittest.mock import patch
from engine.web_server import WebGameServer
from content_fixtures import authored_patch


class WebTests(unittest.TestCase):
    def setUp(self):
        self.server=WebGameServer(('127.0.0.1',0),':memory:','test-token')
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        self.headers={'Origin':self.origin,'Sec-Fetch-Site':'same-origin','X-Everweave-Web':'1','Cookie':self.server.cookie_name+'=test-token'}
    def tearDown(self):
        self.server.shutdown();self.worker.join();self.server.server_close();self.server.world.store.close()
    def request(self,path='/',method='GET',data=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        h=dict(headers or {})
        if data is not None:h['Content-Type']='application/json'
        conn.request(method,path,json.dumps(data) if data is not None else None,h)
        response=conn.getresponse();result=(response.status,dict(response.getheaders()),response.read());conn.close();return result
    def test_root_sets_http_only_cookie_and_blocks_cross_site_embedding(self):
        status,headers,body=self.request()
        self.assertEqual(status,200);self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy']);self.assertIn(b'/app.js',body)
        self.assertEqual(self.request(headers={'Sec-Fetch-Site':'cross-site'})[0],403)
    def test_api_requires_cookie_and_same_origin_header(self):
        self.assertEqual(self.request('/state')[0],401)
        self.assertEqual(self.request('/state',headers=self.headers)[0],200)
        for change in ({'Origin':'https://evil.example'},{'X-Everweave-Web':''},{'Cookie':'wrong=token'}):
            self.assertEqual(self.request('/state',headers={**self.headers,**change})[0],401)
    def test_browser_and_native_bearer_can_use_normal_actions(self):
        w=self.server.world;w.start('Web 动作验证');w.apply_patch(authored_patch(),w.context())
        before=w.state['steps'];status,_,body=self.request('/action','POST',{'op':'move','dx':0,'dy':1},self.headers)
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['player']['y'],11);self.assertEqual(w.state['steps'],before+1)
        self.assertEqual(self.request('/state',headers={'Authorization':'Bearer test-token'})[0],200)
    def test_projection_omits_rules_future_scenes_and_mutable_object_secrets(self):
        w=self.server.world;w.start('Web 玩家投影');w.apply_patch(authored_patch(),w.context())
        snapshot=json.loads(self.request('/state',headers=self.headers)[2]);region=snapshot['region']
        for key in ('program','scenes','runtime','plan','generation_raw'):self.assertNotIn(key,region)
        self.assertTrue(all('state' not in e and 'dialogue' not in e for e in region['entities']))
        self.assertTrue(region['visuals']);self.assertTrue(region['tiles'])
        w.state['items']['potion']['use']={'label':'使用','when':True,'consume':1,'effects':[{'op':'message','text':'隐藏效果'}]}
        self.assertTrue(all('use' not in item for item in self.server.snapshot()['inventory']))
    def test_traversal_and_cross_origin_mutation_are_rejected(self):
        self.assertEqual(self.request('/media/../../deepseek.local.key',headers=self.headers)[0],404)
        self.assertEqual(self.request('/start','POST',{},dict(self.headers,Origin='https://evil.example'))[0],401)
        self.assertIsNone(self.server.world.state)
    def test_web_configuration_keeps_selected_model_effort_and_budget(self):
        with patch.object(self.server.subscription,'public',return_value={'ready':True,'phase':'ready'}):
            status,_,body=self.request('/configure','POST',{'provider':'chatgpt_subscription','offline':False,'model':'gpt-6-luna','reasoning_effort':'none','max_calls':5},self.headers)
        self.assertEqual(status,200)
        value=json.loads(body);self.assertEqual(value['configuration']['model'],'gpt-6-luna');self.assertEqual(value['configuration']['reasoning_effort'],'none')
        self.assertEqual(value['configuration']['max_calls'],5);self.assertEqual(self.server.director.calls,0)


if __name__=='__main__':unittest.main()
