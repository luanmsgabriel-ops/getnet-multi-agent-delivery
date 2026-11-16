import unittest,copy,json
from evals.structured_judge_wire import prepare,restore,segments
from evals.judging import make_packet,QuotedVerdict,validate_verdict
class Structural(unittest.TestCase):
 def setUp(self):
  self.p=make_packet({'message':'Como limpar?'},{'answer':'Use pano seco.','status':'ok','sources':[]},[
   {'source':'https://example.org/a','text':'Use pano seco. Nunca molhe.','evidence_id':'sourceA'},
   {'source':'https://example.org/b','text':'Outro texto.','evidence_id':'sourceB'}],opaque_id='control_case')
  self.policy,self.w,self.s,self.state=prepare('policy',self.p,QuotedVerdict.model_json_schema())
  self.v=dict(segment_audit={'a1':dict(kind='product_claim',assessment='supported',evidence_segments=['e1s1'],temporal_scope='none')},outcome='answer',input_need='not_requested',has_factual_claims=True,coverage=[],temporal_checks=[],answer_quotes=['a1'],reason='Supported text.',
    claim_checks=[dict(answer_quote='a1',reference_quote='e1s1',evidence_id='e1',assessment='supported')],
    correctness='pass',relevance='pass',completeness='pass',groundedness='pass',usefulness='pass',citations=['e1'])
 def test_literal_restoration_and_validation(self):
  v=restore(self.v,self.state);self.assertEqual(v['claim_checks'][0]['reference_quote'],'Use pano seco.')
  self.assertEqual(validate_verdict(self.p,v,require_answer_quotes=True).status,'assessed')
 def test_ownership(self):
  self.v['claim_checks'][0]['evidence_id']='e2'
  with self.assertRaises(ValueError):restore(self.v,self.state)
 def test_unknown_quote(self):
  self.v['claim_checks'][0]['reference_quote']='invented'
  with self.assertRaises(ValueError):restore(self.v,self.state)
 def test_copied_quote_not_wire_id(self):
  self.v['claim_checks'][0]['reference_quote']='Use pano seco.'
  with self.assertRaises(ValueError):restore(self.v,self.state)
 def test_temporal_contradiction_rejected_not_regraded(self):
  self.v['temporal_checks']=[dict(answer_quote='a1',reference_quote='e1s1',relation='past_event_as_current')]
  with self.assertRaises(ValueError):restore(self.v,self.state)
  self.assertEqual(self.v['correctness'],'pass')
 def test_nonfactual_requires_empty_checks(self):
  self.v['has_factual_claims']=False
  with self.assertRaises(ValueError):restore(self.v,self.state)
 def test_question_nonassessable(self):
  self.v['segment_audit']['a1'].update(kind='question',assessment='not_factual',evidence_segments=[])
  self.v.update(has_factual_claims=False,claim_checks=[],groundedness='not_assessable',outcome='clarify',input_need='necessary_missing')
  self.assertEqual(restore(self.v,self.state)['outcome'],'clarify')
 def test_partial_coverage_does_not_change_truth(self):
  self.v.update(completeness='partial',coverage=[dict(requested_item='another requested item',state='missing')])
  v=restore(self.v,self.state)
  self.assertEqual(v['groundedness'],'pass');self.assertEqual(v['completeness'],'partial')
 def test_no_packet_mutation_or_expected_label(self):
  before=json.dumps(self.p,sort_keys=True)
  prepare('policy',self.p,QuotedVerdict.model_json_schema())
  self.assertEqual(before,json.dumps(self.p,sort_keys=True))
  self.assertNotIn('expect',self.w)
 def test_exact_segments_and_length(self):
  text='Olá. Um trecho! Outra linha?\n'+('abc '*500)
  self.assertTrue(all(t in text and len(t)<=900 for t in segments(text)))
 def test_schema_act_first_and_quotes_enum(self):
  self.assertEqual(next(iter(self.s['properties'])),'segment_audit')
  self.assertNotIn('ClaimCheck',self.s.get('$defs',{}))
  self.assertEqual(self.s['properties']['segment_audit']['properties']['a1']['properties']['evidence_segments']['items']['enum'],list(self.state[2]))
 def test_claim_contradiction_still_rejected(self):
  self.v['claim_checks'][0]['assessment']='contradicted'
  self.assertEqual(validate_verdict(self.p,restore(self.v,self.state)).status,'inconclusive')
 def test_absent_reference_packet(self):
  p=copy.deepcopy(self.p);p['references']=[]
  _,w,s,state=prepare('policy',p,QuotedVerdict.model_json_schema())
  self.assertEqual(s['properties']['citations']['maxItems'],0)
 def test_privacy_validator_unchanged(self):
  bad=copy.deepcopy(self.p);bad['question']='cpf 12345678901'
  self.assertEqual(validate_verdict(bad,restore(self.v,self.state)).error_code,'invalid_packet')

 def test_audit_all_segments_required(self):
  self.v['segment_audit']={}
  with self.assertRaises(ValueError):restore(self.v,self.state)
 def test_audit_product_claim_needs_check(self):
  self.v['claim_checks']=[]
  with self.assertRaises(ValueError):restore(self.v,self.state)
 def test_known_marker_date_is_safely_delimited(self):
  self.v['reason']='See e1s1 (2026-11-15).'
  v=restore(self.v,self.state)
  self.assertEqual(v['reason'],'See [e1s1] (2026-11-15).')
  self.assertEqual(validate_verdict(self.p,v).status,'assessed')
 def test_unknown_marker_numeric_data_still_blocked(self):
  self.v['reason']='Account 123456789012345.'
  self.assertEqual(validate_verdict(self.p,restore(self.v,self.state)).status,'inconclusive')
 def test_current_transition_dates_visible_across_segments(self):
  p=copy.deepcopy(self.p);p['references'][0]['text']='Use the service. Rollout ended 15/01/2026.';p['reference_date']='2026-11-16'
  _,w,_,_=prepare('x',p,QuotedVerdict.model_json_schema())
  self.assertEqual(w['source_date_candidates'][0]['relative_to_reference_date'],'before')

 def test_omission_does_not_rewrite_supported_fact_as_false(self):
  self.v['correctness']='partial';self.v['completeness']='partial'
  self.assertEqual(restore(self.v,self.state)['correctness'],'pass')
 def test_clear_contradiction_still_fails(self):
  self.v['segment_audit']['a1']['assessment']='contradicted'
  self.v['claim_checks'][0]['assessment']='contradicted';self.v['groundedness']='fail'
  self.assertEqual(restore(self.v,self.state)['correctness'],'fail')
 def test_ambiguity_abstains_not_pass_or_fail(self):
  self.v['segment_audit']['a1'].update(assessment='ambiguous',temporal_scope='uncertain')
  self.v['claim_checks'][0]['assessment']='insufficient'
  v=restore(self.v,self.state)
  self.assertEqual(v['correctness'],'not_assessable');self.assertEqual(v['groundedness'],'not_assessable')
  self.assertEqual(validate_verdict(self.p,v).status,'assessed')
 def test_ambiguity_not_allowed_as_hidden_supported_check(self):
  self.v['segment_audit']['a1'].update(assessment='ambiguous',temporal_scope='uncertain')
  with self.assertRaises(ValueError):restore(self.v,self.state)

 def test_ambiguity_cannot_hide_separate_contradiction(self):
  amap,aliases,rmap=self.state
  state=({**amap,'a2':'Another statement.'},aliases,rmap)
  self.v['segment_audit']['a1']['assessment']='contradicted'
  self.v['claim_checks'][0]['assessment']='contradicted'
  self.v['segment_audit']['a2']=dict(kind='product_claim',assessment='ambiguous',evidence_segments=['e1s1'],temporal_scope='uncertain')
  self.v['claim_checks'].append(dict(answer_quote='a2',evidence_id='e1',reference_quote='e1s1',assessment='insufficient'))
  v=restore(self.v,state)
  self.assertEqual(v['correctness'],'partial');self.assertEqual(v['groundedness'],'partial')

