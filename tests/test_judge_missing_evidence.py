import copy,unittest
from evals.structured_judge_wire import prepare,restore
from evals.judging import QuotedVerdict,ClaimCheck,validate_verdict
from evals.judge_evidence import checks_from_audit,MAX_CLAIM_CHECKS
import test_structured_judge_wire as fixtures

class MissingEvidence(unittest.TestCase):
    setUp=fixtures.Structural.setUp
    def missing(self):
        d=copy.deepcopy(self.v);d.pop('claim_checks')
        d['segment_audit']['a1'].update(assessment='insufficient',evidence_segments=[])
        d['groundedness']='partial';d['correctness']='not_assessable';d['citations']=[]
        return d
    def test_irrelevant_existing_refs_allow_explicit_missing_evidence(self):
        d=self.missing();v=restore(d,self.state)
        self.assertEqual(v['claim_checks'],[dict(answer_quote=self.state[0]['a1'],evidence_id=None,reference_quote=None,assessment='insufficient')])
        self.assertEqual(validate_verdict(self.p,v).status,'assessed')
        self.assertEqual(v['groundedness'],'partial');self.assertEqual(v['correctness'],'not_assessable')
    def test_no_references_also_retains_literal_anchor(self):
        p=copy.deepcopy(self.p);p['references']=[]
        _,_,_,state=prepare('x',p,QuotedVerdict.model_json_schema())
        v=restore(self.missing(),state)
        self.assertIsNone(v['claim_checks'][0]['evidence_id'])
        self.assertEqual(validate_verdict(p,v).status,'assessed')
    def test_supported_contradicted_ambiguous_cannot_lack_sources(self):
        for assessment in ('supported','contradicted','ambiguous'):
            d=self.missing();d['segment_audit']['a1']['assessment']=assessment
            with self.assertRaises(ValueError):restore(d,self.state)
    def test_nulls_only_together_and_only_insufficient(self):
        for assessment in ('supported','contradicted','insufficient'):
            for eid,quote in [(None,'source'),('e1',None),(None,None)]:
                raw=dict(answer_quote='Fact.',evidence_id=eid,reference_quote=quote,assessment=assessment)
                if assessment=='insufficient' and eid is None and quote is None:ClaimCheck.model_validate(raw)
                else:
                    with self.assertRaises(ValueError):ClaimCheck.model_validate(raw)
    def test_missing_evidence_cannot_pass_grounding_or_invent_anchor(self):
        d=self.missing();d['groundedness']='pass'
        with self.assertRaises(ValueError):restore(d,self.state)
        v=restore(self.missing(),self.state)
        for change in ('pass','anchor','citation'):
            bad=copy.deepcopy(v)
            if change=='pass':bad['groundedness']='pass'
            elif change=='anchor':bad['claim_checks'][0]['answer_quote']='Not in answer.'
            else:bad['citations']=['invented']
            self.assertEqual(validate_verdict(self.p,bad).status,'inconclusive')
    def test_legacy_checks_cannot_hide_supported_audit_with_nulls(self):
        d=self.missing();d['claim_checks']=[dict(answer_quote='a1',evidence_id=None,reference_quote=None,assessment='insufficient')]
        d['segment_audit']['a1']['assessment']='supported'
        with self.assertRaises(ValueError):restore(d,self.state)
    def test_unknown_source_still_rejected_and_capacity_bounded(self):
        d=self.missing();d['segment_audit']['a1']['evidence_segments']=['invented']
        with self.assertRaises(ValueError):restore(d,self.state)
        amap={str(i):'Fact.' for i in range(MAX_CLAIM_CHECKS+1)}
        audit={a:dict(kind='product_claim',assessment='insufficient',evidence_segments=[]) for a in amap}
        with self.assertRaises(ValueError):checks_from_audit(audit,amap,{})

    def test_quality_report_consumes_null_checks_without_changing_grade(self):
        from evals.quality import quality_report
        v=restore(self.missing(),self.state)
        row=dict(case_id='O01',replicate=1,execution_kind='controlled',dataset_hash='a'*64,manifest_hash='b'*64,packet=self.p,judgment={'status':'assessed','verdict':v})
        group=quality_report([row],planned_cases=1,planned_replicates=3)['groups'][0]
        self.assertEqual(group['assessed_executions'],1)
        self.assertEqual(group['dimensions']['groundedness'],{'partial':1})
        self.assertEqual(group['fully_replicated_assessed_cases'],0)
