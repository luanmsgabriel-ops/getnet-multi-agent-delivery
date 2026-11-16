"""Focused supervisor/RAG contracts. Controlled decisions are not model proof."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import Mock

from app.agentic import Supervisor
from app.agentic_capabilities import Capabilities
from app.contracts import RespostaEspecialista
from app.rag.runtime import configured_knowledge
from app.rag.grounding import GroundedSynthesizer, evidence_ref
from test_agentic import Script, consult, finish

ROOT = Path(__file__).resolve().parents[1]
ENV = {'GETNET_RAG_ADAPTER': 'documentary', 'GETNET_RAG_RETRIEVAL': 'lexical',
       'GETNET_PUBLIC_SEARCH': 'disabled'}
Q = 'Como compartilhar Link de Pagamento Getnet?'


class Capture(Script):
    def __init__(self, *steps):
        super().__init__(*steps)
        self.systems = []

    def decide(self, system, payload, schema, *, timeout):
        self.systems.append(system)
        return super().decide(system, copy.deepcopy(payload), schema, timeout=timeout)


class Weights23Integration(unittest.TestCase):
    def local(self):
        return configured_knowledge(ROOT / 'corpus_publico', env=ENV)

    def test_effective_search_policy_reaches_client_and_execution(self):
        question = 'Como a compostagem transforma resíduos orgânicos?'
        for selected in ('disabled', 'mwmbl', 'tavily', 'brave'):
            with self.subTest(selected=selected):
                public = Mock()
                public.answer.return_value = RespostaEspecialista(
                    texto='Evidência pública controlada.', status='evidencias',
                    fontes=['https://example.org/compostagem'], modo='pesquisa')
                caps = Capabilities(self.local(), public=public,
                                    env={**ENV, 'GETNET_PUBLIC_SEARCH': selected})
                enabled = selected == 'mwmbl'
                script = Capture(consult('knowledge_public', question),
                                 finish('answered' if enabled else 'unavailable',
                                        action='finish' if enabled else 'limit'))
                result = Supervisor(script, caps).executar(
                    {'message': question, 'user_id': 'cliente1988'})
                for system, payload in zip(script.systems, script.payloads):
                    self.assertEqual(payload['general_search'], caps.public_policy)
                    self.assertIn('Mwmbl habilitada' if enabled else 'busca geral desativada', system)
                    self.assertNotIn('pesquisa geral está pausada', system)
                    self.assertIn('Tavily e Brave permanecem bloqueados', system)
                self.assertEqual(public.answer.call_count, int(enabled))
                self.assertEqual(result.agentic.stop, 'finish' if enabled else 'limit')
                self.assertEqual(script.payloads[1]['observations'][0]['status'],
                                 'complete' if enabled else 'unavailable')

    def test_fixed_documentary_lookup_exact_and_rephrased_stop_without_extra_decision(self):
        for proposal in (Q, 'Getnet Link detalhes de compartilhamento'):
            with self.subTest(proposal=proposal):
                local = self.local()
                # Actual local extraction supplies claims/sources; it is explicitly
                # not assessed and must never be promoted by a scripted decision.
                caps = Capabilities(local, env=ENV)
                self.assertTrue(caps.lookup_plan(Q, goal_request=Q)['fixed'])
                original = local._single
                local._single = Mock(wraps=original)
                script = Capture(consult(query=Q), consult(query=proposal, goals=False))
                result = Supervisor(script, caps).executar(
                    {'message': Q, 'user_id': 'cliente1988'})
                self.assertEqual(result.agentic.stop, 'no_progress')
                self.assertEqual(len(script.payloads), 2)
                self.assertEqual(local._single.call_count, 1)
                self.assertEqual(result.agentic.coverage[0].status, 'partial')
                self.assertTrue(result.grounding)
                self.assertTrue(result.sources)
                self.assertIn('encerrei para não repetir', result.answer)

    def test_terminal_contrasts_are_observed_before_controlled_next_decision(self):
        from app.support import SyntheticTools
        question = 'Consulte o estado da minha maquininha; se estiver offline, consulte a orientação pública de Wi-Fi da Getnet.'
        for state in ('online', 'offline', 'unavailable'):
            with self.subTest(state=state):
                class Terminal(SyntheticTools):
                    def consultar_terminal(self):
                        if state == 'unavailable':
                            raise ConnectionError('controlled unavailable')
                        return {**super().consultar_terminal(), 'status': state}
                def after_observation(payload):
                    observation = payload['observations'][0]
                    if observation['status'] == 'unavailable':
                        return finish('unavailable', action='limit')
                    if ': offline.' in observation['content']:
                        return consult(query=question, goals=False, uses=['o1'])
                    return finish()
                script = Capture(consult('support_terminal', question), after_observation,
                                 finish('partial', refs=('o1', 'o2')))
                caps = Capabilities(self.local(), tools_factory=Terminal, env=ENV)
                result = Supervisor(script, caps).executar({'message': question, 'user_id': 'cliente1988'})
                decisions = [e.action for e in result.agentic.trace if e.kind == 'decision']
                self.assertEqual(decisions[1], {'online': 'finish', 'offline': 'knowledge_getnet',
                                              'unavailable': 'limit'}[state])
                self.assertEqual(result.agentic.tool_calls, 2 if state == 'offline' else 1)
                self.assertEqual(script.payloads[1]['observations'][0]['limitation'],
                                 'tool_provider_failure' if state == 'unavailable' else 'status_only_not_diagnosis')
                self.assertNotIn('controlled unavailable', result.answer)
                if state == 'offline':
                    self.assertTrue(result.sources)
                    self.assertEqual(result.agentic.coverage[0].status, 'partial')

    def test_compound_support_context_and_documentary_stages_stay_separate(self):
        support = 'Qual o estado da minha maquininha?'
        question = 'Como compartilhar Link de Pagamento Getnet, sem mudar meu contrato?'
        record = []

        class PublicStages:
            def decide(self, system, payload, schema, **options):
                record.append(copy.deepcopy(payload))
                stage = schema['title']
                if stage == 'RequestPlan':
                    return {'obligations': [{'id': 'r1', 'request_span': 'Como compartilhar Link de Pagamento Getnet'}],
                            'constraints': ['sem mudar meu contrato']}
                if stage == 'Draft':
                    # Literal local evidence only: controlled wiring, not synthesis quality.
                    e = payload['evidence'][0]
                    text = 'O link de pagamento da Getnet é ideal para vendas online e via WhatsApp, sem necessidade de site ou maquininha física.'
                    assert text in e['text']
                    return {'claims': [{'text': text, 'answers': ['r1'],
                                       'citations': [{'evidence_id': e['evidence_id'], 'quote': e['text']}]}],
                            'gaps': []}
                return {'claims': [{'claim_index': 0, 'supported': True}],
                        'scope_respected': True, 'gaps_supported': True, 'coverage_complete': False,
                        'obligations': [{'obligation_id': 'r1', 'claim_indices': [0], 'status': 'uncertain'}]}

        local = self.local()
        local.synthesizer = GroundedSynthesizer(PublicStages(), evidence_filter=local.scopes.compatible)
        first = consult('support_terminal', support)
        first['goals'].append({'id': 'g2', 'request': question})
        last = {'action': 'finish', 'reason': 'partial', 'uses': ['o1', 'o2'],
                'resolutions': [{'goal_id': 'g1', 'status': 'answered', 'observation_ids': ['o1']},
                                {'goal_id': 'g2', 'status': 'partial', 'observation_ids': ['o2']}]}
        script = Capture(first, consult(query=question, goals=False, goal='g2', uses=['o1']), last)
        result = Supervisor(script, Capabilities(local, env=ENV)).executar(
            {'message': support + ' ' + question, 'user_id': 'cliente1988'},
            history=[{'request': 'Uso a Get Smart.', 'clarification': None}])
        self.assertEqual(result.agentic.stop, 'finish')
        self.assertEqual(result.route, 'support_knowledge')
        self.assertEqual(len(record), 3)
        self.assertEqual(set(record[0]), {'question'})
        for payload in record:
            self.assertEqual(payload['question'], question)
            serialized = json.dumps(payload, ensure_ascii=False)
            for private in ('cliente1988', 'terminal_id', 'Terminal fictício', support):
                self.assertNotIn(private, serialized)
        self.assertEqual(record[1]['request_constraints'], ['sem mudar meu contrato'])
        self.assertTrue(script.payloads[1]['conversation'])
        observation = script.payloads[2]['observations'][1]
        self.assertEqual(observation['evidence_coverage'], 'partial')
        self.assertTrue(observation['sources'])
        self.assertIn('Cobertura não confirmada', observation['content'])
        self.assertNotEqual(observation['limitation'], '')
        self.assertEqual([g.request for g in result.agentic.goals], [support, question])
        self.assertEqual(result.agentic.constraints, ['sem mudar meu contrato'])
        self.assertTrue(result.simulated_data)
        self.assertIn('fictício', result.answer)
        self.assertIn('Cobertura não confirmada', result.answer)


if __name__ == '__main__':
    unittest.main()
