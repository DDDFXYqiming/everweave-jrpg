import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from engine.chatgpt_provider import generate,DirectError
from engine.subscription_auth import Store,Token,Login,LoginManager
from engine.director import Director,ChatProvider,ProviderError
from engine.storage import Store as WorldStore
from engine.world import World
from engine.server import GameServer


class SSE:
    def __init__(self,events):
        self.lines=[]
        for event in events:self.lines.extend([('data: '+json.dumps(event)+'\n').encode(),b'\n'])
        self.index=0;self.closed=False
    def readline(self):
        if self.index==len(self.lines):return b''
        line=self.lines[self.index];self.index+=1;return line
    def close(self):self.closed=True


def completed(text='{"ok":true}',model='gpt-5.6-luna'):
    response={'status':'completed','model':model,'output':[{'type':'message','content':[{'type':'output_text','text':text}]}],
              'usage':{'input_tokens':100,'output_tokens':50,'input_tokens_details':{'cached_tokens':20},'output_tokens_details':{'reasoning_tokens':30}}}
    return [dict(type='response.output_text.delta',delta=text),dict(type='response.completed',response=response)]


class MemoryStore:
    def __init__(self,token=None):self.token=token;self.saved=[]
    def load(self):return self.token
    def save(self,token):self.token=token;self.saved.append(token)


class DirectSubscriptionTests(unittest.TestCase):
    def token(self,refresh='refresh'):return Token('access',refresh,time.time()+3600,'account')
    def test_direct_sse_has_no_cli_and_reports_usage(self):
        stream=SSE(completed())
        with patch('urllib.request.urlopen',return_value=stream) as request:
            raw,usage=generate('system','user',{'model':'gpt-5.6-luna','reasoning_effort':'high','_subscription_token':self.token()})
        self.assertEqual(raw,'{"ok":true}');self.assertEqual(usage['reasoning_tokens'],30);self.assertEqual(usage['cached_input_tokens'],20)
        sent=json.loads(request.call_args.args[0].data)
        self.assertEqual(sent['reasoning']['effort'],'high');self.assertTrue(sent['stream']);self.assertEqual(sent['model'],'gpt-5.6-luna')
        self.assertEqual(sent['text']['format']['type'],'json_object')
        self.assertIn('JSON object',sent['input'][0]['content'][0]['text'])
        self.assertNotIn('tools',sent);self.assertNotIn('include',sent);self.assertTrue(sent['prompt_cache_key'].startswith('everweave-'))
        self.assertEqual(request.call_args.args[0].headers['Authorization'],'Bearer access')
        self.assertTrue(stream.closed)
    def test_model_and_effort_are_fixed(self):
        for cfg in ({'model':'other','reasoning_effort':'high'},{'model':'gpt-5.6-luna','reasoning_effort':'medium'}):
            with self.assertRaises(DirectError):generate('','',dict(cfg,_subscription_token=self.token()))
    def test_model_reroute_is_rejected(self):
        with patch('urllib.request.urlopen',return_value=SSE(completed(model='other'))):
            with self.assertRaises(DirectError):generate('','',{'model':'gpt-5.6-luna','reasoning_effort':'high','_subscription_token':self.token()})
    def test_store_roundtrip_is_protected_on_windows(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'credential.bin';store=Store(path);token=Token('secret-access','secret-refresh',time.time()+3600,'account')
            store.save(token);loaded=store.load();self.assertEqual(loaded,token)
            if os.name=='nt':self.assertNotIn(b'secret-access',path.read_bytes())
            store.forget();self.assertFalse(path.exists())
    def test_windows_cross_volume_replace_uses_protected_bounded_write(self):
        if os.name!='nt':self.skipTest('Windows DPAPI fallback')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'credential.bin';store=Store(path);original=Path.replace
            def fail(source,target):
                error=OSError('cross volume');error.winerror=17;raise error
            with patch.object(Path,'replace',fail):store.save(Token('safe-access','safe-refresh',time.time()+3600,'account'))
            self.assertEqual(store.load().account_id,'account');self.assertNotIn(b'safe-access',path.read_bytes())
    def test_login_manager_persists_completed_device_flow(self):
        memory=MemoryStore();login=Login('https://auth.openai.com/codex/device','ABCD','device',3,time.time()+60)
        with patch('engine.subscription_auth.start_login',return_value=login),patch('engine.subscription_auth.poll_login',return_value=self.token()),patch('engine.subscription_auth.time.sleep'):
            manager=LoginManager(memory);public=manager.start();self.assertEqual(public['user_code'],'ABCD');manager.thread.join(2)
        self.assertTrue(manager.public()['ready']);self.assertEqual(len(memory.saved),1)
    def test_direct_dispatch_never_uses_app_server_or_paid_http(self):
        w=World(WorldStore(':memory:'))
        try:
            d=Director(w);d.configure({'provider':'chatgpt_subscription','offline':False})
            self.assertEqual((d.cfg['model'],d.cfg['reasoning_effort'],d.cfg['api_key']),('gpt-5.6-luna','high',''))
            with patch('engine.chatgpt_provider.generate',return_value=('{}',{})) as direct,patch('engine.codex_provider.generate',side_effect=AssertionError('app server')),patch('urllib.request.build_opener',side_effect=AssertionError('paid API')):
                ChatProvider(d.cfg).generate({'content_version':2},'campaign');self.assertEqual(direct.call_count,1)
            with patch('engine.chatgpt_provider.generate',side_effect=DirectError('auth',category='auth')):
                with self.assertRaises(ProviderError):ChatProvider(d.cfg).generate({'content_version':2},'campaign')
        finally:w.store.close()
    def test_server_migrates_old_codex_provider_to_direct(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'world.sqlite3';path.with_name('settings.json').write_text(json.dumps({'provider':'codex_subscription','max_calls':7}))
            with patch('engine.subscription_auth.Store.load',return_value=None):server=GameServer(('127.0.0.1',0),path,'test')
            try:self.assertEqual(server.preferences['provider'],'chatgpt_subscription');self.assertEqual(server.preferences['max_calls'],7)
            finally:server.server_close();server.world.store.close()
    def test_server_snapshot_never_exposes_subscription_tokens(self):
        with patch('engine.subscription_auth.Store.load',return_value=self.token()):
            server=GameServer(('127.0.0.1',0),':memory:','test')
        try:
            snapshot=json.dumps(server.snapshot())
            self.assertTrue(server.snapshot()['subscription']['ready'])
            self.assertNotIn('access',snapshot);self.assertNotIn('refresh',snapshot);self.assertNotIn('account',snapshot)
        finally:server.server_close();server.world.store.close()

if __name__=='__main__':unittest.main()
