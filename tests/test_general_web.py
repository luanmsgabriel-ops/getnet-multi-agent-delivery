import unittest
from unittest.mock import Mock
from fastapi.testclient import TestClient
from app.main import create_app
from app.rag.general_web import GeneralWebSearch, parse_results

RSS = b'<rss><channel><item><title>Python</title><description>Programming language</description><link>https://www.python.org/</link></item></channel></rss>'

class GeneralWebTests(unittest.TestCase):
    def test_public_multi_domain_results(self):
        self.assertEqual(parse_results(RSS)[0]['url'], 'https://www.python.org/')

    def test_xml_entity_rejected(self):
        with self.assertRaises(ValueError):
            parse_results(b'<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss/>')

    def test_private_urls_rejected(self):
        for url in ('http://127.0.0.1/', 'http://169.254.169.254/', 'file:///etc/passwd', 'http://localhost/'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_results(RSS.replace(b'https://www.python.org/', url.encode()))

    def test_sensitive_query_never_sent(self):
        transport = Mock()
        with self.assertRaises(ValueError):
            GeneralWebSearch(transport).search('cpf 12345678900')
        transport.assert_not_called()

    def test_failure_does_not_expose_exception(self):
        result = GeneralWebSearch(Mock(side_effect=RuntimeError('SECRET'))).search('Python')
        self.assertEqual(result['status'], 'unavailable')
        self.assertNotIn('SECRET', str(result))

    def test_http_general_query_isolated(self):
        transport = Mock(return_value=parse_results(RSS))
        client = TestClient(create_app(mode='rag', enable_web=True, web_search=GeneralWebSearch(transport)))
        response = client.post('/chat', json={'message':'pesquise na web: linguagem Python', 'user_id':'cliente1988'}).json()
        self.assertEqual(response['status'], 'limitado')
        self.assertEqual(response['sources'], [])
        transport.assert_not_called()

    def test_oversized_xml_rejected(self):
        with self.assertRaises(ValueError):
            parse_results(b'x' * 200001)
