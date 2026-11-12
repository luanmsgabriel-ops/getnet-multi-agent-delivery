"""Reproduções F03/auditoria 71 e períodos inéditos; somente fixtures locais."""
import unittest
from dataclasses import asdict
from datetime import date
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from app.contracts import Entrada
from app.intents import ReceivableQuery, classify, receivable_query
from app.main import create_app
from app.support import DEMO_PRINCIPAL, SupportSintetico, SyntheticTools

TODAY = date(2026, 11, 10)

EMPTY_RANGES = (
    'Quero consultar meus recebíveis de 2026-11-01 a 2026-11-05.',
    'Consulte meus recebíveis entre 01/11/2026 e 05/11/2026.',
    'Quero ver minhas vendas de 1 de novembro de 2026 até 5 de novembro de 2026.',
)
SALE_RANGES = (
    'Consulte minhas vendas de 2026-11-08 a 2026-11-09.',
    'Quero ver as minhas vendas entre 08/11/2026 e 09/11/2026.',
    'Check my sales from 2026-11-08 to 2026-11-09.',
    'Consulte minhas vendas de 8 de novembro de 2026 até 9 de novembro de 2026.',
)
DUAL_DATES = (
    'As vendas que fiz ontem no crédito à vista caem hoje?',
    'As minhas vendas de ontem serão creditadas hoje?',
    'Recebo hoje minhas vendas de ontem?',
    "Will yesterday's sales be deposited today?",
)
UNSUPPORTED_PERIODS = (
    'Consulte meus recebíveis de 01/11 a 05/11.',
    'Consulte meus recebimentos entre 01 e 05 de novembro.',
    'Consulte meus recebíveis de 2026-11-01 a 05.',
    'Consulte minhas vendas de 2026-11-09 a 2026-11-08.',
    'Consulte minhas vendas de 31/11/2026.',
    'Consulte minhas vendas de 2026-02-29.',
    'Consulte meus recebíveis de 2026-11-08 ou 2026-11-09.',
    'Consulte meus recebimentos na semana passada.',
    'Consulte meus recebíveis desde ontem.',
    'Consulte meus recebimentos dos últimos 999999 dias.',
    'Consulte meus recebimentos dos últimos 0 dias.',
    'Consulte meus recebimentos de 01/01/2024 a 01/01/2026.',
)


def ask(message, *, tools=None):
    return SupportSintetico(tools=tools, today=lambda:TODAY).responder(
        Entrada(message=message,user_id='demo_A'),())


