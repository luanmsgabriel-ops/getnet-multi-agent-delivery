import os,unittest
from unittest.mock import patch,Mock
from fastapi.testclient import TestClient
from app.main import create_app
class EchoEvidenceGenerator:
 def generate(self,question,evidence):
  text=evidence[0]['text']
  return {'answer':text,'citations':[{'evidence_id':0,'quote':text}]}
class HTTPGeneration(unittest.TestCase):
 def test_injected_generator_full_api(self):
  client=TestClient(create_app(mode='generated',generator=EchoEvidenceGenerator(),enable_web=False))
  result=client.post('/chat',json={'message':'How many installments can I split a sale into with the crediário?','user_id':'demo_A'}).json()
  self.assertEqual(result['status'],'evidencias');self.assertEqual(result['modo'],'gerado');self.assertTrue(result['sources'])
 def test_no_implicit_network(self):
  with patch.dict(os.environ,{},clear=True),self.assertRaises(ValueError):create_app(mode='generated')
 def test_missing_configuration_fails_closed(self):
  with patch.dict(os.environ,{'GETNET_ALLOW_MODEL_NETWORK':'1'},clear=True),self.assertRaises(ValueError):create_app(mode='generated')
 def test_invalid_provider_no_constructor(self):
  with patch.dict(os.environ,{'GETNET_ALLOW_MODEL_NETWORK':'1','GETNET_MODEL':'other:demo','OPENROUTER_API_KEY':'fake-test'},clear=True),patch('app.rag.generation.PydanticGenerator') as factory:
   with self.assertRaises(ValueError):create_app(mode='generated')
   factory.assert_not_called()
 def test_unknown_query_does_not_generate(self):
  generator=Mock();client=TestClient(create_app(mode='generated',generator=generator,enable_web=False))
  result=client.post('/chat',json={'message':'Como funciona ZebraQuantum?', 'user_id':'demo_A'}).json()
  self.assertEqual(result['status'],'limitado');generator.generate.assert_not_called()
