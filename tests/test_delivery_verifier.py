"""A verificação gratuita não pode aceitar um endpoint de geração paga por engano."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import verify_delivery

class FreeVerifier(unittest.TestCase):
    def test_rejects_wrong_mode_before_any_post(self):
        for health in ({'knowledge':'generated','web_search_enabled':False}, {'knowledge':'rag','web_search_enabled':True}, {'web_search_enabled':False}):
            with self.subTest(health=health), tempfile.TemporaryDirectory() as folder:
                argv=['verify_delivery','--url','http://127.0.0.1:8000','--output',str(Path(folder)/'result.json')]
                with patch('sys.argv',argv), patch.object(verify_delivery,'request',return_value=(200,health)) as request, patch.object(verify_delivery,'verify') as verify:
                    with self.assertRaisesRegex(RuntimeError,'no POST performed'):verify_delivery.main()
                    request.assert_called_once_with('http://127.0.0.1:8000','/health',timeout=1)
                    verify.assert_not_called()
