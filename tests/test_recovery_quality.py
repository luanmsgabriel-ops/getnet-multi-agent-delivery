import unittest
from pathlib import Path
from unittest.mock import Mock
from app.knowledge import KnowledgeRag, KnowledgeGenerated
from app.contracts import Entrada

class RecoveryQualityTest(unittest.TestCase):
    def setUp(self):
        self.index=KnowledgeRag.from_directory(Path(__file__).resolve().parents[1]/'corpus_publico').index
    def test_comparison_has_physical_controls_and_smart(self):
        rows=self.index.search("What's the difference between the Get Classica and the Get Smart?")['candidates']
        self.assertTrue(any('Confirma as opera' in r['text'] and 'Classica' in r['title'] for r in rows))
        self.assertTrue(any('touchscreen' in r['text'] for r in rows))
    def test_decline_generated_retains_safe_triage(self):
        rows=self.index.search('transacao negada cartao')['candidates']
        generator=Mock()
        generator.generate.return_value={'answer':rows[0]['text'], 'citations':[{'evidence_id':0,'quote':rows[0]['text']}]}
        result=KnowledgeGenerated(self.index,generator).responder(Entrada(message='My card machine is showing a transaction decline error.',user_id='demo_A'),())
        self.assertEqual(result.status,'evidencias')
        self.assertIn('código de erro',result.texto)
        self.assertIn('não identifica o motivo específico',result.texto)
        self.assertIn('sem dados do cartão, senhas ou códigos de autenticação',result.texto)
        self.assertNotIn('Envie sua senha',result.texto)
    def test_decline_failed_citation_uses_safe_evidence(self):
        generator=Mock();generator.generate.return_value={'answer':'Resposta', 'citations':[{'evidence_id':0,'quote':'INVALID_QUOTE'}]}
        result=KnowledgeGenerated(self.index,generator).responder(Entrada(message='transaction decline error',user_id='demo_A'),())
        self.assertEqual(result.status,'evidencias');self.assertEqual(result.modo,'extrativo')
        self.assertNotIn('INVALID_QUOTE',result.texto);self.assertIn('código de erro',result.texto)

    def test_pix_account_requirement_has_direct_official_evidence(self):
        rows=self.index.search('Do I need a bank account to receive my sales via Pix?')['candidates']
        self.assertTrue(any(r['source']=='https://site.getnet.com.br/duvidas/' and 'conta de recebimento desejada' in r['text'] and 'conta de pagamento' in r['text'] for r in rows))
