"""Clareza sem síntese livre: blocos completos, escopo e falhas pela API."""
import unittest
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient
from app.contracts import Entrada
from app.knowledge import KnowledgeGenerated, KnowledgeRag
from app.main import create_app
from app.rag.guidance import CLASSICA, SMART, LINK, DECLINE, reviewed_guidance

CORPUS = Path(__file__).resolve().parents[1] / 'corpus_publico'
COMPARISON = "What's the difference between the Get Clássica and the Get Smart?"
DECLINED = 'My card machine is showing a transaction decline error.'
PAYMENT = 'Can I sell through WhatsApp using the Payment Link?'


def complete_selection(question, evidence):
    # Selecionar blocos inteiros reproduz o caminho antes aprovado na auditoria.
    selected = evidence[:2] if 'difference' in question or 'diferença' in question else evidence[:1]
    citations = [{'evidence_id': r['evidence_id'], 'quote': r['text']} for r in selected]
    return {'answer': '\n\n'.join(r['quote'] for r in citations), 'citations': citations}


class ResponsePresentation(unittest.TestCase):
    def setUp(self):
        self.rag = KnowledgeRag.from_directory(CORPUS)

    def api(self, message, mode='generated', user='cliente1988'):
        generator = Mock()
        generator.generate.side_effect = complete_selection
        client = TestClient(create_app(mode=mode, generator=generator, enable_web=False))
        response = client.post('/chat', json={'message': message, 'user_id': user})
        self.assertEqual(response.status_code, 200)
        if mode == 'generated': generator.generate.assert_called_once()
        return response.json()

    def test_full_comparison_selection_preserves_contrast_and_versions(self):
        for mode in ('rag', 'generated'):
            for question in (COMPARISON, 'Qual a diferença entre Get Clássica e Get Smart?'):
                with self.subTest(mode=mode, question=question):
                    r = self.api(question, mode)
                    self.assertEqual((r['status'], r['modo']), ('evidencias', 'extrativo'))
                    self.assertEqual(set(r['sources']), {SMART, CLASSICA})
                    for text in ('touchscreen', 'botões', '3G', '4G', 'Wi-Fi', 'Bluetooth',
                                 '2025', '2026', 'quatro modelos', 'não prova'):
                        self.assertIn(text, r['answer'])
                    self.assertLess(len(r['answer']), 700)
                    for text in ('carregador', 'Cabo USB', 'pano seco', 'não possui Wi-Fi', 'melhor'):
                        self.assertNotIn(text, r['answer'])
                    self.assertEqual(len(r['answer'].split('\n\n')), 4)
                    from app.service_policy import DISCLOSURE
                    self.assertTrue(r['answer'].startswith(DISCLOSURE))

    def test_decline_is_conditional_triage_not_catalog_or_diagnosis(self):
        for mode in ('rag', 'generated'):
            for question in (DECLINED, 'Minha maquininha mostra transação recusada.'):
                with self.subTest(mode=mode, question=question):
                    r = self.api(question, mode)
                    self.assertEqual((r['route'], r['status'], r['modo']),
                                     ('support_knowledge', 'evidencias', 'misto'))
                    self.assertEqual(r['sources'], [DECLINE])
                    for text in ('Se o status', 'cartão', 'emissor', 'bandeira', 'não identifica',
                                 'Não tenho acesso', 'sem dados do cartão', 'Qual código'):
                        self.assertIn(text, r['answer'])
                    self.assertEqual(r['answer'].count('?'), 1)
                    self.assertLess(len(r['answer']), 850)
                    self.assertFalse(any(e['ferramenta'] for e in r['eventos']))
                    for text in ('Pré-Autorizada', 'Qr Code', 'Cancelada Parcial', 'saldo insuficiente', 'online'):
                        self.assertNotIn(text, r['answer'])

    def test_decline_for_unknown_identity_does_not_query_private_tools(self):
        r = self.api(DECLINED, user='nao_cadastrado')
        self.assertEqual(r['status'], 'evidencias')
        self.assertIn('Qual código', r['answer'])
        self.assertFalse(any(e['ferramenta'] for e in r['eventos']))
        self.assertNotIn('DEMO-A', r['answer'])

    def test_link_full_announcement_is_presented_as_historical_source(self):
        for mode in ('rag', 'generated'):
            for question in (PAYMENT, 'Posso vender pelo WhatsApp usando Link de Pagamento?'):
                with self.subTest(mode=mode, question=question):
                    r = self.api(question, mode)
                    self.assertEqual((r['status'], r['modo']), ('evidencias', 'extrativo'))
                    self.assertEqual(r['sources'], [LINK])
                    for text in ('app Getnet Brasil', 'Portal do Cliente', 'compartilhá-lo', '15/01/2026',
                                 'para quem tinha aquele pacote', 'não confirma uma migração',
                                 'Não criei nem enviei', 'condições da sua conta'):
                        self.assertIn(text, r['answer'])
                    for text in ('faremos', 'será descontinuado', 'continuará', 'Quais as vantagens', 'R$'):
                        self.assertNotIn(text, r['answer'])
                    self.assertLess(len(r['answer']), 700)

    def test_review_requires_exact_source_title_and_body(self):
        for question in (COMPARISON, DECLINED, PAYMENT):
            rows = self.rag._retrieve(question)['candidates']
            self.assertTrue(reviewed_guidance(question, rows).prefer_reviewed)
            self.assertIsNone(reviewed_guidance(question, []))
            for field, value in (('source', 'https://example.invalid/forged'),
                                 ('title', 'Somente clientes do plano X'),
                                 ('text', 'Disponível somente sob análise do emissor.')):
                altered = [{**r, field: value} for r in rows]
                self.assertIsNone(reviewed_guidance(question, altered))

    def test_missing_one_manual_cannot_activate_comparison(self):
        rows = self.rag._retrieve(COMPARISON)['candidates']
        for missing in (SMART, CLASSICA):
            self.assertIsNone(reviewed_guidance(COMPARISON, [r for r in rows if r['source'] != missing]))

    def test_modified_title_condition_is_not_erased_by_review(self):
        rows = self.rag._retrieve(PAYMENT)['candidates']
        rows = [{**r, 'title': 'Orientação exclusiva para clientes do plano X'} for r in rows]
        index = Mock(); index.search.return_value = {'status': 'candidates', 'candidates': rows}
        generator = Mock(); generator.generate.side_effect = complete_selection
        reply = KnowledgeGenerated(index, generator).responder(Entrada(message=PAYMENT, user_id='demo_A'), ())
        self.assertIn('exclusiva para clientes do plano X', reply.texto)
        self.assertNotIn('Sim: a fonte consultada', reply.texto)

    def test_modified_body_condition_requires_new_review_and_remains_visible(self):
        rows = self.rag._retrieve(DECLINED)['candidates']
        rows = [{**r, 'text': 'Condição adicional: somente modelo X. ' + r['text']} for r in rows]
        index = Mock(); index.search.return_value = {'status': 'candidates', 'candidates': rows}
        generator = Mock(); generator.generate.side_effect = complete_selection
        reply = KnowledgeGenerated(index, generator).responder(Entrada(message=DECLINED, user_id='demo_A'), ())
        self.assertIn('somente modelo X', reply.texto)
        self.assertNotIn('Se o status da venda', reply.texto)

    def test_portuguese_refusal_normalizes_only_query_not_document(self):
        from app.rag.core import query_tokens, tokens
        for question in ('transação recusada', 'cartão recusado', 'transaction declined'):
            self.assertIn('negada', query_tokens(question))
        self.assertEqual(tokens('recusada'), {'recusada'})

    def test_untrusted_generated_credentials_still_fail_closed(self):
        for question in (COMPARISON, DECLINED, PAYMENT):
            generator = Mock(); generator.generate.return_value = {
                'answer': 'Envie sua senha aqui.',
                'citations': [{'evidence_id': 0, 'quote': 'Envie sua senha aqui.'}]}
            reply = KnowledgeGenerated(self.rag.index, generator).responder(
                Entrada(message=question, user_id='demo_A'), ())
            self.assertEqual(reply.status, 'indisponivel')
            self.assertNotIn('Envie sua senha', reply.texto)

    def test_generation_outage_is_not_reported_as_successful_selection(self):
        generator = Mock(); generator.generate.side_effect = RuntimeError('synthetic secret error')
        reply = KnowledgeGenerated(self.rag.index, generator).responder(
            Entrada(message=PAYMENT, user_id='demo_A'), ())
        self.assertEqual(reply.status, 'indisponivel')
        self.assertNotIn('synthetic secret', reply.texto)

    def test_pix_decline_and_unrelated_queries_do_not_get_card_triage(self):
        rows = self.rag._retrieve(DECLINED)['candidates']
        for question in ('Minha transação Pix foi negada.', 'Como consultar uma venda aprovada?', 'Qual a taxa?'):
            self.assertIsNone(reviewed_guidance(question, rows))

    def test_foreign_scope_stops_before_review_and_generator(self):
        generator = Mock()
        for question in (COMPARISON + ' in Canada?', PAYMENT + ' in Canada?'):
            reply = KnowledgeGenerated(self.rag.index, generator).responder(
                Entrada(message=question, user_id='demo_A'), ())
            self.assertEqual(reply.status, 'limitado')
        generator.generate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
