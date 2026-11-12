"""Audit 71 context regressions with a deliberately fallible model proposal.

No model/network calls. The real ContextService, SoloInterpreter, local corpus
and SQLite store are exercised. These cases verify the local boundary; they do
not claim that a real language model produced the deliberately wrong proposal.
"""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.context_service import ContextService
from app.context_solo import SoloInterpreter
from app.context_store import Store


def request(quote, kind='summary', topic='other', refs=('new1',)):
    return {'kind': kind, 'topic': topic, 'entities': list(refs), 'quote': quote}


def observation(quote, value, field='symptom', status='asserted'):
    return {'entity': 'new1', 'incident': '', 'field': field, 'value': value,
            'status': status, 'origin': 'customer', 'scope': 'entity',
            'quote': quote}


def proposal(quote, devices=(), observations=(), kind='summary', topic='other'):
    return {'devices': list(devices), 'observations': list(observations),
            'requests': [request(quote, kind, topic)], 'focus': ['new1'],
            'resolve_pending': []}


class FallibleProposalSpy:
    def __init__(self):
        self.calls = []
        self.propose = None

    def complete(self, system, payload, schema):
        self.calls.append(copy.deepcopy(payload))
        if 'disputed' in payload:
            # Even an over-permissive semantic review cannot authorize a
            # categorical assertion explicitly denied by its evidence.
            return {group: [
                {'index': i, 'verdict': 'supported', 'origin': 'customer'}
                for i in payload['disputed'][group]
            ] for group in ('devices', 'observations')}
        return self.propose(payload['message'])


