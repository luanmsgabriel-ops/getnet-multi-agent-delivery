import unittest
from fastapi.testclient import TestClient
from app.main import create_app
class WifiFlow(unittest.TestCase):
    def setUp(self):self.c=TestClient(create_app(mode='rag',enable_web=False))
    def test_compound_english_with_real_public_corpus(self):
        r=self.c.post('/chat',json={'message':'My card machine connection internet what should I do?','user_id':'demo_A'}).json()
        self.assertEqual(r['route'],'support_knowledge');self.assertEqual(r['status'],'evidencias')
        self.assertTrue(r['simulated_data']);self.assertTrue(any('como-configurar-o-wi-fi' in s for s in r['sources']))
        self.assertEqual([e['ferramenta'] for e in r['eventos'] if e['ferramenta']],['consultar_terminal'])
        self.assertIn('Nenhuma configuracao ou operacao foi realizada',r['answer'])
    def test_independent_portuguese(self):
        for q in ['como configurar wi-fi maquininha','conexao internet maquininha']:
            r=self.c.post('/chat',json={'message':q,'user_id':'demo_A'}).json()
            from app.knowledge import KnowledgeRag
            from app.contracts import Entrada
            result=KnowledgeRag.from_directory('corpus_publico').responder(Entrada(message=q,user_id='demo_A'),())
            self.assertTrue(any('como-configurar-o-wi-fi' in source for source in result.fontes))
    def test_account_denied_before_public_guide(self):
        r=self.c.post('/chat',json={'message':'Como configurar minha maquininha wi-fi?','user_id':'demo_B'}).json()
        self.assertEqual(r['status'],'recusado');self.assertEqual(r['sources'],[])
    def test_decline_not_misdiagnosed_as_wifi(self):
        r=self.c.post('/chat',json={'message':'My card machine is showing a transaction decline error.','user_id':'demo_A'}).json()
        self.assertEqual(r['status'],'evidencias');self.assertTrue(all('status-das-minhas-vendas' in u for u in r['sources']));self.assertIn('não identifica o motivo específico',r['answer'])
