import unittest
from app.knowledge import KnowledgeRag
from app.contracts import Entrada
class ComparisonTest(unittest.TestCase):
 def test_two_manuals(self):
  agent=KnowledgeRag.from_directory('corpus_publico')
  for query in ("What's the difference between the Get Classica and the Get Smart?",'Compare Get Smart and Get Classica'):
   with self.subTest(query=query):
    result=agent.responder(Entrada(message=query,user_id='demo_A'),())
    self.assertEqual(result.status,'evidencias');self.assertEqual(len(result.fontes),2)
    self.assertTrue(all(url.endswith('.pdf') for url in result.fontes))
    self.assertIn('ausência de um recurso no trecho não prova',result.texto);self.assertNotIn('R$',result.texto)
 def test_unknown_product_not_fabricated(self):
  result=KnowledgeRag.from_directory('corpus_publico').responder(Entrada(message='Compare produtos Getnet ZebraX QuantumY',user_id='demo_A'),())
  self.assertEqual(result.status,'sem_evidencia')