class AuditContextIntegrity(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {
            'GETNET_WEB_SEARCH': '0', 'GETNET_ALLOW_MODEL_NETWORK': '0'})
        environment.start()
        self.addCleanup(environment.stop)
        for target in ('socket.create_connection', 'socket.socket.connect'):
            guard = patch(target, side_effect=AssertionError('Network forbidden in mock test'))
            guard.start()
            self.addCleanup(guard.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.spy = FallibleProposalSpy()
        self.service = ContextService(
            Store(Path(self.directory.name) / 'context.db'), SoloInterpreter(self.spy))
        self.owner = 'audit_context_synthetic'
        self.session = self.service.create(self.owner)

    def seed(self, country='Brasil'):
        quote = 'Minha A920 está no ' + country + ' e não conecta.'
        self.spy.propose = lambda message: proposal(
            message,
            devices=[{'ref': 'new1', 'label': 'A920', 'store': '', 'quote': message}],
            observations=[observation(message, country, 'country'),
                          observation(message, 'não conecta')],
            kind='next_step', topic='connectivity')
        result = self.ask(quote)
        self.assertEqual(result['mode'], 'semantic_interpretation_reviewed_response')
        self.assertEqual(result['state']['devices']['new1']['label'], 'A920')
        self.assertEqual(self.fact(result, 'country')['value'], country)
        return result

    def ask(self, text):
        return self.service.step(self.owner, self.session, text)

    def fact(self, result, field):
        found = [fact for fact in result['state']['facts'].values()
                 if fact['entity'] == 'new1' and fact['field'] == field]
        return found[-1] if found else {}

    def assert_brazil_not_actionable(self, result):
        country = self.fact(result, 'country')
        self.assertFalse(country.get('value') == 'Brasil'
                         and country.get('status') in ('asserted', 'corrected'))
        self.assertNotIn('Procurar Redes', result['answer'])

    def test_s19_denied_country_invalidates_stale_actionable_country(self):
        self.seed()
        text = 'Não estou no Brasil; estou no Chile.'
        self.spy.propose = lambda message: proposal(
            message, observations=[observation('Não estou no Brasil', 'Brasil', 'country')],
            kind='next_step', topic='connectivity')
        result = self.ask(text)
        self.assertEqual(result['mode'], 'scope_policy')
        self.assert_brazil_not_actionable(result)

    def test_s20_corrected_model_is_not_displayed_with_old_model_heading(self):
        self.seed('Brasil')
        text = 'Corrigindo: o modelo é DX8000.'
        self.spy.propose = lambda message: proposal(
            message, observations=[observation(message, 'DX8000', 'product', 'corrected')])
        result = self.ask(text)
        self.assertEqual(self.fact(result, 'product').get('value'), 'DX8000')
        self.assertIn('DX8000', result['answer'])
        self.assertNotIn('A920 —', result['answer'])

    def test_s21_latest_affirmative_model_is_the_retained_product(self):
        self.seed('Brasil')
        text = 'Não uso DX8000; meu terminal é A920.'
        self.spy.propose = lambda message: proposal(
            message, observations=[observation('Não uso DX8000', 'DX8000', 'product')])
        result = self.ask(text)
        # This is the historical assertion, stronger than merely rejecting DX8000.
        # It requires retaining the current affirmative model as a product fact.
        self.assertEqual(self.fact(result, 'product').get('value'), 'A920')
        self.assertNotIn('modelo: DX8000', result['answer'])

    def test_s22_uncertain_country_invalidates_stale_actionable_country(self):
        self.seed()
        text = 'Pode ser Brasil ou Chile; não sei em qual país está a operação.'
        self.spy.propose = lambda message: proposal(
            message, observations=[observation('Pode ser Brasil ou Chile', 'Brasil', 'country')],
            kind='next_step', topic='connectivity')
        result = self.ask(text)
        self.assertEqual(result['mode'], 'scope_policy')
        self.assert_brazil_not_actionable(result)

    def test_s23_connected_wifi_and_current_printing_failure_get_printing_response(self):
        self.seed()
        text = 'O Wi-Fi está conectado; agora minha A920 não imprime.'
        self.spy.propose = lambda message: proposal(
            message, observations=[
                observation('O Wi-Fi está conectado', 'true', 'connected'),
                observation('agora minha A920 não imprime', 'false', 'printing_ok'),
                observation('agora minha A920 não imprime', 'não imprime')],
            kind='information')
        result = self.ask(text)
        self.assertEqual(self.fact(result, 'connected').get('value'), 'true')
        self.assertEqual(self.fact(result, 'printing_ok').get('value'), 'false')
        self.assertNotIn('Procurar Redes', result['answer'])
        self.assertIn('A920', result['answer'])
        self.assertIn('impr', result['answer'].lower())

    def test_negated_model_proposal_is_rejected_even_with_permissive_review(self):
        self.seed('Brasil')
        text = 'Não uso DX8000; meu terminal é A920.'
        self.spy.propose = lambda message: proposal(
            message, observations=[observation('Não uso DX8000', 'DX8000', 'product')])
        result = self.ask(text)
        self.assertNotEqual(self.fact(result, 'product').get('value'), 'DX8000')
        self.assertNotIn('modelo: DX8000', result['answer'])
        self.assertTrue(result['validation']['rejected'])

    def test_affirmative_country_is_kept_despite_separate_negative_symptom(self):
        self.seed()
        text = 'Corrigindo: minha A920 está no Chile e não conecta.'
        self.spy.propose = lambda message: proposal(
            message, observations=[observation(message, 'Chile', 'country', 'corrected')],
            kind='next_step', topic='connectivity')
        result = self.ask(text)
        self.assertEqual(result['state']['service_boundary']['entities']['new1'], 'OUT')
        self.assertEqual(self.fact(result, 'country').get('status'), 'unknown')
        self.assertNotIn('Procurar Redes', result['answer'])


if __name__ == '__main__':
    unittest.main()


class CategoricalClauseBoundary(unittest.TestCase):
    def test_copula_is_not_conjunction(self):
        from app.context_contract import Observation
        from app.context_proof import evidence_guard
        o=Observation.model_validate(observation('não é a loja do Brasil','Brasil','country','asserted'))
        with self.assertRaisesRegex(ValueError,'categorical_polarity'):evidence_guard(o)

    def test_negating_other_country_preserves_chile(self):
        with tempfile.TemporaryDirectory() as d:
            service=ContextService(Store(Path(d)/'s.db'));sid=service.create('synthetic')
            first=service.step('synthetic',sid,'Tenho A920 no Chile.')
            result=service.step('synthetic',sid,'não é a loja do Brasil')
            self.assertEqual(first['mode'],'scope_policy')
            self.assertFalse(result['state']['facts'])
            self.assertNotIn('Procurar Redes',result['answer'])
            self.assertEqual(result['sources'],[])
