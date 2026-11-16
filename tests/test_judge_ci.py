"""Controlled evaluator contracts and variability accounting, not LLM quality."""
import copy
import unittest
from evals.judging import judge
from evals.quality import quality_report
import test_eval_judging as helpers

class JudgeSemanticsContract(unittest.TestCase):
    def test_policy_separates_omission_support_outcome_and_time(self):
        packet = helpers.BlindJudging().packet()
        script = helpers.Script(helpers.verdict())
        judge(packet, script)
        policy = script.calls[0][0]
        for rule in ['omissions in completeness/reason',
                     'still outcome answer', 'include the dated passage',
                     'Independent usage guidance is not itself a transition claim',
                     'while ignoring another that supports it',
                     'Never insert ellipses, paraphrase',
                     'claim_checks MUST be []',
                     'whether the question is useful or unnecessary']:
            self.assertIn(rule, policy)

    def test_grounded_partial_answer_is_not_rewritten_to_limit_or_failure(self):
        packet = helpers.BlindJudging().packet()
        raw = helpers.verdict(outcome='answer', completeness='partial',
                              groundedness='pass', correctness='pass')
        result = judge(packet, helpers.Script(raw))
        self.assertEqual(result.verdict.outcome, 'answer')
        self.assertEqual(result.verdict.completeness, 'partial')
        self.assertEqual(result.verdict.groundedness, 'pass')
        # This is prescribed evaluator output, not automatic semantic approval.

    def test_short_contiguous_quote_is_valid_without_full_reference(self):
        packet = helpers.BlindJudging().packet()
        packet['references'][0]['text'] = 'Desligue o aparelho. Use pano seco. Aguarde antes de ligar.'
        raw = helpers.verdict(answer_quotes=['Use pano seco.'], claim_checks=[{
            'answer_quote': 'Use pano seco.', 'evidence_id': 'e1',
            'reference_quote': 'Use pano seco.', 'assessment': 'supported'}])
        self.assertEqual(judge(packet, helpers.Script(raw)).status, 'assessed')

    def test_summarized_joined_or_invented_quotes_remain_invalid(self):
        packet = helpers.BlindJudging().packet()
        packet['references'][0]['text'] = 'Desligue o aparelho. Use pano seco. Aguarde antes de ligar.'
        for quote in ['Desligue o aparelho... Aguarde antes de ligar.',
                      'Desligue o aparelho. Aguarde antes de ligar.',
                      'Limpe com um pano seco.', 'Use  pano seco.']:
            with self.subTest(quote=quote):
                raw = helpers.verdict(answer_quotes=['Use pano seco.'], claim_checks=[{
                    'answer_quote': 'Use pano seco.', 'evidence_id': 'e1',
                    'reference_quote': quote, 'assessment': 'supported'}])
                result = judge(packet, helpers.Script(raw))
                self.assertEqual(result.error_code, 'invalid_verdict')
                self.assertIsNone(result.verdict)

    def test_pure_questions_allow_empty_checks_without_rewriting_adequacy(self):
        packet = helpers.BlindJudging().packet()
        packet['response']['answer'] = 'Qual modelo?'
        for adequacy in ['pass', 'partial', 'fail']:
            with self.subTest(adequacy=adequacy):
                raw = helpers.verdict(outcome='clarify', answer_quotes=['Qual modelo?'],
                    claim_checks=[], groundedness='not_assessable', citations=[],
                    relevance=adequacy, usefulness=adequacy)
                result = judge(packet, helpers.Script(raw))
                self.assertEqual(result.status, 'assessed')
                self.assertEqual(result.verdict.claim_checks, [])
                self.assertEqual(result.verdict.groundedness, 'not_assessable')
                self.assertEqual(result.verdict.usefulness, adequacy)
                # Prescribed outputs prove no semantic classification by this test.

class JudgeStabilityAccounting(unittest.TestCase):
    def row(self, replicate, **changes):
        packet = helpers.BlindJudging().packet()
        value = dict(case_id='O01', replicate=replicate,
                     execution_kind='controlled', dataset_hash='a'*64,
                     manifest_hash='b'*64, packet=packet,
                     judgment={'status':'assessed','verdict':helpers.verdict()})
        value.update(changes)
        return value

    def report(self, rows):
        return quality_report(rows, planned_cases=1, planned_replicates=3)

    def test_outcome_variation_is_not_stable_even_when_grades_agree(self):
        rows = [self.row(i) for i in (1, 2, 3)]
        rows[1]['judgment']['verdict']['outcome'] = 'clarify'
        group = self.report(rows)['groups'][0]
        self.assertEqual(group['fully_replicated_assessed_cases'], 1)
        self.assertEqual(group['stable_verdict_cases'], 0)

    def test_stable_failure_is_agreement_not_semantic_success(self):
        rows = [self.row(i) for i in (1, 2, 3)]
        for row in rows:row['judgment']['verdict']['correctness'] = 'fail'
        group = self.report(rows)['groups'][0]
        self.assertEqual(group['stable_verdict_cases'], 1)
        self.assertEqual(group['dimensions']['correctness'], {'fail':3})
        self.assertFalse(group['semantic_certification'])

    def test_missing_and_inconclusive_runs_do_not_complete_three_replicates(self):
        rows = [self.row(1), self.row(2)]
        group = self.report(rows)['groups'][0]
        self.assertEqual(group['missing_executions'], 1)
        self.assertEqual(group['fully_replicated_assessed_cases'], 0)
        rows.append(self.row(3, judgment={'status':'inconclusive','error_code':'transport_error'}))
        group = self.report(rows)['groups'][0]
        self.assertEqual(group['inconclusive_executions'], 1)
        self.assertEqual(group['fully_replicated_assessed_cases'], 0)

    def test_versions_are_not_pooled_and_duplicate_runs_are_rejected(self):
        rows = [self.row(1), self.row(2), self.row(3, manifest_hash='c'*64)]
        groups = self.report(rows)['groups']
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(g['fully_replicated_assessed_cases']==0 for g in groups))
        with self.assertRaises(ValueError):self.report([rows[0], copy.deepcopy(rows[0])])

if __name__ == '__main__': unittest.main()
