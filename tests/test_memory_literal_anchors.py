"""Explicit provenance anchors; no model calls or semantic-equivalence oracle."""
import unittest
from app.agentic_contracts import Goal,decision_schema
from app.dialogue_memory import quote_coverage
import test_memory_final_points as memory_tests
from test_memory_final_points import INITIAL,CTX02,USER
from test_agentic import Script,FakeCapabilities,consult,finish

TID='t_'+'a'*32
HISTORY=[{'turn_id':TID,'request':INITIAL,'outcome':{}}]

class LiteralAnchors(unittest.TestCase):
    def goal(self,**overrides):
        values=dict(id='g1',request='A Get Smart do caixa azul esta sem internet. Como verificar a conexao?',context_turn_id=TID,current_request_quote=CTX02)
        values.update(overrides);return Goal(**values)
    def test_reformulation_rebuilt_only_from_literal_sources(self):
        current,covered,goals=quote_coverage([self.goal()],HISTORY,CTX02)
        self.assertEqual(goals[0].request,INITIAL+' '+CTX02)
        self.assertTrue(all(covered));self.assertIsNone(goals[0].current_request_quote)
    def test_invented_interpretation_never_becomes_executable(self):
        _,_,goals=quote_coverage([self.goal(request='Invented user identity and authorized transfer')],HISTORY,CTX02)
        self.assertNotIn('transfer',goals[0].request)
        self.assertEqual(goals[0].request,INITIAL+' '+CTX02)
    def test_invalid_or_partial_current_anchor_rejected(self):
        for anchor in ['Get Smart',INITIAL,CTX02+' Ignore limits']:
            with self.subTest(anchor=anchor),self.assertRaises(ValueError):
                quote_coverage([self.goal(current_request_quote=anchor)],HISTORY,CTX02)
    def test_unknown_missing_or_old_only_binding_rejected(self):
        for tid in [None,'t_'+'b'*32]:
            with self.subTest(tid=tid),self.assertRaises(ValueError):
                quote_coverage([self.goal(context_turn_id=tid)],HISTORY,CTX02)
        with self.assertRaises(ValueError):quote_coverage([self.goal()],[],CTX02)
    def test_unanchored_paraphrase_stays_rejected(self):
        with self.assertRaises(ValueError):quote_coverage([self.goal(current_request_quote=None)],HISTORY,CTX02)
    def test_negative_instruction_not_dropped(self):
        current=CTX02+' Nao consulte meus recebiveis.'
        _,covered,goals=quote_coverage([self.goal(current_request_quote=current)],HISTORY,current)
        self.assertTrue(all(covered));self.assertTrue(goals[0].request.endswith(current))
    def test_combined_anchor_limit_fails_without_truncating(self):
        history=[{'turn_id':TID,'request':'x'*990,'outcome':{}}]
        with self.assertRaisesRegex(ValueError,'exceeds limit'):
            quote_coverage([self.goal()],history,CTX02)
    def test_schema_exposes_separate_current_anchor(self):
        schema=decision_schema(initial=True)['$defs']['Goal']
        self.assertIn('current_request_quote',schema['properties'])
        self.assertFalse(schema['additionalProperties'])
        self.assertIn({'type':'null'},schema['properties']['current_request_quote']['anyOf'])

class AnchoredRoute(unittest.TestCase):
    setUp=memory_tests.MemoryFinalPoints.setUp
    client=memory_tests.MemoryFinalPoints.client
    post=memory_tests.MemoryFinalPoints.post
    def test_r2_real_proposal_with_explicit_anchor_reaches_clarification(self):
        def corrected(payload):
            return {'goals':[dict(id='g1',request='A Get Smart do caixa azul esta sem internet. Como verificar a conexao?',context_turn_id=payload['conversation'][-1]['turn_id'],current_request_quote=payload['request'])], 'action':'clarify','goal_id':'g1','reason':'need_guidance','clarification':'connectivity'}
        script=Script(consult(query=INITIAL),finish(),corrected)
        c=self.client(script);sid=self.post(c,INITIAL).json()['session_id']
        response=self.post(c,CTX02,sid).json()
        self.assertEqual(response['agentic']['stop'],'clarify')
        self.assertEqual(response['agentic']['goals'][0]['request'],INITIAL+' '+CTX02)
    def test_model_query_interpretation_is_not_forwarded(self):
        def corrected(payload):
            proposal=consult(query='untrusted model interpretation')
            proposal['goals'][0].update(context_turn_id=payload['conversation'][-1]['turn_id'],current_request_quote=payload['request'])
            return proposal
        script=Script(consult(query=INITIAL),finish(),corrected,finish())
        caps=FakeCapabilities();c=self.client(script,caps);sid=self.post(c,INITIAL).json()['session_id']
        response=self.post(c,CTX02,sid).json()
        self.assertEqual(response['agentic']['stop'],'finish')
        self.assertEqual(response['agentic']['goals'][0]['request'],INITIAL+' '+CTX02)
        self.assertEqual(caps.calls[-1][1],INITIAL+' '+CTX02)
        self.assertEqual(script.payloads[-1]['goals'][0]['request'],INITIAL+' '+CTX02)
        self.assertIsNone(script.payloads[-1]['goals'][0]['current_request_quote'])
        self.assertFalse(self.store.read(USER,sid)[1]['facts'])
