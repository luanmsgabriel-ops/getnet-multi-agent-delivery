"""Controlled subprocess results validate cleanup; no Docker/model calls here."""
import json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import verify_docker

class DockerLifecycle(unittest.TestCase):
    def exercise(self,fail=None):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'result.json';calls=[];cid='a'*64
            def run(command,**kwargs):
                calls.append(command)
                if command[0]=='docker':
                    verb=command[1]
                    if verb=='create':
                        Path(command[command.index('--cidfile')+1]).write_text(cid)
                        return subprocess.CompletedProcess(command,1 if fail=='create' else 0,stdout=cid,stderr='')
                    if verb=='start':return subprocess.CompletedProcess(command,1 if fail=='start' else 0,stdout='',stderr='')
                    if verb=='port':return subprocess.CompletedProcess(command,0,stdout='127.0.0.1:12345',stderr='')
                    if verb=='logs' and fail=='logs':raise OSError('SYNTHETIC_ERROR_NOT_FOR_LOGS')
                    if verb=='inspect':return subprocess.CompletedProcess(command,0,stdout='invalid' if fail=='state' else '{}',stderr='')
                    return subprocess.CompletedProcess(command,1 if verb=='rm' and fail=='cleanup' else 0,stdout='',stderr='')
                return subprocess.CompletedProcess(command,0)
            with patch('sys.argv',['verify_docker','--output',str(output)]),patch.object(verify_docker.subprocess,'run',side_effect=run):status=verify_docker.main()
            receipt=json.loads(output.with_suffix('.container.json').read_text())
            self.assertEqual([x for x in calls if x[:2]==['docker','rm']],[['docker','rm','-f',cid]])
            self.assertNotIn('SYNTHETIC_ERROR',json.dumps(receipt))
            return status,receipt
    def test_success_is_reported_after_cleanup(self):
        status,receipt=self.exercise();self.assertEqual(status,0);self.assertEqual(receipt['cleanup_exit_code'],0)
    def test_created_container_removed_after_create_error(self):self.assertEqual(self.exercise('create')[0],1)
    def test_created_container_removed_after_start_error(self):self.assertEqual(self.exercise('start')[0],1)
    def test_log_error_still_cleans_up(self):self.assertEqual(self.exercise('logs')[0],1)
    def test_invalid_inspect_still_cleans_up(self):self.assertEqual(self.exercise('state')[0],1)
    def test_cleanup_error_cannot_report_success(self):self.assertEqual(self.exercise('cleanup')[0],1)
if __name__=='__main__':unittest.main()
