import unittest
from app.knowledge import KnowledgeRag
from app.contracts import Entrada
class OfficialExpansion(unittest.TestCase):
    def setUp(self):self.k=KnowledgeRag.from_directory('corpus_publico')
    def test_independent_whatsapp_queries(self):
        for q in ['link pagamento whatsapp','payment link whatsapp','WhatsApp Pay descontinuado']:
            r=self.k.responder(Entrada(message=q,user_id='demo_A'),())
            self.assertEqual(r.status,'evidencias');self.assertTrue(any('descontinuacao-whatsapp-business' in x for x in r.fontes))
            self.assertIn('15/01/2026',r.texto)
    def test_independent_advance_queries(self):
        for q in ['antecipar vendas app','antecipacao valores taxas','antecipacao getnet']:
            r=self.k.responder(Entrada(message=q,user_id='demo_A'),())
            self.assertEqual(r.status,'evidencias');self.assertTrue(any('antecipacao-de-venda' in x for x in r.fontes))
    def test_new_snapshots_provenance(self):
        entries=[e for e in self.k.index.entries if 'descontinuacao-whatsapp-business' in e['source'] or 'antecipacao-de-venda' in e['source']]
        self.assertEqual(len(entries),3)
        self.assertTrue(all(e['market']=='BR' and e['captured_at'] for e in entries))
    def test_financial_question_not_account_lookup(self):
        r=self.k.responder(Entrada(message='antecipacao getnet',user_id='demo_B'),())
        self.assertEqual(r.modo,'extrativo')
        for term in ('crédito', 'simular', 'taxas', 'condições aplicáveis', 'Não solicitei'):
            self.assertIn(term, r.texto)
        self.assertEqual(r.tool_traces,[])
