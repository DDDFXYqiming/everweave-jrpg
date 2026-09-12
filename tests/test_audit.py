import json
from pathlib import Path
import tempfile
import unittest
from engine.audit import AuditLog
from engine.server import GameServer


class AuditTests(unittest.TestCase):
    def test_redacts_credentials_and_keeps_usage_and_error_trace(self):
        with tempfile.TemporaryDirectory() as folder:
            log=AuditLog(folder);log.add_secret('local-session-secret')
            try:
                try:raise ValueError('bad local-session-secret')
                except ValueError as error:
                    log.emit('test.failure',exception=error,api_key='do-not-write',
                             text='Bearer abcdef sk-abcdefghijklmnop',input_tokens=123)
            finally:log.close()
            text=(Path(folder)/'engine.jsonl').read_text(encoding='utf-8')
            self.assertNotIn('local-session-secret',text);self.assertNotIn('do-not-write',text)
            self.assertNotIn('abcdefghijklmnop',text)
            data=json.loads(text)
            self.assertEqual(data['data']['input_tokens'],123)
            self.assertIn('ValueError',data['exception'])
    def test_rotation_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            log=AuditLog(folder,max_bytes=400,backups=2)
            for i in range(30):log.emit('rotation.test',number=i,text='x'*100)
            log.close()
            files=list(Path(folder).glob('engine.jsonl*'))
            self.assertEqual(len(files),3)
            for file in files:
                for line in file.read_text(encoding='utf-8').splitlines():json.loads(line)
    def test_server_lifecycle_uses_save_local_log(self):
        with tempfile.TemporaryDirectory() as folder:
            server=GameServer(('127.0.0.1',0),Path(folder)/'world.sqlite3','private-loopback-token')
            server.server_close();server.world.store.close()
            lines=(Path(folder)/'logs/engine.jsonl').read_text(encoding='utf-8').splitlines()
            self.assertEqual([json.loads(line)['event'] for line in lines],['server.started','server.stopped'])
            self.assertNotIn('private-loopback-token',''.join(lines))
