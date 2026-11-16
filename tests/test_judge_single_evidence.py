import copy, unittest
from evals.judge_evidence import checks_from_audit, evaluator_identity, MAX_CLAIM_CHECKS
from evals.structured_judge_wire import prepare, restore
from evals.judging import QuotedVerdict, make_packet, validate_verdict
import test_structured_judge_wire as structural

class SingleEvidence(unittest.TestCase):
    setUp = structural.Structural.setUp
    def test_wire_no_duplicate_checks_but_literal_canonical_checks(self):
        self.assertNotIn('claim_checks',self.s['properties'])
        self.assertNotIn('claim_checks',self.s['required'])
        self.v.pop('claim_checks')
        v=restore(self.v,self.state)
        self.assertEqual(v['claim_checks'][0]['reference_quote'],'Use pano seco.')
        self.assertEqual(validate_verdict(self.p,v).status,'assessed')
    def test_more_than_twelve_claims_not_silently_dropped(self):
        text=' '.join(f'Item {i} usa pano seco.' for i in range(30))
        p=make_packet({'message':'Quais cuidados?'},{'answer':text,'status':'ok','sources':[]},[{'source':'https://example.org/a','text':text,'evidence_id':'ref'}],opaque_id='synthetic_long')
        _,_,_,state=prepare('x',p,QuotedVerdict.model_json_schema());amap,aliases,rmap=state
        d=copy.deepcopy(self.v);d.pop('claim_checks')
        d['segment_audit']={a:dict(kind='product_claim',assessment='supported',evidence_segments=[r],temporal_scope='none') for a,r in zip(amap,rmap)}
        d['answer_quotes']=[next(iter(amap))];d['citations']=['e1']
        v=restore(d,state);self.assertEqual(len(v['claim_checks']),30)
        self.assertEqual(validate_verdict(p,v).status,'assessed')
    def test_missing_or_invented_evidence_rejected(self):
        for ids in ([],['unknown'],['e1s1','e1s1']):
            d=copy.deepcopy(self.v);d.pop('claim_checks');d['segment_audit']['a1']['evidence_segments']=ids
            with self.assertRaises(ValueError):restore(d,self.state)
    def test_contradiction_does_not_turn_into_pass(self):
        self.v.pop('claim_checks');self.v['segment_audit']['a1']['assessment']='contradicted'
        with self.assertRaises(ValueError):restore(self.v,self.state)
    def test_multiple_evidence_kept_and_source_ownership_derived(self):
        self.v.pop('claim_checks');self.v['segment_audit']['a1']['evidence_segments']=['e1s1','e2s1']
        v=restore(self.v,self.state)
        self.assertEqual([c['evidence_id'] for c in v['claim_checks']],['sourceA','sourceB'])
    def test_explicit_capacity_not_unbounded(self):
        amap={str(i):'fact' for i in range(MAX_CLAIM_CHECKS+1)};rmap={'r':('e','source')}
        audit={i:dict(kind='product_claim',assessment='supported',evidence_segments=['r']) for i in amap}
        with self.assertRaises(ValueError):checks_from_audit(audit,amap,rmap)
    def test_identity_not_claimed_independent(self):
        p=evaluator_identity('openai/gpt-5-mini','openai/gpt-5-mini')
        self.assertTrue(p['same_model']);self.assertEqual(p['model_family_independence'],'not_demonstrated')
        self.assertEqual(evaluator_identity('a/x','b/y')['human_review'],'not_demonstrated')
