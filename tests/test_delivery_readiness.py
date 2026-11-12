"""Readiness regressions use a virtual clock; these are not live service tests."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from scripts import verify_delivery as verifier

class Clock:
    def __init__(self):self.now=0
    def tick(self,seconds):self.now+=seconds

class Readiness(unittest.TestCase):
    def clock(self):
        clock=Clock()
        a=patch.object(verifier.time,'monotonic',side_effect=lambda:clock.now);a.start();self.addCleanup(a.stop)
        b=patch.object(verifier.time,'sleep',side_effect=clock.tick);b.start();self.addCleanup(b.stop)
        return clock
    def test_startup_beyond_old_fifteen_second_window(self):
        clock=self.clock();health={'knowledge':'rag','web_search_enabled':False,'context_interpreter_enabled':False}
        def request(base,path,*,timeout):
            self.assertGreater(timeout,0);self.assertLessEqual(timeout,1)
            if clock.now<18:raise ConnectionRefusedError()
            return 200,health
        with patch.object(verifier,'request',side_effect=request):
            status,data,diag=verifier.wait_ready('http://127.0.0.1:1234',timeout=90)
        self.assertEqual(status,200);self.assertEqual(data,health);self.assertEqual(diag['elapsed_seconds'],18)
        self.assertGreater(diag['attempts'],60)
    def test_deadline_is_bounded_and_error_does_not_leak(self):
        clock=self.clock()
        with patch.object(verifier,'request',side_effect=OSError('SYNTHETIC_SECRET_NOT_FOR_LOGS')):
            with self.assertRaises(verifier.StartupError) as caught:verifier.wait_ready('http://127.0.0.1:1234',timeout=2)
        self.assertEqual(clock.now,2);self.assertEqual(caught.exception.diagnostics['last_error_type'],'OSError')
        self.assertNotIn('SYNTHETIC_SECRET',json.dumps(caught.exception.diagnostics))
    def test_owned_process_exit_is_reported_without_post(self):
        self.clock();process=Mock();process.poll.return_value=1
        with patch.object(verifier,'request') as request:
            with self.assertRaises(verifier.StartupError) as caught:verifier.wait_ready('http://127.0.0.1:1234',process=process)
        self.assertEqual(caught.exception.diagnostics['reason'],'server_process_exited');request.assert_not_called()
    def test_last_probe_cannot_exceed_remaining_budget(self):
        clock=self.clock();timeouts=[]
        def request(*args,timeout):timeouts.append(timeout);clock.tick(timeout);raise TimeoutError()
        with patch.object(verifier,'request',side_effect=request):
            with self.assertRaises(verifier.StartupError):verifier.wait_ready('http://127.0.0.1:1234',timeout=1.5)
        self.assertEqual(timeouts,[1,.25]);self.assertEqual(clock.now,1.5)
    def test_malformed_health_is_not_treated_as_ready(self):
        self.clock()
        with patch.object(verifier,'request',side_effect=json.JSONDecodeError('invalid','',0)):
            with self.assertRaises(json.JSONDecodeError):verifier.wait_ready('http://127.0.0.1:1234')
    def test_failure_receipt_and_no_contract_execution(self):
        self.clock()
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'http.json'
            with patch('sys.argv',['verify','--url','http://127.0.0.1:1234','--startup-timeout','1','--output',str(output)]),patch.object(verifier,'request',side_effect=ConnectionRefusedError()),patch.object(verifier,'verify') as contracts:
                with self.assertRaises(verifier.StartupError):verifier.main()
            receipt=json.loads(output.read_text());self.assertFalse(receipt['passed'])
            self.assertEqual(receipt['readiness']['reason'],'startup_deadline_exceeded');contracts.assert_not_called()

if __name__=='__main__':unittest.main()