class AuditReceivablePeriods(unittest.TestCase):
    def assert_lookup(self, result):
        self.assertEqual([t.ferramenta for t in result.tool_traces],['consultar_recebiveis'])
        self.assertEqual(result.tool_traces[0].status,'ok')
        self.assertIn('SIMULACAO',result.texto)

    def test_audited_range_never_returns_unfiltered_total(self):
        for message in EMPTY_RANGES:
            with self.subTest(message=message):
                result=ask(message)
                self.assert_lookup(result)
                self.assertIn('Não há',result.texto)
                self.assertIn('2026-11-01 a 2026-11-05',result.texto)
                self.assertNotIn('R$',result.texto)
                self.assertIn('não confirma ausência',result.texto)

    def test_sale_interval_includes_both_endpoints(self):
        for message in SALE_RANGES:
            with self.subTest(message=message):
                result=ask(message)
                self.assert_lookup(result)
                self.assertIn('750,00',result.texto)
                self.assertIn('500,00',result.texto)
                self.assertIn('Total deste recorte fictício: R$ 1250,00',result.texto)

    def test_single_day_does_not_leak_other_rows(self):
        for day in ('2026-11-09','09/11/2026','9 de novembro de 2026','ontem'):
            with self.subTest(day=day):
                result=ask('Consulte minhas vendas de '+day)
                self.assert_lookup(result)
                self.assertIn('750,00',result.texto)
                self.assertNotIn('500,00',result.texto)
                self.assertNotIn('1250,00',result.texto)

    def test_same_date_for_sale_and_settlement_uses_different_fields(self):
        sale=ask('Consulte minhas vendas de 09/11/2026')
        receipt=ask('Consulte meus recebimentos de 09/11/2026')
        self.assertIn('750,00',sale.texto)
        self.assertNotIn('R$',receipt.texto)
        self.assertIn('créditos previstos',receipt.texto)

    def test_receipt_date_selects_expected_date(self):
        result=ask('Consulte meus recebimentos de 12/11/2026')
        self.assert_lookup(result)
        self.assertIn('750,00',result.texto)
        self.assertNotIn('500,00',result.texto)
        self.assertIn('2026-11-09',result.texto)
        self.assertIn('não comprova liquidação',result.texto)

    def test_receipt_interval_filters_both_expected_dates(self):
        result=ask('Consulte meus recebimentos de 12/11/2026 a 13/11/2026')
        self.assert_lookup(result)
        self.assertIn('Total deste recorte fictício: R$ 1250,00',result.texto)

    def test_audited_dual_dates_preserve_roles_in_both_orders(self):
        for message in DUAL_DATES:
            with self.subTest(message=message):
                query=receivable_query(message)
                self.assertEqual(query.sale_period.resolve(TODAY),(date(2026,11,9),)*2)
                self.assertEqual(query.settlement_period.resolve(TODAY),(TODAY,)*2)
                result=ask(message)
                self.assert_lookup(result)
                self.assertNotIn('De qual data',result.texto)
                self.assertIn('não há crédito previsto',result.texto)
                self.assertIn('2026-11-12, fora do período',result.texto)
                self.assertNotIn('1250',result.texto)

    def test_two_matching_roles_keep_only_intersection(self):
        result=ask('Consulte minhas vendas de 08/11/2026 a 09/11/2026 com recebimento em 12/11/2026')
        self.assert_lookup(result)
        self.assertIn('750,00',result.texto)
        self.assertNotIn('500,00',result.texto)
        self.assertNotIn('1250,00',result.texto)

    def test_relative_last_days_are_inclusive_of_reference_day(self):
        result=ask('Consulte minhas vendas dos últimos 2 dias')
        self.assertIn('2026-11-09 a 2026-11-10 (inclusive)',result.texto)
        self.assertIn('Total deste recorte fictício: R$ 750,00',result.texto)
        self.assertNotIn('500,00',result.texto)

    def test_days_ago_and_day_before_yesterday_are_equivalent(self):
        for phrase in ('há 2 dias','anteontem'):
            result=ask('Consulte minhas vendas de '+phrase)
            self.assert_lookup(result)
            self.assertIn('500,00',result.texto)
            self.assertNotIn('750,00',result.texto)

    def test_today_empty_is_not_aggregate(self):
        result=ask('Consulte minhas vendas de hoje')
        self.assertIn('Não há vendas correspondentes',result.texto)
        self.assertNotIn('R$',result.texto)

    def test_mixed_absolute_and_relative_range_resolves_once(self):
        clock=Mock(return_value=TODAY)
        tools=SyntheticTools(DEMO_PRINCIPAL,today=clock)
        result=ask('Consulte minhas vendas de 08/11/2026 a ontem',tools=tools)
        clock.assert_called_once_with()
        self.assertIn('Total deste recorte fictício: R$ 1250,00',result.texto)

    def test_bad_or_unsupported_periods_ask_before_tools(self):
        tools=Mock(principal=DEMO_PRINCIPAL)
        for message in UNSUPPORTED_PERIODS:
            with self.subTest(message=message):
                result=ask(message,tools=tools)
                self.assertEqual(result.status,'limitado')
                self.assertFalse(result.tool_traces)
                self.assertIn('Nenhuma consulta foi realizada',result.texto)
                self.assertNotIn('R$',result.texto)
        tools.consultar_recebiveis.assert_not_called()

    def test_relative_inverted_interval_is_not_reordered(self):
        result=ask('Consulte minhas vendas de hoje a ontem')
        self.assertEqual(result.status,'limitado')
        self.assertIn('posterior ao fim',result.texto)
        self.assertNotIn('R$',result.texto)

    def test_two_unconnected_days_are_not_silently_collapsed(self):
        result=ask('Consulte minhas vendas de ontem e hoje')
        self.assertEqual(result.status,'limitado')
        self.assertFalse(result.tool_traces)

    def test_contradictory_periods_across_sentences_ask(self):
        result=ask('Consulte minhas vendas de ontem. Consulte minhas vendas de hoje.')
        self.assertEqual(result.status,'limitado')
        self.assertFalse(result.tool_traces)

    def test_no_date_still_requests_sale_period(self):
        result=ask('Quando recebo minhas vendas?')
        self.assertIn('De qual data',result.texto)
        self.assertFalse(result.tool_traces)

    def test_requested_total_without_date_keeps_compatibility(self):
        for message in ('Qual é meu saldo?','Consulte meus recebíveis','Qual é o total das minhas vendas?'):
            result=ask(message)
            self.assert_lookup(result)
            self.assertIn('Recebiveis ficticios: R$ 1250,00',result.texto)

    def test_explicit_total_with_bad_period_cannot_erase_it(self):
        result=ask('Qual é o total dos meus recebíveis de 01/11 a 05/11?')
        self.assertEqual(result.status,'limitado')
        self.assertNotIn('1250',result.texto)
        self.assertFalse(result.tool_traces)

    def test_total_of_single_day_is_sum_of_selected_rows_only(self):
        result=ask('Qual é o total das minhas vendas de ontem?')
        self.assertIn('Total deste recorte fictício: R$ 750,00',result.texto)
        self.assertNotIn('1250',result.texto)

    def test_general_questions_do_not_authorize_fixture_lookup(self):
        for message in ('Qual o prazo de recebimento das vendas no crédito?',
                        'Como consultar meus recebimentos?',
                        'O que é um recebível?',
                        'Em geral, quando recebo as vendas?',
                        'Não quero consultar meus recebíveis.'):
            with self.subTest(message=message):
                self.assertFalse(classify(message).receivables)
                self.assertFalse(ask(message).tool_traces)

    def test_receipt_today_is_private_even_without_sales_noun(self):
        self.assertTrue(classify('Consulte meus recebimentos de hoje').receivables)
        result=ask('Consulte meus recebimentos de hoje')
        self.assert_lookup(result)
        self.assertNotIn('R$',result.texto)

    def test_future_sale_has_no_forecast_or_aggregate(self):
        result=ask('Consulte minhas vendas de 2026-11-11')
        self.assertEqual(result.status,'limitado')
        self.assertIn('vendas que ainda serão feitas',result.texto)
        self.assertNotIn('R$',result.texto)

    def test_future_receipt_does_not_turn_past_sale_into_future_sale(self):
        message='As vendas que fiz ontem caem amanhã?'
        self.assertTrue(classify(message).receivables)
        result=ask(message)
        self.assert_lookup(result)
        self.assertIn('2026-11-12',result.texto)
        self.assertNotIn('De qual data',result.texto)

    def test_missing_reference_cannot_be_used_for_any_period(self):
        tools=Mock(principal=DEMO_PRINCIPAL)
        tools.consultar_recebiveis.return_value={'simulated':True,'currency':'BRL','total_centavos':125000}
        result=ask('Consulte minhas vendas de ontem',tools=tools)
        self.assertEqual(result.status,'limitado')
        self.assertNotIn('R$',result.texto)
        self.assertIn('referência válida',result.texto)

    def test_period_in_following_sentence_cannot_be_discarded(self):
        for message in ('Consulte meus recebíveis. De 2026-11-01 a 2026-11-05.',
                        'Consulte minhas vendas. O período é de 2026-11-01 a 2026-11-05.'):
            result=ask(message)
            self.assert_lookup(result)
            self.assertIn('2026-11-01 a 2026-11-05',result.texto)
            self.assertNotIn('R$',result.texto)

    def test_explicit_date_field_is_not_discarded_as_unsupported(self):
        result=ask('Consulte meus recebíveis pela data de recebimento de 12/11/2026')
        self.assert_lookup(result)
        self.assertIn('750,00',result.texto)
        self.assertNotIn('500,00',result.texto)
        result=ask('Consulte meus recebíveis pela data da venda de 09/11/2026')
        self.assert_lookup(result)
        self.assertIn('750,00',result.texto)

    def test_other_topic_date_does_not_restrict_balance(self):
        result=ask('Consulte meu saldo. Minha maquininha ficou offline ontem.')
        self.assertIn('Recebiveis ficticios: R$ 1250,00',result.texto)
        self.assertIn('DEMO-A-001',result.texto)

    def test_card_modality_is_not_a_settlement_date_cue(self):
        result=ask('Consulte minhas vendas no crédito à vista de ontem')
        self.assert_lookup(result)
        self.assertIn('750,00',result.texto)
        self.assertNotIn('Não há créditos',result.texto)

    def test_legacy_query_constructor_remains_available(self):
        self.assertFalse(ReceivableQuery(False).individual)
        query=receivable_query('Consulte minhas vendas de ontem')
        self.assertEqual(query.period,'yesterday')
        self.assertIn('sale_period',asdict(query))

    def test_http_audited_range_does_not_use_total(self):
        client=TestClient(create_app(mode='rag',enable_web=False))
        with patch('app.support.simulation_date',return_value=TODAY):
            response=client.post('/chat',json={'message':EMPTY_RANGES[0],'user_id':'cliente1988'}).json()
        self.assertEqual(response['route'],'support')
        self.assertIn('Não há',response['answer'])
        self.assertNotIn('1250',response['answer'])
        self.assertEqual([e['ferramenta'] for e in response['eventos'] if e['ferramenta']],['consultar_recebiveis'])

    def test_http_dual_dates_keep_temporal_constraint(self):
        client=TestClient(create_app(mode='rag',enable_web=False))
        with patch('app.support.simulation_date',return_value=TODAY):
            response=client.post('/chat',json={'message':DUAL_DATES[0],'user_id':'cliente1988'}).json()
        self.assertIn('2026-11-12, fora do período',response['answer'])
        self.assertNotIn('De qual data',response['answer'])


if __name__=='__main__':
    unittest.main()
