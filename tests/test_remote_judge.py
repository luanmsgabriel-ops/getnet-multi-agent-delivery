"""No paid network: verifies real adapter envelope and shared reservations."""
import json,tempfile,unittest
from pathlib import Path
import httpx
from app.agentic_client import Budget,ModelUnavailable
from evals.remote_judge import RemoteJudge

class RemoteJudgeTest(unittest.TestCase):
 def test_remote_contract_and_reconciliation(self):
  with tempfile.TemporaryDirectory() as tmp:
   budget=Budget(Path(tmp)/'b.db',max_calls=2,max_cost='1',initialize=True)
   bodies=[]
   def handler(request):
    body=json.loads(request.content);bodies.append(body)
    self.assertEqual(budget.max_calls,2)
    with budget.db() as db:self.assertEqual(db.execute('SELECT status FROM calls').fetchone()[0],'reserved')
    return httpx.Response(200,json={'usage':{'cost':'.0001'},'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]})
   judge=RemoteJudge(key='SYNTHETIC_TEST_KEY',budget=budget,transport=httpx.MockTransport(handler))
   self.assertEqual(judge.decide('public rubric',{'question':'public'}, {'type':'object','properties':{},'additionalProperties':False}),{})
   self.assertEqual(bodies[0]['model'],'openai/gpt-4.1-mini')
   self.assertEqual(bodies[0]['provider']['only'],['OpenAI']);self.assertFalse(bodies[0]['provider']['allow_fallbacks'])
   self.assertEqual(bodies[0]['max_tokens'],2000)
   # Compact nested JSON changes whitespace only, keeping the reservation bound.
   self.assertEqual(bodies[0]['messages'][1]['content'],'{"question":"public"}')
   self.assertNotIn('reasoning',bodies[0])
   self.assertEqual(bodies[0]['provider']['max_price'],{'prompt':0.4,'completion':1.6})
   with budget.db() as db:self.assertEqual(db.execute('SELECT status FROM calls').fetchone()[0],'billed')
 def test_oversize_payload_stops_before_reservation(self):
  with tempfile.TemporaryDirectory() as tmp:
   budget=Budget(Path(tmp)/'b.db',max_calls=2,max_cost='1',initialize=True)
   judge=RemoteJudge(key='SYNTHETIC_TEST_KEY',budget=budget,transport=httpx.MockTransport(lambda r:self.fail('network')))
   with self.assertRaises(ModelUnavailable):judge.decide('policy',{'text':'x'*80000},{'type':'object'})
   with budget.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM calls').fetchone()[0],0)

class CompactReferenceTransport(unittest.TestCase):
 def test_wire_ids_are_short_and_canonical_ids_restored_without_packet_mutation(self):
  from evals.judging import make_packet,judge
  refs=[{'source':'https://example.org/manual','text':'Use pano seco.','evidence_id':letter*64} for letter in 'abc']
  packet=make_packet({'message':'Como limpar?'},{'answer':'Use pano seco.','status':'evidencias','sources':['https://example.org/manual']},refs,opaque_id='opaque_case')
  original=json.dumps(packet,sort_keys=True)
  with tempfile.TemporaryDirectory() as tmp:
   budget=Budget(Path(tmp)/'b.db',max_calls=1,max_cost='1',initialize=True)
   def handler(request):
    body=json.loads(request.content);wire=json.loads(body['messages'][1]['content'])
    self.assertEqual([r['evidence_id'] for r in wire['references']],['e1','e2','e3'])
    schema=body['response_format']['json_schema']['schema']['properties']['citations']
    self.assertEqual(schema['maxItems'],3);self.assertEqual(schema['items']['enum'],['e1','e2','e3'])
    self.assertEqual(wire['answer_quote_choices'],[{'id':'a1','text':'Use pano seco.'}])
    self.assertEqual(body['response_format']['json_schema']['schema']['properties']['answer_quotes']['items']['enum'],['a1'])
    verdict={k:'pass' for k in ['correctness','relevance','completeness','groundedness','usefulness']}
    verdict.update(outcome='answer',reason='Texto controlado.',citations=['e2'],answer_quotes=['a1'],
                   claim_checks=[{'answer_quote':'Use pano seco.','reference_quote':'Use pano seco.',
                                  'evidence_id':'e2','assessment':'supported'}])
    return httpx.Response(200,json={'usage':{'cost':'.0001'},'choices':[{'finish_reason':'stop','message':{'content':json.dumps(verdict)}}]})
   result=judge(packet,RemoteJudge(key='SYNTHETIC',budget=budget,transport=httpx.MockTransport(handler)))
   self.assertEqual(result.verdict.claim_checks[0].evidence_id,'b'*64)
   self.assertEqual(result.verdict.answer_quotes,['Use pano seco.']);self.assertEqual(result.verdict.citations,['b'*64]);self.assertEqual(json.dumps(packet,sort_keys=True),original)
 def test_stage_profile_changes_only_explicit_model_stage_not_budget_or_schema(self):
  from app.agentic_client import SupervisorClient
  with tempfile.TemporaryDirectory() as tmp:
   budget=Budget(Path(tmp)/'b.db',max_calls=2,max_cost='1',initialize=True);bodies=[]
   def handler(request):
    bodies.append(json.loads(request.content))
    return httpx.Response(200,json={'usage':{'cost':'.0001'},'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]})
   client=SupervisorClient(key='SYNTHETIC',model='synthetic',prices={'prompt':'.00000025','completion':'.000002'},budget=budget,max_output=3500,reasoning_effort='medium',stage_reasoning={'RequestPlan':'low','Draft':'low'},transport=httpx.MockTransport(handler))
   for title in ['RequestPlan','Verdict']:client.decide('policy',{'request':'public'}, {'title':title,'type':'object','properties':{}},timeout=1)
   self.assertEqual([b['reasoning']['effort'] for b in bodies],['low','medium'])
   self.assertEqual([b['max_tokens'] for b in bodies],[3500,3500])
   with budget.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM calls').fetchone()[0],2)
