import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from engine.audit import AuditLog
from engine.codex_telemetry import CodexTelemetry
from engine.codex_provider import generate,CodexError


class TelemetryTests(unittest.TestCase):
    def test_counts_phases_and_retries_without_logging_reasoning_or_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            audit=AuditLog(folder)
            t=CodexTelemetry({'_audit':audit,'model':'gpt-5.6-luna','reasoning_effort':'high'},'PRIVATE_PROMPT','PRIVATE_CONTEXT')
            t.observe({'method':'item/reasoning/textDelta','params':{'delta':'PRIVATE_REASONING'}})
            t.observe({'method':'item/agentMessage/delta','params':{'itemId':'a','delta':'{"ok":true}'}})
            t.observe({'method':'error','params':{'error':{'message':'Bearer confidential-value','codexErrorInfo':{'responseStreamDisconnected':{'httpStatusCode':502}}},'willRetry':True}})
            t.stderr('Authorization: Bearer confidential-value reconnect')
            t.finish('failed');audit.close()
            body=(Path(folder)/'engine.jsonl').read_text(encoding='utf8')
            for secret in ('PRIVATE_PROMPT','PRIVATE_CONTEXT','PRIVATE_REASONING','confidential-value'):self.assertNotIn(secret,body)
            self.assertEqual(t.retries,1);self.assertEqual(t.errors,1);self.assertEqual(t.output_chars,11)
            self.assertIn('responseStreamDisconnected',body)
            self.assertIsNotNone(t.first_reasoning);self.assertIsNotNone(t.first_output)
    def test_partial_artifact_excludes_reasoning_and_commentary(self):
        with tempfile.TemporaryDirectory() as folder:
            t=CodexTelemetry({'_codex_partial_dir':folder},'','')
            t.observe({'method':'item/reasoning/textDelta','params':{'delta':'PRIVATE_THOUGHT'}})
            t.observe({'method':'item/agentMessage/delta','params':{'itemId':'comment','delta':'Working...'}})
            t.observe({'method':'item/completed','params':{'item':{'id':'comment','type':'agentMessage','phase':'commentary'}}})
            t.observe({'method':'item/agentMessage/delta','params':{'itemId':'answer','delta':'{"region":'}})
            t.finish('failed')
            body=next(Path(folder).glob('*.partial.txt')).read_text()
            self.assertEqual(body,'{"region":')
    def test_historical_deadline_records_active_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            audit=AuditLog(folder)
            with patch('engine.codex_telemetry.time.monotonic',return_value=0):t=CodexTelemetry({'_audit':audit},'','')
            with patch('engine.codex_telemetry.time.monotonic',return_value=301):
                t.observe({'method':'item/agentMessage/delta','params':{'delta':'ongoing'}})
                snapshot=t.snapshot();t.heartbeat()
            audit.close();body=(Path(folder)/'engine.jsonl').read_text()
            self.assertEqual(body.count('codex.previous_deadline.reached'),1)
            self.assertEqual(snapshot['last_progress_age'],0);self.assertEqual(snapshot['stage'],'output')
    def test_high_cannot_be_silently_lowered(self):
        with self.assertRaises(CodexError):generate('','',{'model':'gpt-5.6-luna','reasoning_effort':'medium'})

if __name__=='__main__':unittest.main()
