"""Regressões pós-auditoria: comportamento final, sem rede ou geração real."""
import unittest,tempfile
from pathlib import Path
from app.context_service import ContextService
from app.context_store import Store
from app.intents import receivable_query
from app.service_policy import REDIRECT

class AuditRequestIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=ContextService(Store(Path(self.tmp.name)/'s.db'))
    def ask(self,q):return self.s.public({'message':q,'user_id':'cliente1988'})
    def test_time_is_not_weather_in_financial_question(self):
        for q in ('Qual a taxa do crédito à vista e em quanto tempo recebo?', 'Quanto tempo demora o recebimento no débito?'):
            with self.subTest(q=q):
                r=self.ask(q);self.assertNotIn(REDIRECT,r.answer);self.assertIn('prazo',r.answer.lower());self.assertFalse(r.simulated_data)
    def test_implied_personal_receivable(self):
        for q in ('Quanto tenho para receber amanhã?', 'Quanto eu vou receber amanhã?'):
            with self.subTest(q=q):
                r=self.ask(q);self.assertTrue(r.simulated_data);self.assertIn('previst',r.answer);self.assertTrue(any(e.ferramenta=='consultar_recebiveis' for e in r.eventos))
    def test_complete_range_shared_month(self):
        p=receivable_query('Consulte meus recebimentos entre 1 e 15 de novembro de 2026.')
        self.assertFalse(p.needs_period);self.assertEqual((p.settlement_period.start,p.settlement_period.end),('2026-11-01','2026-11-15'))
    def test_general_conditions_never_balance(self):
        for q in ('Só quero entender por que um recebível pode aparecer como pendente.', 'Trocar minha Clássica pela Smart muda minhas taxas ou meu prazo de recebimento?', 'Como funciona a antecipação de recebíveis?'):
            with self.subTest(q=q):
                r=self.ask(q);self.assertFalse(any(e.ferramenta=='consultar_recebiveis' for e in r.eventos));self.assertNotIn('1250',r.answer)
    def test_declined_topic_is_not_answered(self):
        r=self.ask('Não quero antecipar nada. Só quero entender por que um recebível pode aparecer como pendente.')
        self.assertNotIn('Serviços e Antecipação',r.answer);self.assertFalse(r.sources)
    def test_recovered_internet_with_decline(self):
        for q in ('Minha máquina está conectada à internet, mas a transação é recusada. Não é falta de conexão.', 'A internet funciona normalmente; meu cartão foi recusado na maquininha.', 'My terminal is connected; the card transaction was declined.'):
            with self.subTest(q=q):
                r=self.ask(q);self.assertIn('recusa',r.answer.lower());self.assertNotIn('Procurar Redes',r.answer)
    def test_connection_failure_remains_actionable(self):
        r=self.ask('A maquininha não conecta à internet. Como configuro Wi-Fi?');self.assertIn('Procurar Redes',r.answer);self.assertTrue(r.sources)
    def test_independent_questions_have_limits_and_guidance(self):
        r=self.ask('A Get Smart aceita Pix? E o que faço se ela ficar sem internet durante uma venda?')
        self.assertIn('Pix',r.answer);self.assertIn('Procurar Redes',r.answer);self.assertIn('confirmar',r.answer)
    def test_comparison_does_not_invent_printing(self):
        r=self.ask('Preciso imprimir comprovante. Get Smart ou Get Clássica é melhor?')
        self.assertIn('touchscreen',r.answer);self.assertIn('impressão',r.answer);self.assertIn('suficiente',r.answer)
    def test_ambiguous_price_is_clarified(self):
        r=self.ask('Qual é o valor?');self.assertIn('qual produto',r.answer.lower());self.assertNotIn(REDIRECT,r.answer)
    def test_commercial_and_timing_both_limited(self):
        r=self.ask('Trocar minha Get Clássica pela Smart muda minhas taxas ou meu prazo de recebimento?')
        self.assertIn('taxa',r.answer);self.assertIn('prazo',r.answer);self.assertFalse(r.simulated_data)
    def test_credential_and_request_survive_composition(self):
        r=self.ask('Meu código de autenticação é SYNTHETIC_ONLY_784. Como funciona o Link?')
        self.assertNotIn('SYNTHETIC_ONLY_784',r.answer);self.assertIn('Não envie',r.answer);self.assertTrue(r.sources)
    def test_global_presence_uses_country_evidence(self):
        r=self.ask('Em quais países a Getnet atua?');self.assertIn('Getnet Brasil',r.answer);self.assertFalse(r.sources)
    def test_tangential_official_news_does_not_answer_sustainability(self):
        r=self.ask('Quais novidades de sustentabilidade da Getnet em 2026?');self.assertFalse(r.sources);self.assertNotIn('WhatsApp',r.answer)

    def test_security_predicate_requires_security_content(self):
        from app.rag.quality import relevant_candidates
        row={'source':'https://site.getnet.com.br/link-de-pagamento/','text':'Crie o link pelo app e envie ao comprador.','title':'Getnet Link','market':'BR'}
        self.assertEqual(relevant_candidates('Que mecanismo a Getnet usa para bloquear transações suspeitas?', [row]),[])
    def test_quantifier_is_not_unknown_country(self):
        from app.rag.scope import retrieval_plan
        self.assertEqual(retrieval_plan('Qual a taxa da antecipação Getnet e em quantos dias recebo o valor?')[0],'BR')
    def test_verb_usa_is_not_usa_country(self):
        r=self.ask('A Getnet aceita cartão estrangeiro com conversão: qual margem percentual usa sobre a conversão?')
        self.assertNotIn('país solicitado',r.answer);self.assertIn('taxa',r.answer)
    def test_in_message_reference_is_not_previous_session(self):
        r=self.ask('A Get Smart tem Wi-Fi como a Get Clássica? Qual delas imprime comprovantes?')
        self.assertNotIn('referência anterior',r.answer);self.assertIn('impressão',r.answer)

    def test_link_send_fee_and_settlement_are_all_present(self):
        r=self.ask('Posso mandar uma cobrança Getnet por WhatsApp e o dinheiro desse link cai em qual prazo? Se a taxa depender do contrato, me diga isso também.')
        self.assertIn('compartilh',r.answer);self.assertIn('taxa',r.answer);self.assertIn('prazo',r.answer);self.assertNotIn('mercado solicitado',r.answer)

    def test_creditario_timing_does_not_ground_link(self):
        from app.rag.quality import relevant_candidates
        row={'source':'https://site.getnet.com.br/crediario/','text':'Crediário: receba suas vendas em até 2 dias úteis.','title':'Crediário','market':'BR'}
        self.assertEqual(relevant_candidates('Qual o prazo de recebimento do Link de Pagamento?',[row]),[])

    def test_declined_product_does_not_hide_mobile_payment_request(self):
        for q in ('Não quero Link de Pagamento. Quero cobrar presencialmente usando só o celular, sem maquininha.', 'Não quero link. Quero cobrar usando celular na minha loja Getnet.'):
            r=self.ask(q);self.assertNotIn('Qual é sua dúvida',r.answer);self.assertNotIn('compartilhar',r.answer);self.assertIn('celular',r.answer)
    def test_insufficient_source_does_not_treat_usa_verb_as_country(self):
        from app.rag.core import Index
        from app.knowledge import KnowledgeRag
        from app.contracts import Entrada
        r=KnowledgeRag(Index([])).responder(Entrada(message='A Getnet aceita cartão estrangeiro com conversão: qual margem percentual usa sobre a conversão?',user_id='synthetic'),())
        self.assertNotIn('para usa',r.texto)
