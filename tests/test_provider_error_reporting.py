"""Emitter/report contract roundtrip; no network, credentials or model calls."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import observability
from app.observability_report import aggregate_file, valid_record

class ProviderErrorReporting(unittest.TestCase):
    def record(self, status):
        records=[]
        with patch.object(observability, '_write', side_effect=lambda r: records.append(r) or True):
            self.assertTrue(observability.emit_event('provider_http_error', stage='model',
                outcome='error', mode='remote', http_status=status))
        self.assertEqual(len(records),1)
        return records[0]

    def test_emitter_records_roundtrip_without_client_http_pollution(self):
        records=[self.record(429),self.record(500)]
        for r in records:self.assertTrue(valid_record(r))
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'events.jsonl'
            p.write_text(''.join(json.dumps(r)+'\n' for r in records),encoding='utf8')
            report=aggregate_file(p)
        self.assertEqual(report['input_quality']['invalid_records'],0)
        self.assertEqual(report['input_quality']['accepted_records'],2)
        self.assertEqual(report['provider_http_errors'],{'records':2,'statuses':{'429':1,'500':1}})
        self.assertEqual(report['http']['requests'],0)
        self.assertEqual(report['http']['statuses'],{})
        self.assertEqual(report['event_counts']['provider_http_error'],2)
        self.assertEqual(report['costs']['by_mode']['remote']['confirmed_usd'],'0')

    def test_provider_error_schema_remains_closed(self):
        good=self.record(429)
        changes=[{'http_status':True},{'http_status':200},{'http_status':99},
                 {'http_status':600},{'http_status':'429'},{'http_status':None},
                 {'stage':'tool'},{'mode':None},{'mode':'untrusted'},
                 {'payload':'must not be accepted'}, {'cost_state':'unknown','cost_usd':1}]
        for change in changes:
            with self.subTest(change=change):self.assertFalse(valid_record(dict(good,**change)))
        missing=copy.deepcopy(good);missing.pop('http_status')
        self.assertFalse(valid_record(missing))

    def test_other_stage_events_cannot_accept_http_status(self):
        base=self.record(429)
        base['event']='stage_result'
        self.assertFalse(valid_record(base))
        base.pop('http_status')
        self.assertTrue(valid_record(base))

    def test_emitter_still_rejects_invalid_provider_metadata(self):
        with patch.object(observability,'_write') as write:
            for status in [True,200,99,600,'429',None]:
                self.assertFalse(observability.emit_event('provider_http_error',stage='model',outcome='error',mode='remote',http_status=status))
            self.assertFalse(observability.emit_event('stage_result',stage='model',outcome='error',mode='remote',http_status=429))
            write.assert_not_called()
