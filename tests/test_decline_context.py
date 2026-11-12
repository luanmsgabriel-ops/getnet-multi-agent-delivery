import unittest
from app.knowledge import KnowledgeRag
from app.support import SupportSintetico
from app.contracts import Entrada
class DeclineContext(unittest.TestCase):
 def test_general_status_not_network_diagnosis(self):
  agent=KnowledgeRag.from_directory('corpus_publico')
  for query in ('My card machine is showing a transaction decline error.','Minha venda no cartao foi negada','transaction declined'):
   r=agent.responder(Entrada(message=query,user_id='demo_A'),())
   self.assertEqual(r.status,'evidencias');self.assertIn('status-das-minhas-vendas',r.fontes[0]);self.assertIn('não identifica o motivo específico',r.texto)
   self.assertNotIn('erro-adq',r.fontes[0])
 def test_support_no_misleading_terminal_check(self):
  r=SupportSintetico().responder(Entrada(message='My card machine transaction declined',user_id='demo_A'),())
  self.assertEqual(r.tool_traces,[]);self.assertNotIn('online',r.texto);self.assertIn('nao determina',r.texto)