class EmptyReferenceContract(unittest.TestCase):
 setUp=Structural.setUp
 def empty(self):
  p=copy.deepcopy(self.p);p['references']=[]
  return prepare('policy',p,QuotedVerdict.model_json_schema())
 def test_no_source_sentinel_cannot_be_selected(self):
  policy,wire,schema,state=self.empty()
  for name in ['citations','temporal_checks']:self.assertEqual(schema['properties'][name]['maxItems'],0)
  self.assertEqual(schema['properties']['segment_audit']['properties']['a1']['properties']['evidence_segments']['maxItems'],0)
 def test_no_refs_question_restores_without_inventing_evidence(self):
  _,_,_,state=self.empty();v=copy.deepcopy(self.v)
  v['segment_audit']['a1'].update(kind='question',assessment='not_factual',evidence_segments=[])
  v.update(outcome='clarify',has_factual_claims=False,claim_checks=[],citations=[],groundedness='not_assessable')
  self.assertEqual(restore(v,state)['groundedness'],'not_assessable')
 def test_unreferenced_fact_cannot_pass(self):
  _,_,_,state=self.empty();v=copy.deepcopy(self.v);v['segment_audit']['a1']['evidence_segments']=[];v.update(claim_checks=[],citations=[])
  with self.assertRaises(ValueError):restore(v,state)
  v['segment_audit']['a1']['assessment']='insufficient';v['groundedness']='not_assessable'
  self.assertEqual(restore(v,state)['correctness'],'not_assessable')
 def test_sentinel_is_rejected_even_if_transport_ignores_schema(self):
  _,_,_,state=self.empty();v=copy.deepcopy(self.v);v['segment_audit']['a1']['evidence_segments']=['__none__']
  with self.assertRaises(ValueError):restore(v,state)
 def test_policy_distinguishes_process_and_visible_act(self):
  from evals.structured_judge_wire import POLICY
  self.assertIn('process_description',POLICY);self.assertIn('not from what should happen next',POLICY)
  self.assertIn('product promise hidden inside a disclaimer remains a product claim',POLICY)
class ScopeBoundary(unittest.TestCase):
 def test_scope_policy_targets_visible_claims_not_source_extras(self):
  from app.rag.grounding import VERIFY_POLICY
  for phrase in ['EXCLUSIVAMENTE o texto das claims','sua mera presença na fonte NUNCA','scope_issue deve citar literalmente','realmente anuncia evento atual']:
   self.assertIn(phrase,VERIFY_POLICY)

class CitationMarkers(unittest.TestCase):
 def test_repeated_source_has_one_marker_without_mutating_evidence(self):
  from app.rag.grounding import citation_markers
  refs=['a','a','b'];self.assertEqual(citation_markers(refs,['a','b']),'[1][2]');self.assertEqual(refs,['a','a','b'])
 def test_different_sources_preserve_order_and_indices(self):
  from app.rag.grounding import citation_markers
  self.assertEqual(citation_markers(['b','a'],['a','b']),'[2][1]')
