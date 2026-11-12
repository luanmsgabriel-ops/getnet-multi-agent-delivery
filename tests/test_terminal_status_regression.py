"""Private terminal status must not become unrelated public retrieval."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import create_app
from app.intents import terminal_status_query, classify
from app.propositions import knowledge_tasks
from app.context_service import ContextService
from app.context_store import Store

class TerminalStatusRegression(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(mode='rag', enable_web=False))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        service = ContextService(Store(Path(self.tmp.name)/'state.db'), None)
        with patch('app.context_store.Store'):
            from app.context_api import create_app as context_app
        self.context = TestClient(context_app(service))

    def test_pure_status_is_not_knowledge(self):
        for text in ('Qual o estado do meu terminal?', 'Qual e o status da minha maquininha?',
                     'Consulte o status do meu terminal', 'What is the status of my card machine?'):
            with self.subTest(text=text):
                self.assertTrue(terminal_status_query(text))
                self.assertTrue(classify(text).terminal)
                self.assertFalse(classify(text).knowledge)

    def test_http_status_has_no_unrelated_sources_on_all_paths(self):
        for client, endpoint in ((self.client,'/chat'),(self.context,'/chat'),(self.context,'/context/chat')):
            with self.subTest(endpoint=endpoint, client=client):
                response=client.post(endpoint,json={'message':'Qual o estado do meu terminal?','user_id':'cliente1988'})
                self.assertEqual(response.status_code,200)
                body=response.json()
                self.assertIn('DEMO-A-001',body['answer'])
                self.assertIn('online',body['answer'])
                self.assertNotIn('credi',body['answer'].lower())
                self.assertEqual(body['sources'],[])

    def test_mixed_status_preserves_only_public_obligation(self):
        for separator in ('? ', '; ', ' e '):
            text='Qual o estado do meu terminal'+separator+'Como funciona o Crediario?'
            with self.subTest(text=text):
                tasks=knowledge_tasks(text,support_answered=True)
                self.assertEqual(tasks,[('information','Como funciona o Crediario')])
                self.assertTrue(classify(text).knowledge)
                body=self.client.post('/chat',json={'message':text,'user_id':'cliente1988'}).json()
                self.assertIn('DEMO-A-001',body['answer'])
                self.assertIn('credi',body['answer'].lower())
                self.assertTrue(body['sources'])

    def test_technical_product_and_negated_clauses_not_swallowed(self):
        for text in ("My card machine won't connect to the internet, what should I do?",
                     'My card machine is showing a transaction decline error.',
                     'Qual o estado do meu terminal com erro de transacao?',
                     'Qual o estado do meu terminal e qual a taxa do Crediario?',
                     'Nao quero consultar o status do meu terminal',
                     'Como consultar o status do meu terminal?'):
            with self.subTest(text=text):
                self.assertFalse(terminal_status_query(text))

    def test_unknown_identity_never_gets_fixture(self):
        body=self.client.post('/chat',json={'message':'Qual o estado do meu terminal?','user_id':'unknown'}).json()
        self.assertNotIn('DEMO-A-001',body['answer'])

    def test_public_only_plan_unchanged_without_support(self):
        text='Qual o estado do meu terminal? Como funciona o Crediario?'
        self.assertEqual(len(knowledge_tasks(text,support_answered=False)),2)
