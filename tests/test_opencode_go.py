"""验证本机 Go 凭据仅用于明确选择的官方端点。"""
import os
import io
import json
import time
import unittest
import urllib.error
from unittest.mock import patch

from engine.director import ChatProvider, Director, ProviderError, official_opencode_go, read_chat_stream
from engine.storage import Store
from engine.world import World


class OpenCodeGoTests(unittest.TestCase):
    def test_region_uses_complete_go_stream_with_reported_usage(self):
        wire=(b'data: {"choices":[{"delta":{"content":"{\\"kind\\":","reasoning_content":"thinking"}}]}\n\n'
              b'data: {"choices":[{"delta":{"content":"\\"region\\":{}}"},"finish_reason":"stop"}]}\n\n'
              b'data: {"choices":[],"usage":{"prompt_tokens":8,"completion_tokens":5}}\n\n'
              b'data: [DONE]\n\n')
        payloads=[]
        def open_request(request,*args,**kwargs):
            payloads.append(json.loads(request.data))
            return io.BytesIO(wire)
        cfg={'provider':'chat_completions','base_url':'https://opencode.ai/zen/go/v1',
             'model':'space-bunny-free','api_key':'sk-test-only',
             'deepseek_options':False,'reasoning_effort':'none'}
        with patch('engine.director.urllib.request.OpenerDirector.open',side_effect=open_request):
            raw,usage=ChatProvider(cfg).generate({},'region')
        self.assertTrue(payloads[0]['stream'])
        self.assertTrue(payloads[0]['stream_options']['include_usage'])
        self.assertEqual(raw,'{"kind":"region":{}}')
        self.assertEqual(usage['output_tokens'],5)
        self.assertTrue(usage['reasoning_observed'])

    def test_incomplete_stream_keeps_usage_uncertain(self):
        with self.assertRaises(ProviderError) as caught:
            read_chat_stream(io.BytesIO(b'data: {"choices":[{"delta":{"content":"partial"}}]}\n'))
        self.assertTrue(caught.exception.diagnostics['usage_unknown'])

    def test_stream_respects_shared_task_deadline(self):
        wire=b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        with self.assertRaises(ProviderError) as caught:
            read_chat_stream(io.BytesIO(wire),deadline=time.monotonic()-1)
        self.assertEqual(caught.exception.diagnostics['category'],'deadline')

    def test_stream_wire_limit_counts_overhead_separately(self):
        wire=b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n'
        with self.assertRaises(ProviderError) as caught:
            read_chat_stream(io.BytesIO(wire),limit=100,wire_limit=16)
        self.assertTrue(caught.exception.diagnostics['usage_unknown'])

    def test_transient_503_uses_one_accounted_retry(self):
        calls=[]
        reservations=[]
        response=(b'data: {"choices":[{"delta":{"content":"{\\"kind\\":\\"reaction\\",\\"reaction\\":{\\"text\\":\\"\xe9\xa3\x8e\xe5\x81\x9c\xe4\xba\x86\xe3\x80\x82\\"}}"},"finish_reason":"stop"}]}\n\n'
                  b'data: {"choices":[],"usage":{"prompt_tokens":8,"completion_tokens":5}}\n\n'
                  b'data: [DONE]\n\n')
        def open_request(*args,**kwargs):
            calls.append(1)
            if len(calls)==1:
                raise urllib.error.HTTPError('https://opencode.ai/zen/go/v1/chat/completions',503,'Unavailable',{},io.BytesIO(b'{}'))
            return io.BytesIO(response)
        def reserve(details):
            reservations.append(details)
            return 2
        cfg={'provider':'chat_completions','base_url':'https://opencode.ai/zen/go/v1',
             'model':'deepseek-v4.1-flash','api_key':'sk-test-only',
             'deepseek_options':False,'reasoning_effort':'none','max_transport_retries':1,
             '_request_meta':{'call':1},'_reserve_transport_retry':reserve}
        with patch('engine.director.urllib.request.OpenerDirector.open',side_effect=open_request):
            raw,usage=ChatProvider(cfg).generate({},'reaction')
        self.assertEqual(len(calls),2)
        self.assertEqual(reservations[0]['retry_kind'],'http_503')
        self.assertEqual(usage['transport_retries'],1)
        self.assertEqual(usage['model_requests'],2)
        self.assertIn('风停了',raw)

    def test_subscription_error_identifies_the_selected_key(self):
        response = io.BytesIO(b'{"error":{"type":"server_error","message":"Upstream request failed: An active OpenCode Go subscription is required to use Go models."}}')
        failure = urllib.error.HTTPError('https://opencode.ai/zen/go/v1/chat/completions', 403, 'Forbidden', {}, response)
        cfg = {'provider': 'chat_completions', 'base_url': 'https://opencode.ai/zen/go/v1',
               'model': 'deepseek-v4.1-flash', 'api_key': 'sk-test-only',
               'deepseek_options': False, 'reasoning_effort': 'none'}
        with patch('engine.director.urllib.request.OpenerDirector.open', side_effect=failure):
            with self.assertRaisesRegex(ProviderError, '当前 OpenCode Go Key 未获订阅工作区访问权限'):
                ChatProvider(cfg).generate({}, 'reaction')

    def test_environment_key_is_scoped_to_official_go_endpoint(self):
        self.assertTrue(official_opencode_go('https://opencode.ai/zen/go/v1'))
        self.assertFalse(official_opencode_go('https://opencode.ai/zen/v1'))
        world = World(Store(':memory:'))
        try:
            director = Director(world)
            with patch.dict(os.environ, {'OPENCODE_GO_API_KEY': 'sk-local-test'}):
                director.configure({'provider': 'chat_completions', 'offline': False,
                                    'base_url': 'https://opencode.ai/zen/go/v1',
                                    'model': 'deepseek-v4.1-flash', 'deepseek_options': False})
                self.assertEqual(director.cfg['api_key'], 'sk-local-test')
                with self.assertRaises(ProviderError):
                    director.configure({'provider': 'chat_completions', 'offline': False,
                                        'base_url': 'https://opencode.ai/zen/v1',
                                        'model': 'deepseek-v4.1-flash', 'deepseek_options': False})
        finally:
            world.store.close()


if __name__ == '__main__':
    unittest.main()
