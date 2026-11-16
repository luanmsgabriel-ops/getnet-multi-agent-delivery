"""Focused mechanics for observed temporal/judge defects, never semantic proof."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from evals.judging import make_packet, judge, validate_verdict
from evals.quality import catalog, source_references
from app.rag.grounding import GroundedSynthesizer, expired_schedule_claim
from app.rag.runtime import configured_knowledge
import test_eval_judging as helpers
from test_eval_judging import Script, verdict

ROOT = Path(__file__).resolve().parents[1]

class FocalEvaluation(unittest.TestCase):
    def test_date_is_explicit_validated_and_old_packets_still_import(self):
        p = helpers.BlindJudging().packet()
        self.assertEqual(p['rubric_version'], 'blind-public-v2')
        self.assertIsNone(p['reference_date'])
        p['reference_date'] = '2026-11-16'
        self.assertEqual(judge(p).error_code, 'no_transport')
        for value in ['2026-02-30', 'not-a-date', '2026-11-16 private', 20261116]:
            bad = copy.deepcopy(p); bad['reference_date'] = value
            s = Script(verdict())
            self.assertEqual(judge(bad, s).error_code, 'invalid_packet')
            self.assertEqual(s.calls, [])
        p.pop('reference_date'); p['rubric_version'] = 'blind-public-v1'
        self.assertEqual(validate_verdict(p, verdict()).status, 'assessed')

    def test_service_context_is_explicit_not_selected_by_answer_metadata(self):
        response = {'answer': 'Valor fictício informado.', 'status': 'simulado',
                    'sources': [], 'service_context': 'synthetic_demo', 'expected': 'pass'}
        p = make_packet({'message': 'Qual o valor?'}, response, [], opaque_id='context_test')
        self.assertEqual(p['service_context'], 'public_information')
        p = make_packet({'message': 'Qual o valor?'}, response, [], opaque_id='context_test',
                        service_context='synthetic_demo')
        self.assertEqual(p['service_context'], 'synthetic_demo')
        self.assertNotIn('service_context', p['response'])
        self.assertNotIn('expected', p)
        with self.assertRaises(ValueError):
            make_packet({'message': 'Qual o valor?'}, response, [], opaque_id='context_test',
                        service_context='always_pass')

    def test_scoped_policy_reaches_transport_without_relaxing_validation(self):
        p = helpers.BlindJudging().packet(); p['references'] = []
        p['response']['answer'] = 'Qual rede você utiliza?'
        raw = verdict(groundedness='not_assessable', citations=[], outcome='clarify',
                      answer_quotes=[p['response']['answer']])
        s = Script(raw); s.requires_answer_quotes = True
        self.assertEqual(judge(p, s).status, 'assessed')
        system, payload, schema = s.calls[0]
        for text in ['necessary clarification', 'solely because the fixture is',
                     'unrequested button-by-button', 'groundedness MUST be not_assessable',
                     'omissions in the answer', 'Present-tense transition']:
            self.assertIn(text, system)
        self.assertEqual(payload['response']['answer'], p['response']['answer'])
        self.assertFalse(schema['additionalProperties'])
        keys = list(schema['properties'])
        self.assertLess(keys.index('claim_checks'), keys.index('outcome'))
        self.assertLess(keys.index('outcome'), keys.index('correctness'))
        self.assertLess(keys.index('reason'), keys.index('correctness'))
        self.assertIn('already supplied or unnecessary', system)
        self.assertIn('including volunteered amounts', system)
        self.assertIn('any contradicted', system)
        # A scripted pass with no evidence remains invalid; this is not semantic grading.
        raw['groundedness'] = 'pass'
        self.assertEqual(judge(p, Script(raw)).error_code, 'invalid_verdict')

    def test_claim_checks_require_exact_answer_and_reference_quotes(self):
        p = helpers.BlindJudging().packet()
        p['response']['answer'] = 'O valor é 950.'
        p['references'][0]['text'] = 'O valor é 750.'
        ref = p['references'][0]['evidence_id']
        check = dict(answer_quote='O valor é 950.', evidence_id=ref,
                     reference_quote='O valor é 750.', assessment='contradicted')
        raw = verdict(correctness='fail', groundedness='fail', claim_checks=[check])
        self.assertEqual(validate_verdict(p, raw).status, 'assessed')
        for key, value in [('answer_quote', 'Texto ausente'),
                           ('reference_quote', 'Outra fonte'), ('evidence_id', 'unknown'),
                           ('answer_quote', ' '), ('reference_quote', ' ')]:
            bad = copy.deepcopy(raw); bad['claim_checks'][0][key] = value
            self.assertEqual(validate_verdict(p, bad).error_code, 'invalid_verdict')
        # The model's contradiction assessment cannot coexist with a pass.
        raw['correctness'] = 'pass'
        self.assertEqual(validate_verdict(p, raw).error_code, 'invalid_verdict')
        raw['correctness'] = 'partial'; raw['groundedness'] = 'pass'
        raw['claim_checks'][0]['assessment'] = 'insufficient'
        self.assertEqual(validate_verdict(p, raw).error_code, 'invalid_verdict')

    def test_supplemental_pix_source_does_not_create_required_retrieval_group(self):
        cases, gold = catalog(ROOT)
        oracle = next(o for o in gold['oracles'] if o['case_id'] == 'O04')
        self.assertEqual(len(oracle['evidence_groups']), 1)
        refs = source_references(ROOT, oracle)
        self.assertEqual(len(refs), 2)
        self.assertTrue(any('selecione o domicílio bancário' in r['text'].lower() for r in refs))
        case = next(c for c in cases['cases'] if c['id'] == 'O04')
        p = make_packet({'message': case['turns'][0]['message']},
                        {'answer': 'Resposta de teste.', 'status': 'limitado', 'sources': []},
                        refs, opaque_id='public_pix_focal', reference_date='2026-11-16')
        self.assertEqual(p['reference_date'], '2026-11-16')
        for forbidden in ['criteria', 'acceptable_outcomes', 'evidence_groups', 'case_id', 'expected']:
            self.assertNotIn(forbidden, p)

    def test_invalid_supplemental_reference_rejected_by_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder); (path/'evals').mkdir()
            (path/'evals/cases.json').write_bytes((ROOT/'evals/cases.json').read_bytes())
            base = json.loads((ROOT/'evals/oracles.json').read_text())
            for invalid in [{'source': 'file:///private', 'ordinal': 0},
                            {'source': 'https://example.org/public', 'ordinal': -1}]:
                data = copy.deepcopy(base)
                data['oracles'][3]['supplemental_references'] = [invalid]
                (path/'evals/oracles.json').write_text(json.dumps(data))
                with self.assertRaises(ValueError): catalog(path)

class SourceBoundTemporalRegression(unittest.TestCase):
    def test_state_change_without_migration_noun_uses_source_schedule(self):
        old = 'O cronograma tinha data fim até 15/01/2026.'
        for claim in ['Você pode continuar vendendo, mas a cobrança passa a ser feita pelo link.',
                      'O acesso passa a funcionar pelo novo portal.']:
            self.assertTrue(expired_schedule_claim(claim, '2026-11-16', source_quotes=[old]))
            self.assertFalse(expired_schedule_claim(claim, '2025-11-16', source_quotes=[old]))
            self.assertFalse(expired_schedule_claim(claim, '2026-11-16', source_quotes=['Orientação sem cronograma.']))

    def test_historical_attribution_and_independent_usage_stay_usable(self):
        old = 'A migração tinha data fim até 15/01/2026. O produto permite envio por mensagem.'
        for claim in ['O link pode ser criado no aplicativo e compartilhado por mensagem.',
                      'A fonte anunciava a mudança para 15/01/2026.',
                      'Após selecionar a rede, o terminal passa a usar a conexão escolhida.']:
            self.assertFalse(expired_schedule_claim(claim, '2026-11-16', source_quotes=[old]))

    def test_permissive_verifier_cannot_publish_expired_transition_as_complete(self):
        q = 'Can I sell through WhatsApp using the Payment Link?'
        local = configured_knowledge(ROOT/'corpus_publico', env={})
        rows = local._retrieve(q)['candidates']
        bad = 'Você pode continuar vendendo pelo WhatsApp, mas a cobrança passa a ser feita mediante envio de um link de pagamento da Getnet.'
        good = 'O link de pagamento pode ser criado no app Getnet Brasil e compartilhado pelo WhatsApp.'
        class Controlled:
            def decide(self, system, payload, schema, **kw):
                if schema['title'] == 'RequestPlan':
                    return {'obligations': [{'id': 'r1', 'request_span': q}]}
                if schema['title'] == 'Draft':
                    e = payload['evidence'][0]
                    return {'claims': [{'text': text, 'answers': ['r1'],
                                        'citations': [{'evidence_id': e['evidence_id']}]} for text in [bad, good]], 'gaps': []}
                return {'claims': [{'claim_index': i, 'supported': True} for i in range(2)],
                        'scope_respected': True, 'gaps_supported': True, 'coverage_complete': True,
                        'obligations': [{'obligation_id': 'r1', 'claim_indices': [0, 1], 'status': 'covered'}]}
        with patch('app.rag.grounding.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 16, tzinfo=timezone.utc)
            text, sources, claims, complete = GroundedSynthesizer(
                Controlled(), evidence_filter=local.scopes.compatible).synthesize(q, rows)
        self.assertFalse(complete)
        self.assertNotIn(bad, text)
        self.assertIn(good, text)
        self.assertTrue(sources)
        self.assertEqual(len(claims), 1)

if __name__ == '__main__': unittest.main()
