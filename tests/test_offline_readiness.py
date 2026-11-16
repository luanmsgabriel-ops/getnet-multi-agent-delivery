import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from evals.offline_readiness import exposure_report,stability_report,deviation_report
from evals.quality import read_json
import test_judge_ci as fixtures

ROOT=Path(__file__).resolve().parents[1]
class OfflineReadiness(unittest.TestCase):
    def test_catalog_transparency_not_blind_holdout(self):
        r=exposure_report(ROOT)
        self.assertEqual(r['catalog_cases'],40)
        self.assertEqual(r['exposure_counts'],{'known_original':10,'known_regression':10,'not_verified_unseen':20})
        self.assertEqual(r['verified_unseen_cases'],0)
    def test_fabricated_unseen_or_duplicate_registry_rejected(self):
        original=read_json(ROOT/'evals/exposure_registry.json')
        for mutation in ('unseen','duplicate','missing'):
            data=copy.deepcopy(original)
            if mutation=='unseen':data['cases'][-1]['exposure_status']='certified_unseen'
            elif mutation=='duplicate':data['cases'][-1]=data['cases'][0]
            else:data['cases'].pop()
            # catalog uses its own module reader; this patches only registry read.
            with patch('evals.offline_readiness.read_json',return_value=data):
                with self.assertRaises(ValueError):exposure_report(ROOT)
    def rows(self):return [fixtures.JudgeStabilityAccounting().row(i) for i in (1,2,3)]
    def test_three_same_version_and_missing_not_completed(self):
        rows=self.rows();r=stability_report(rows)
        self.assertEqual(r['groups'][0]['fully_replicated_assessed_cases'],1)
        self.assertEqual(r['groups'][0]['missing_executions'],117)
        self.assertFalse(r['semantic_stability_certified'])
        self.assertEqual(stability_report(rows[:2])['groups'][0]['fully_replicated_assessed_cases'],0)
    def test_versions_separated_and_duplicates_rejected(self):
        rows=self.rows();rows[-1]['manifest_hash']='c'*64
        r=stability_report(rows)
        self.assertEqual(len(r['groups']),2)
        self.assertTrue(all(g['fully_replicated_assessed_cases']==0 for g in r['groups']))
        with self.assertRaises(ValueError):stability_report([rows[0],rows[0]])
    def test_agreement_on_failure_is_not_success(self):
        rows=self.rows()
        for row in rows:row['judgment']['verdict']['correctness']='fail'
        g=stability_report(rows)['groups'][0]
        self.assertEqual(g['stable_verdict_cases'],1)
        self.assertEqual(g['dimensions']['correctness'],{'fail':3})
        self.assertFalse(g['semantic_certification'])
    def test_empty_and_invalid_log_remain_actionable_not_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'events.jsonl';p.write_text('bad json\n',encoding='utf8')
            before=p.read_bytes();r=deviation_report(p)
            self.assertEqual(before,p.read_bytes())
            self.assertFalse(r['actions_executed']);self.assertFalse(r['all_clear_claimed'])
            self.assertIn('NO_USABLE_EVENTS',[x['code'] for x in r['findings']])
            self.assertIn('INCOMPLETE_CAPTURE',[x['code'] for x in r['findings']])
    def test_provider_budget_and_functional_flags_no_actions(self):
        observed={'input_quality':{'accepted_records':5,'incomplete':False},
         'provider_http_errors':{'statuses':{'429':1,'503':1}},'http':{'statuses':{'200':1}},
         'costs':{'by_mode':{'remote':{'unconfirmed_reconciliation_records':1}}},
         'functional_outcomes':{'partial':1}}
        with patch('evals.offline_readiness.aggregate_file',return_value=observed):r=deviation_report('unused')
        codes={x['code'] for x in r['findings']}
        self.assertEqual(codes,{'PROVIDER_429','PROVIDER_5XX','BUDGET_UNCERTAIN','FUNCTIONAL_REVIEW'})
        self.assertFalse(r['actions_executed'])
    def test_empty_findings_do_not_certify_health(self):
        observed={'input_quality':{'accepted_records':1,'incomplete':False},'provider_http_errors':{'statuses':{}},
         'http':{'statuses':{'200':1}},'costs':{'by_mode':{}},'functional_outcomes':{'ok':1}}
        with patch('evals.offline_readiness.aggregate_file',return_value=observed):r=deviation_report('unused')
        self.assertEqual(r['findings'],[]);self.assertFalse(r['all_clear_claimed'])
