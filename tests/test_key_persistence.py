"""本机提供方密钥的保存范围和重启恢复。"""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine.director import ProviderError
from engine.server import GameServer


class KeyPersistenceTests(unittest.TestCase):
    def test_key_survives_restart_only_for_exact_provider_url(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'OPENCODE_GO_API_KEY': ''}):
            root = Path(folder)
            save = root / 'world.sqlite3'
            keys = root / 'provider-keys.local.json'
            config = {'provider': 'chat_completions', 'offline': False,
                      'base_url': 'https://opencode.ai/zen/go/v1',
                      'model': 'deepseek-v4.1-flash', 'deepseek_options': False}
            first = GameServer(('127.0.0.1', 0), save, 'local-test-token', credential_path=keys)
            try:
                credential = first.configure_generation(dict(config, api_key='sk-test-only'))
                first.remember_configuration(credential)
                self.assertEqual(json.loads(keys.read_text('utf8'))['chat_completions'][config['base_url']], 'sk-test-only')
                self.assertNotIn('sk-test-only', (root / 'settings.json').read_text('utf8'))
                self.assertNotIn('sk-test-only', json.dumps(first.snapshot()))
            finally:
                first.server_close()
                first.world.store.close()
            second = GameServer(('127.0.0.1', 0), save, 'local-test-token', credential_path=keys)
            try:
                second.configure_generation(dict(config, api_key=''))
                self.assertEqual(second.director.cfg['api_key'], 'sk-test-only')
                self.assertTrue(second.snapshot()['configuration']['credential_available'])
                with self.assertRaises(ProviderError):
                    second.configure_generation(dict(config, base_url='https://example.com/v1', api_key=''))
            finally:
                second.server_close()
                second.world.store.close()


if __name__ == '__main__':
    unittest.main()
