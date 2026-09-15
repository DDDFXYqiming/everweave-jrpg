from collections import deque
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from engine.codex_provider import CodexError,generate,preflight,process_config,close_json_containers,MODEL
from engine.director import ChatProvider,Director,ProviderError
from engine.world import World
from engine.storage import Store
from engine.server import GameServer


class FakeRPC:
    account={'type':'chatgpt','planType':'pro'}
    model=MODEL
    limits={}
    final_status='completed'
    instances=[]
    def __init__(self,*args,**kwargs):
        self.calls=[];self.closed=False;self.saved=deque([
            {'method':'item/completed','params':{'threadId':'test-thread','item':{'id':'preface','type':'agentMessage','phase':'commentary','text':'Working...'}}},
            {'method':'item/agentMessage/delta','params':{'threadId':'test-thread','delta':'{"kind":"region"}'}},
            {'method':'item/completed','params':{'threadId':'test-thread','item':{'id':'answer','type':'agentMessage','phase':'final_answer','text':'{"kind":"region"}'}}},
            {'method':'thread/tokenUsage/updated','params':{'threadId':'test-thread','tokenUsage':{'last':{'inputTokens':120,'outputTokens':80,'cachedInputTokens':40,'reasoningOutputTokens':20}}}},
            {'method':'turn/completed','params':{'threadId':'test-thread','turn':{'id':'test-turn','status':self.final_status}}}])
        self.instances.append(self)
    def initialize(self):pass
    def close(self):self.closed=True
    def call(self,method,params):
        self.calls.append((method,params))
        if method=='account/read':return {'account':self.account}
        if method=='model/list':return {'data':[{'model':self.model,'supportedReasoningEfforts':[{'reasoningEffort':'high'}]}]}
        if method=='account/rateLimits/read':return self.limits
        if method=='thread/start':return {'thread':{'id':'test-thread'},'model':self.model,'reasoningEffort':'high','modelProvider':'openai'}
        if method=='turn/start':return {'turn':{'id':'test-turn'}}
        raise AssertionError(method)
    def receive(self):raise AssertionError('Unexpected additional receive')


class CodexProviderTests(unittest.TestCase):
    def setUp(self):
        FakeRPC.instances=[];FakeRPC.account={'type':'chatgpt','planType':'pro'};FakeRPC.model=MODEL;FakeRPC.limits={};FakeRPC.final_status='completed'
    def test_requires_subscription_not_an_api_key_login(self):
        FakeRPC.account={'type':'apiKey'}
        with self.assertRaises(CodexError):preflight(FakeRPC())
        self.assertEqual([m for m,p in FakeRPC.instances[-1].calls],['account/read'])
    def test_closing_only_containers_never_fabricates_a_partial_value(self):
        text,count=close_json_containers('{"kind":"campaign","campaign":{"regions":[]}')
        self.assertEqual(count,1);self.assertEqual(json.loads(text)['campaign']['regions'],[])
        for raw in ('{"text":"cut off','{"value":','{"value":]','{"a":{oops}'):
            self.assertEqual(close_json_containers(raw),(raw,0))
    def test_exact_model_and_effort_no_fallback(self):
        FakeRPC.model='another-model'
        with self.assertRaises(CodexError):preflight(FakeRPC())
        FakeRPC.model=MODEL
        with self.assertRaises(CodexError):preflight(FakeRPC(),effort='ultra')
    def test_exhausted_subscription_stops_before_generation(self):
        FakeRPC.limits={'rateLimits':{'primary':{'usedPercent':100},'credits':{'hasCredits':True}}}
        with self.assertRaises(CodexError):preflight(FakeRPC())
        self.assertNotIn('turn/start',[m for m,p in FakeRPC.instances[-1].calls])
    def test_ephemeral_final_only_usage_and_cleanup(self):
        with patch('engine.codex_provider.RPC',FakeRPC):raw,usage=generate('protocol','game context',{'model':MODEL,'reasoning_effort':'high'})
        self.assertEqual(raw,'{"kind":"region"}');self.assertEqual(usage['reasoning_tokens'],20)
        rpc=FakeRPC.instances[-1];self.assertTrue(rpc.closed)
        start=next(p for m,p in rpc.calls if m=='thread/start');turn=next(p for m,p in rpc.calls if m=='turn/start')
        self.assertTrue(start['ephemeral']);self.assertFalse(start['allowProviderModelFallback'])
        self.assertEqual(start['sandbox'],'read-only');self.assertEqual(turn['effort'],'high')
        self.assertEqual(start['modelProvider'],'openai');self.assertEqual(turn['serviceTierForTurn'],'default')
    def test_failed_turn_preserves_usage_and_closes(self):
        FakeRPC.final_status='failed'
        with patch('engine.codex_provider.RPC',FakeRPC),self.assertRaises(CodexError) as caught:generate('protocol','data',{'model':MODEL,'reasoning_effort':'high'})
        self.assertTrue(FakeRPC.instances[-1].closed);self.assertEqual(caught.exception.usage['output_tokens'],80)
    def test_inherited_tools_disabled_without_global_config_changes(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'CODEX_HOME':folder}):
            path=Path(folder)/'config.toml';original='model="something_else"\n[mcp_servers.example]\ncommand="unused"\n';path.write_text(original)
            cfg=process_config();self.assertFalse(cfg['features.shell_tool']);self.assertFalse(cfg['features.apps'])
            self.assertFalse(cfg['mcp_servers.example.enabled']);self.assertEqual(path.read_text(),original)
            path.write_text('forced_login_method="api"')
            with self.assertRaises(CodexError):process_config()
    def test_subscription_dispatch_never_opens_http_fallback(self):
        w=World(Store(':memory:'))
        try:
            d=Director(w)
            with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'do-not-use','OPENAI_API_KEY':'do-not-use'}):d.configure({'provider':'codex_subscription','offline':False,'api_key':'do-not-use'})
            self.assertEqual((d.cfg['model'],d.cfg['reasoning_effort'],d.cfg['api_key']),(MODEL,'high',''))
            with patch('engine.codex_provider.generate',return_value=('{}',{})) as call,patch('urllib.request.build_opener',side_effect=AssertionError('paid API fallback')):
                ChatProvider(d.cfg).generate({'content_version':2,'setting':'test'},'campaign')
                self.assertEqual(call.call_count,1)
            with patch('engine.codex_provider.generate',side_effect=CodexError('offline')),patch('urllib.request.build_opener',side_effect=AssertionError('paid API fallback')):
                with self.assertRaises(ProviderError):ChatProvider(d.cfg).generate({'content_version':2},'campaign')
        finally:w.store.close()
    def test_old_settings_default_to_subscription_without_loading_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'world.sqlite3';path.with_name('settings.json').write_text(json.dumps({'model':'deepseek-flash','base_url':'https://api.deepseek.com','reasoning_effort':'low','max_calls':7}))
            server=GameServer(('127.0.0.1',0),path,'test')
            try:
                self.assertEqual(server.preferences['provider'],'codex_subscription')
                self.assertEqual(server.preferences['model'],MODEL);self.assertEqual(server.preferences['reasoning_effort'],'high');self.assertEqual(server.preferences['max_calls'],7)
            finally:server.server_close();server.world.store.close()

if __name__=='__main__':unittest.main()
