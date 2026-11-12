import unittest
from app.knowledge import KnowledgeRag
from app.rag.core import query_tokens
from app.contracts import Entrada
class BilingualRetrieval(unittest.TestCase):
    def setUp(self):self.k=KnowledgeRag.from_directory('corpus_publico')
    def test_independent_installment_queries(self):
        for q in ['installments crediario limit','crediario interest installments','maximum instalments crediario']:
            r=self.k.responder(Entrada(message=q,user_id='demo_A'),())
            self.assertEqual(r.status,'evidencias');self.assertIn('https://site.getnet.com.br/crediario/',r.fontes)
            self.assertTrue('emissor' in r.texto.lower() or 'juros' in r.texto.lower())
    def test_domain_terms_not_whole_prompts(self):
        self.assertEqual(query_tokens('How many installments can I split a sale into?'),{'parcelas','dividir','venda'})
    def test_negative_unrelated(self):
        for q in ['astronomy quantum asteroid galaxy','weather rainfall humidity tomorrow']:
            self.assertEqual(self.k.responder(Entrada(message=q,user_id='demo_A'),()).status,'limitado')
