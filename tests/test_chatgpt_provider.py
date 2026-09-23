import json
import io
import os
from pathlib import Path
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import patch
from engine.chatgpt_provider import generate,DirectError,classify
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


class StrictSSE(SSE):
    def readline(self):
        if self.index==len(self.lines):raise AssertionError('read after response.completed')
        return super().readline()


class Audit:
    def __init__(self):self.events=[]
    def emit(self,event,**details):self.events.append((event,details))


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
    def test_transient_eof_retries_once_with_fresh_buffer_and_metering(self):
        first=SSE([dict(type='response.output_text.delta',delta='{"partial":')]);second=SSE(completed('{"ok":true}'));reserved=[];audit=Audit()
        cfg={'model':'gpt-5.6-luna','reasoning_effort':'high','_subscription_token':self.token(),'max_transport_retries':1,
             '_request_meta':{'kind':'campaign','target':'r0','call':1},'_audit':audit,
             '_reserve_transport_retry':lambda details:reserved.append(details) or 2}
        with patch('urllib.request.urlopen',side_effect=[first,second]) as request,patch('engine.chatgpt_provider.wait_retry',return_value=False):raw,usage=generate('system','user',cfg)
        self.assertEqual(raw,'{"ok":true}');self.assertEqual(request.call_count,2);self.assertEqual(len(reserved),1)
        self.assertEqual((usage['transport_retries'],usage['unknown_usage_attempts'],usage['model_requests']),(1,1,2))
        self.assertTrue(any(event=='chatgpt.retry.scheduled' and data['partial_output_chars']>0 for event,data in audit.events))
    def test_completed_event_returns_without_waiting_for_stream_close(self):
        stream=StrictSSE(completed())
        with patch('urllib.request.urlopen',return_value=stream):raw,_=generate('system','user',{'model':'gpt-5.6-luna','reasoning_effort':'high','_subscription_token':self.token()})
        self.assertEqual(raw,'{"ok":true}');self.assertTrue(stream.closed)
    def test_retry_stops_when_budget_reservation_fails(self):
        stream=SSE([dict(type='response.created')]);cfg={'model':'gpt-5.6-luna','reasoning_effort':'high','_subscription_token':self.token(),'max_transport_retries':1,'_reserve_transport_retry':lambda _:None}
        with patch('urllib.request.urlopen',return_value=stream) as request,patch('engine.chatgpt_provider.wait_retry',return_value=False),self.assertRaises(DirectError) as caught:generate('system','user',cfg)
        self.assertEqual(request.call_count,1);self.assertEqual(caught.exception.diagnostics['retry_blocked'],'budget_or_state')
    def test_retry_wait_can_be_cancelled_without_second_send(self):
        stream=SSE([dict(type='response.created')]);cfg={'model':'gpt-5.6-luna','reasoning_effort':'high','_subscription_token':self.token(),'max_transport_retries':1,'_reserve_transport_retry':lambda _:2}
        with patch('urllib.request.urlopen',return_value=stream) as request,patch('engine.chatgpt_provider.wait_retry',return_value=True),self.assertRaises(DirectError) as caught:generate('system','user',cfg)
        self.assertEqual(caught.exception.category,'cancelled');self.assertEqual(request.call_count,1)
    def test_429_rate_limit_is_distinct_from_quota(self):
        def failure(payload):return urllib.error.HTTPError('https://example.test',429,'limited',{'Retry-After':'3'},io.BytesIO(json.dumps(payload).encode()))
        for payload,category in (({'error':{'code':'rate_limit_exceeded'}},'rate_limit'),({'error':{'code':'insufficient_quota'}},'quota')):
            with self.subTest(category=category),patch('urllib.request.urlopen',side_effect=failure(payload)),self.assertRaises(DirectError) as caught:
                generate('system','user',{'model':'gpt-5.6-luna','reasoning_effort':'high','_subscription_token':self.token()})
            self.assertEqual(caught.exception.category,category)
            self.assertFalse(caught.exception.diagnostics['usage_unknown'])
            if category=='rate_limit':self.assertEqual(caught.exception.retry_after,3)
    def test_permission_failure_is_not_treated_as_expired_auth(self):
        self.assertEqual(classify({'error':{'code':'permission_denied'}},403),'provider')
        self.assertEqual(classify({'error':{'code':'access_token_expired'}},403),'auth')
    def test_expired_shared_deadline_sends_nothing(self):
        cfg={'model':'gpt-5.6-luna','reasoning_effort':'high','_subscription_token':self.token(),'_task_deadline':time.monotonic()-1}
        with patch('urllib.request.urlopen',side_effect=AssertionError('must not send')),self.assertRaises(DirectError) as caught:generate('system','user',cfg)
        self.assertEqual(caught.exception.category,'deadline')
    def test_context_projection_is_logged_without_prompt_content(self):
        world=World(WorldStore(':memory:'))
        try:
            director=Director(world);director.configure({'provider':'chatgpt_subscription','offline':False});audit=Audit();cfg=dict(director.cfg,_audit=audit,_request_meta={'kind':'campaign','target':'r0','call':1})
            with patch('engine.chatgpt_provider.generate',return_value=('{}',{})):ChatProvider(cfg).generate({'content_version':2,'setting':'private-test'},'campaign')
            event=next(data for name,data in audit.events if name=='model.context.prepared')
            self.assertGreater(event['system_chars'],0);self.assertGreater(event['projected_chars'],0);self.assertNotIn('private-test',json.dumps(event))
        finally:world.store.close()
    def test_model_and_effort_are_fixed(self):
        for cfg in ({'model':'other','reasoning_effort':'high'},{'model':'gpt-5.6-luna','reasoning_effort':'invalid'}):
            with self.assertRaises(DirectError):generate('','',dict(cfg,_subscription_token=self.token()))
    def test_gpt6_luna_all_six_efforts_use_selected_model_without_fallback(self):
        for effort in ('none','low','medium','high','xhigh','max'):
            with self.subTest(effort=effort):
                events=completed(model='gpt-6-luna');events[-1]['response']['reasoning']={'effort':effort}
                with patch('urllib.request.urlopen',return_value=SSE(events)) as request:
                    _,stats=generate('system','user',{'model':'gpt-6-luna','reasoning_effort':effort,'_subscription_token':self.token()})
                sent=json.loads(request.call_args.args[0].data)
                self.assertEqual((sent['model'],sent['reasoning']['effort']),('gpt-6-luna',effort))
                self.assertEqual((stats['model'],stats['effort'],stats['reported_effort']),('gpt-6-luna',effort,effort))
    def test_medium_is_sent_and_reported_without_silent_high_override(self):
        events=completed();events[-1]['response']['reasoning']={'effort':'medium'};audit=Audit()
        with patch('urllib.request.urlopen',return_value=SSE(events)) as request:
            _,usage=generate('system','user',{'model':'gpt-5.6-luna','reasoning_effort':'medium','_subscription_token':self.token(),'_audit':audit})
        self.assertEqual(json.loads(request.call_args.args[0].data)['reasoning']['effort'],'medium')
        self.assertEqual((usage['effort'],usage['reported_effort']),('medium','medium'))
        self.assertTrue(any(name=='chatgpt.request.started' and d['effort']=='medium' for name,d in audit.events))
    def test_direct_input_is_not_cut_to_a_small_context_setting(self):
        user='long-context-check '*20000
        with patch('urllib.request.urlopen',return_value=SSE(completed())) as request:
            generate('system',user,{'model':'gpt-5.6-luna','reasoning_effort':'medium','_subscription_token':self.token()})
        body=json.loads(request.call_args.args[0].data)
        self.assertTrue(body['input'][0]['content'][0]['text'].startswith(user))
        self.assertNotIn('model_context_window',body);self.assertNotIn('context_management',body)
    def test_reported_effort_mismatch_is_not_accepted(self):
        events=completed();events[-1]['response']['reasoning']={'effort':'high'}
        with patch('urllib.request.urlopen',return_value=SSE(events)),self.assertRaises(DirectError):
            generate('','',{'model':'gpt-5.6-luna','reasoning_effort':'medium','_subscription_token':self.token()})
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
            self.assertEqual((d.cfg['model'],d.cfg['reasoning_effort'],d.cfg['api_key']),('gpt-6-luna','high',''))
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
    def test_existing_direct_save_preserves_gpt_5_6_choice(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'world.sqlite3'
            path.with_name('settings.json').write_text(json.dumps({'provider':'chatgpt_subscription','model':'gpt-5.6-luna','reasoning_effort':'medium'}))
            server=GameServer(('127.0.0.1',0),path,'test')
            try:self.assertEqual((server.preferences['model'],server.preferences['reasoning_effort']),('gpt-5.6-luna','medium'))
            finally:server.server_close();server.world.store.close()
    def test_server_snapshot_never_exposes_subscription_tokens(self):
        with patch('engine.subscription_auth.Store.load',return_value=self.token()):
            server=GameServer(('127.0.0.1',0),':memory:','test')
        try:
            first=server.snapshot();snapshot=json.dumps(first)
            self.assertTrue(server.snapshot()['subscription']['ready'])
            self.assertTrue(first['instance_id']);self.assertEqual(server.snapshot()['instance_id'],first['instance_id'])
            self.assertNotIn('access',snapshot);self.assertNotIn('refresh',snapshot);self.assertNotIn('account',snapshot)
        finally:server.server_close();server.world.store.close()

if __name__=='__main__':unittest.main()
