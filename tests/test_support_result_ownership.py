import unittest
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor
from app.support import SupportSintetico,Principal,DEMO_PRINCIPAL
from app.contracts import Entrada
class ResultOwnership(unittest.TestCase):
 def test_valid_schema_wrong_tenant_refused(self):
  tools=Mock();tools.principal=DEMO_PRINCIPAL
  tools.consultar_terminal.return_value={'simulated':True,'terminal_id':'DEMO-B-001','status':'offline'}
  result=SupportSintetico(tools=tools).responder(Entrada(message='meu terminal',user_id='demo_A'),())
  self.assertEqual(result.status,'recusado');self.assertNotIn('DEMO-B',result.texto)
  self.assertEqual(result.tool_traces[0].status,'falha')
 def test_parallel_isolation(self):
  a=SupportSintetico();b=SupportSintetico(Principal('demo_B','loja_ficticia_B',frozenset({'terminal:read'})))
  def query(i):
   agent,subject,terminal=(a,'demo_A','DEMO-A-001') if i%2==0 else (b,'demo_B','DEMO-B-001')
   result=agent.responder(Entrada(message='meu terminal',user_id=subject),())
   self.assertIn(terminal,result.texto)
   self.assertNotIn('DEMO-B' if i%2==0 else 'DEMO-A',result.texto)
  with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(query,range(40)))
 def test_user_identifier_does_not_authenticate(self):
  # demo_A e apenas fixture publica: nao e credencial nem prova de identidade.
  tools=Mock();tools.principal=DEMO_PRINCIPAL
  for subject in ('cliente1988','demo_B','admin'):
   result=SupportSintetico(tools=tools).responder(Entrada(message='meu terminal',user_id=subject),())
   self.assertEqual(result.status,'recusado')
  tools.consultar_terminal.assert_not_called()
