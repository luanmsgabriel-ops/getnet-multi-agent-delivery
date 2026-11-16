"""Focused mechanics for failures observed in the original ten real responses.
No model semantics are proved by the scripted client below.
"""
import unittest
from pathlib import Path
from app.rag.runtime import configured_knowledge
from app.rag.obligations import request_plan_schema,validate_request_plan
from app.rag.grounding import GroundedSynthesizer,evidence_ref,expired_schedule_claim
from app.agentic_capabilities import Capabilities
from app.contracts import RespostaEspecialista

ROOT=Path(__file__).resolve().parents[1]
class OriginalRequestBoundaries(unittest.TestCase):
 def test_simple_requests_do_not_offer_the_whole_question_as_constraint(self):
  for q in ['Do I need a bank account to receive my sales via Pix?',
            'How does receivables advance (antecipação) work with Getnet?',
            'My card machine is showing a transaction decline error.']:
   schema=request_plan_schema(q)
   self.assertEqual(schema['properties']['constraints']['maxItems'],0)
   self.assertEqual(schema['properties']['user_context']['maxItems'],0)
   self.assertEqual(validate_request_plan(q,{'obligations':[{'id':'r1','request_span':q}]}).constraints,[])
   with self.assertRaises(ValueError):
    validate_request_plan(q,{'obligations':[{'id':'r1','request_span':q}],'constraints':[q]})
 def test_original_anticipation_retrieves_frozen_required_groups(self):
  local=configured_knowledge(ROOT/'corpus_publico',env={})
  rows=local._retrieve('How does receivables advance (antecipação) work with Getnet?')['candidates']
  text=' '.join(c['text'] for c in rows)
  self.assertEqual(len(rows),3)
  for phrase in ['antes do prazo original','mediante uma taxa','elegíveis','simular a antecipação']:
   self.assertIn(phrase,text)
 def test_unknown_network_cannot_be_complete_under_permissive_verdict(self):
  q="My card machine won't connect to the internet, what should I do?"
  local=configured_knowledge(ROOT/'corpus_publico',env={})
  rows=local._retrieve(q)['candidates'];e=next(c for c in rows if 'Procurar Redes' in c['text']);seen=[]
  class Script:
   def decide(self,system,payload,schema,**kw):
    seen.append(payload)
    if schema['title']=='RequestPlan':return {'obligations':[{'id':'r1','request_span':q}]}
    if schema['title']=='Draft':return {'claims':[{'text':'Se a conexão for Wi-Fi, selecione Procurar Redes na opção Wi-Fi.','citations':[{'evidence_id':evidence_ref(e).evidence_id}],'answers':['r1']}],'gaps':[]}
    return {'claims':[{'claim_index':0,'supported':True}],'scope_respected':True,'coverage_complete':True,'gaps_supported':True,'obligations':[{'obligation_id':'r1','claim_indices':[0],'status':'covered'}]}
  text,sources,claims,complete=GroundedSynthesizer(Script(),evidence_filter=local.scopes.compatible).synthesize(q,rows)
  self.assertFalse(complete);self.assertTrue(claims);self.assertIn('Se a conexão for Wi-Fi',text)
  self.assertTrue(seen[1]['applicability_requires_clarification'])
  self.assertTrue(seen[2]['applicability_requires_clarification'])
 def test_past_transition_is_not_current_change(self):
  self.assertTrue(expired_schedule_claim('A cobrança passa a ser por Link a partir de 15/01/2026.','2026-11-15'))
  self.assertFalse(expired_schedule_claim('A fonte anunciava a mudança para 15/01/2026.','2026-11-15'))
 def test_weather_observation_has_no_documentary_failure_label(self):
  class Public:
   def answer(self,q):return RespostaEspecialista(texto='Previsão datada para Porto Alegre.',status='evidencias',fontes=['https://api.open-meteo.com/v1/forecast'],modo='extrativo')
  obs=Capabilities(object(),public=Public(),env={}).run('knowledge_public',"What's the weather forecast in Porto Alegre tomorrow?",owner='cliente1988',goal_id='g1',observation_id='o1')
  self.assertEqual(obs.status,'complete');self.assertEqual(obs.limitation,'')
  self.assertIsNone(obs.evidence_coverage)
 def test_initial_supervisor_receives_missing_incident_context_rule(self):
  from app.agentic import Supervisor
  from test_weights23_integration import Capture
  from test_agentic import FakeCapabilities
  script=Capture()
  Supervisor(script,FakeCapabilities()).executar({'message':'My card machine is showing a transaction decline error.','user_id':'cliente1988'})
  self.assertIn('peça primeiro o dado indispensável',script.systems[0])
  self.assertIn('evidence_coverage=null',script.systems[0])
 def test_receivables_contract_and_selected_direct_flow(self):
  # Script proves the interface and execution, not a real model's choice.
  from unittest.mock import Mock
  from app.agentic import Supervisor
  from test_weights23_integration import Capture
  from test_agentic import consult,finish
  q="When will the money from yesterday's sales be deposited?"
  local=Mock()
  script=Capture(consult('support_receivables',q),finish())
  result=Supervisor(script,Capabilities(local)).executar({'message':q,'user_id':'cliente1988'})
  self.assertIn('selecione diretamente esta capacidade, sem consulta documental prévia',script.systems[0])
  self.assertIn('Explicações gerais sobre prazos, regras ou antecipação pertencem a knowledge_getnet',script.systems[0])
  self.assertIn('Negação de consulta continua vinculante',script.systems[0])
  self.assertEqual(local.mock_calls,[])
  observations=script.payloads[1]['observations']
  self.assertEqual(len(observations),1)
  self.assertEqual(observations[0]['capability'],'support_receivables')
  self.assertTrue(observations[0]['simulated'])
  self.assertEqual(result.agentic.stop,'finish')
  self.assertEqual(result.agentic.coverage[0].status,'answered')
  self.assertNotIn('cliente1988',str(script.payloads))
 def test_final_connect_error_preserves_useful_answer_without_retry(self):
  import json,tempfile
  from pathlib import Path
  import httpx
  from app.agentic import Supervisor
  from app.agentic_client import Budget,SupervisorClient
  from test_agentic import FakeCapabilities,consult
  q='Do I need a bank account to receive my sales via Pix?'
  requests=[]
  async def transport(request):
   requests.append(request)
   if len(requests)==1:
    return httpx.Response(200,json={'usage':{'cost':.001},'choices':[{'finish_reason':'stop','message':{'content':json.dumps(consult(query=q))}}]})
   raise httpx.ConnectError('private transport detail',request=request)
  with tempfile.TemporaryDirectory() as folder:
   budget=Budget(Path(folder)/'budget.db',initialize=True,max_calls=3,max_cost='.50')
   client=SupervisorClient(key='SYNTHETIC',model='synthetic',prices={'prompt':'.00000025','completion':'.000002'},budget=budget,transport=httpx.MockTransport(transport))
   caps=FakeCapabilities(text='A chave Pix deve estar vinculada à conta de recebimento.')
   result=Supervisor(client,caps).executar({'message':q,'user_id':'cliente1988'})
   self.assertEqual(len(requests),2)
   self.assertEqual(len(caps.calls),1)
   self.assertEqual(result.agentic.stop,'model_or_decision_unavailable')
   self.assertNotEqual(result.agentic.coverage[0].status,'answered')
   self.assertIn('A chave Pix deve estar vinculada',result.answer)
   self.assertNotIn('private transport detail',result.answer)
   self.assertNotEqual(result.status,'evidencias')
   with budget.db() as db:
    self.assertEqual(db.execute('SELECT status FROM calls ORDER BY id').fetchall(),[('billed',),('reserved',)])
if __name__=='__main__':unittest.main()
