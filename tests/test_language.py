import copy
import http.client
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from engine.server import GameServer
from engine.director import ChatProvider,Director

class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'world.sqlite3'
        self.server=GameServer(('127.0.0.1',0),self.path,'language-test-token')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.server.world.store.close();self.temp.cleanup()
    def request(self,body,token='language-test-token'):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        conn.request('POST','/language',json.dumps(body),{'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        response=conn.getresponse();data=json.loads(response.read());status=response.status;conn.close();return status,data
    def test_language_only_change_keeps_world_pause_budget_and_identity(self):
        w=self.server.world;w.start('旧故事和旧任务保持中文',authored=True)
        d=self.server.director;d.configure({'offline':True});d.calls=7;d.paused=True
        before=copy.deepcopy(w.state);generation=d.generation
        status,data=self.request({'language':'en'})
        self.assertEqual(status,200);self.assertEqual(data['configuration']['language'],'en')
        self.assertEqual(w.state,before);self.assertEqual(d.calls,7);self.assertTrue(d.paused);self.assertEqual(d.generation,generation)
        saved=json.loads(self.path.with_name('settings.json').read_text(encoding='utf8'))
        self.assertEqual(saved['language'],'en');self.assertNotIn('api_key',saved)
        self.assertEqual(self.request({'language':'zh'})[0],200)
        self.assertEqual(d.cfg['language'],'zh');self.assertEqual(w.state,before)
    def test_unconfigured_language_persists_without_starting_generation(self):
        self.assertEqual(self.request({'language':'en'})[0],200)
        self.assertIsNone(self.server.director.cfg);self.assertEqual(self.server.director.calls,0)
        self.assertEqual(self.request({'language':'invalid'})[0],400)
        self.assertEqual(self.request({'language':'zh'},'wrong')[0],401)
        other=GameServer(('127.0.0.1',0),self.path,'second-test-token')
        try:self.assertEqual(other.preferences['language'],'en')
        finally:other.server_close();other.world.store.close()
    def test_english_generation_request_replaces_chinese_instruction(self):
        w=self.server.world;w.start('保留既有事实和名称',authored=True)
        d=Director(w);d.configure({'offline':False,'base_url':'http://127.0.0.1:1','language':'en'})
        captured=[]
        def stop(request,*args,**kwargs):
            captured.append(json.loads(request.data));raise OSError('captured without a model request')
        with patch('engine.director.urllib.request.OpenerDirector.open',side_effect=stop):
            try:ChatProvider(d.cfg).generate(w.context(),'region')
            except Exception:pass
        self.assertEqual(len(captured),1)
        prompt=captured[0]['messages'][0]['content']
        self.assertIn('Use English display names',prompt)
        self.assertNotIn('Use Chinese display names',prompt)
        self.assertIn('Preserve existing names',prompt)
    def test_client_catalog_covers_messages_and_preserves_format_arguments(self):
        catalog=json.loads(Path('assets/i18n/en.json').read_text(encoding='utf8'))
        for p in Path('client').glob('*.gd'):
            for value in re.findall(r'(?:L\.)?t\(("(?:\\.|[^"\\])*")\)',p.read_text(encoding='utf8')):
                source=json.loads(value)
                if re.search('[\u4e00-\u9fff]',source):self.assertIn(source,catalog,f'{p}: {source}')
        for source,target in catalog.items():
            self.assertTrue(target.strip(),source)
            fmt=r'%(?:[0-9.]+)?[dsf]'
            self.assertEqual(re.findall(fmt,source),re.findall(fmt,target),source)

if __name__=='__main__':unittest.main()
