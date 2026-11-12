"""Regressões da revisão 10/11: intenção/atributo/período/privacidade/mercado.
Todas as identidades/credenciais são sintéticas. Sem rede ou modelo real.
"""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
from fastapi.testclient import TestClient
from app.context_service import ContextService
from app.context_store import Store
from app.contracts import Entrada
from app.intents import classify,receivable_query
from app.knowledge import KnowledgeRag
from app.rag.scope import retrieval_plan
from app.rag.quality import attribute_candidates
from app.privacy import clean_message
from app.support import SupportSintetico,SyntheticTools,DEMO_PRINCIPAL

class Closure(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.service=ContextService(Store(Path(self.tmp.name)/'state.db'))
    def ask(self,message):
        return self.service.public({'message':message,'user_id':'cliente1988'})
    def test_general_advance_does_not_request_private_data(self):
        for q in ('Como funciona a antecipação de recebíveis?','Explique antecipação sem consultar meu saldo.', 'How does receivables advance work with Getnet?'):
            with self.subTest(q=q):
                r=self.ask(q)
                self.assertFalse(any(e.ferramenta for e in r.eventos))
                self.assertIn('simular',r.answer);self.assertIn('crédito',r.answer)
                self.assertTrue(r.sources)
    def test_own_sales_without_period_asks_before_tool(self):
        for q in ('Quando vou receber minhas vendas?','Quero consultar minhas vendas','When will my sales be deposited?'):
            with self.subTest(q=q):
                r=self.ask(q)
                self.assertEqual(r.route,'support');self.assertIn('data',r.answer)
                self.assertFalse(any(e.ferramenta for e in r.eventos));self.assertNotIn('R$',r.answer)
    def test_today_is_not_yesterday_or_total_balance(self):
        for q in ('Quero consultar minhas vendas de hoje','Consulte as vendas que fiz hoje','Check my sales today'):
            with self.subTest(q=q):
                r=self.ask(q)
                self.assertEqual([e.ferramenta for e in r.eventos if e.ferramenta],['consultar_recebiveis'])
                self.assertIn('Não há vendas correspondentes',r.answer)
                self.assertNotIn('1250',r.answer)
    def test_yesterday_and_balance_preserved(self):
        for q in ('Quando recebo vendas de ontem?', 'Qual é meu saldo?', 'What is my balance?'):
            with self.subTest(q=q):
                r=self.ask(q);self.assertTrue(any(e.ferramenta=='consultar_recebiveis' for e in r.eventos))
                self.assertIn('R$',r.answer)
    def test_private_and_general_parts_are_both_answered(self):
        r=self.ask('Quando vou receber minhas vendas? Como funciona a antecipação de recebíveis?')
        self.assertIn('data',r.answer);self.assertIn('simular',r.answer)
        self.assertFalse(any(e.ferramenta for e in r.eventos))
    def test_price_and_fee_do_not_return_manual_as_price(self):
        for q in ('Quanto custa a Get Smart?','Qual o preço da Get Clássica?','Quais as taxas da Get Smart?','What is the price of Get Smart?'):
            with self.subTest(q=q):
                r=self.ask(q);self.assertIn('Não consigo confirmar',r.answer)
                self.assertFalse(r.sources);self.assertNotIn('touchscreen',r.answer.lower())
    def test_comparison_and_price_preserve_both_attributes(self):
        r=self.ask('Compare Get Smart e Get Clássica; quanto custa a Get Smart?')
        self.assertIn('touchscreen',r.answer);self.assertIn('Não consigo confirmar',r.answer)
    def test_price_evidence_must_contain_price_and_conditions(self):
        source={'title':'Oferta Get Smart, somente plano X','text':'Preço da Get Smart: R$ 99 para plano X.','source':'https://site.getnet.com.br/'}
        self.assertEqual(attribute_candidates('Qual o preço da Get Smart?',[source]),[source])
        minimum={**source,'text':'Valor mínimo de antecipação R$ 50. Simule taxas.'}
        self.assertEqual(attribute_candidates('Qual taxa da Get Smart?',[minimum]),[])
    def test_quantity_is_not_market_and_country_is_still_checked(self):
        for q in ('Como vender no crediário em 12 parcelas?', 'Crediário em 6 parcelas', 'Crediário em até 24 prestações', 'Crediário in twelve installments'):
            with self.subTest(q=q):
                self.assertEqual(retrieval_plan(q)[0],'BR')
        for q in ('Crediário em 12 parcelas no Canadá','Crediário em doze parcelas em Portugal','Crediário em Marte'):
            self.assertIsNone(retrieval_plan(q)[0])
    def test_context_preserves_today_instead_of_requesting_total(self):
        message='Quero consultar minhas vendas de hoje';sid=self.service.create('cliente1988')
        proposal={'devices':[],'observations':[],'focus':[],'resolve_pending':[],'requests':[{'kind':'information','topic':'settlement','entities':[],'quote':message}]}
        r=self.service.step('cliente1988',sid,message,proposal=proposal)
        self.assertIn('Não há vendas correspondentes',r['answer']);self.assertNotIn('1250',r['answer'])
    def test_disclosure_spans_cover_qualifiers_and_multiword_values(self):
        cases=[('Minha senha de acesso é "SYN_ALPHA SYN_BRAVO SYN_CHARLIE". Onde digito?',['SYN_ALPHA','SYN_BRAVO','SYN_CHARLIE']),
               ('Meu token = alpha.beta.gamma. Como usar Link?',['alpha','beta','gamma']),
               ('My verification code is 765432. What next?',['765432']),
               ('O código recebido por SMS é 876543. Onde uso?',['876543'])]
        for message,values in cases:
            safe,changed=clean_message(message);self.assertTrue(changed)
            for value in values:self.assertNotIn(value,safe)
            self.assertIn('?',safe)
    def test_nonsecret_state_and_instructions_are_preserved(self):
        for q in ('A senha é digitada no aparelho.','My password is not accepted by the terminal.', 'A senha é de seis dígitos ou oito?', 'Onde digitar a senha?', 'My password is incorrect.'):
            self.assertEqual(clean_message(q),(q,False))
    def test_stateless_market_not_lost_when_password_mentioned(self):
        r=self.ask('Como configurar Wi-Fi na maquininha Getnet no Chile? Onde digito a senha?')
        self.assertNotIn('Procurar Redes',r.answer);self.assertNotIn('tela principal',r.answer)
        self.assertFalse(any('get-ajuda-configuracoes' in x for x in r.sources))
    def test_fallback_keeps_previous_country(self):
        sid=self.service.create('cliente1988');version,state=self.service.store.read('cliente1988',sid)
        state['context']={'country':{'value':'Chile','origin':'customer','status':'asserted'}}
        self.service.store.commit('cliente1988',sid,version,state)
        self.service.interpreter=Mock();self.service.interpreter.interpret.side_effect=TimeoutError('synthetic')
        r=self.service.step('cliente1988',sid,'Como configurar o Wi-Fi? Onde digito a senha?')
        self.assertEqual(r['mode'],'scope_policy');self.assertNotIn('Procurar Redes',r['answer'])
        self.assertEqual(self.service.state('cliente1988',sid),state)
    def test_dcc_bytes_stay_verified(self):
        from app.service_policy import dcc_available
        self.assertTrue(dcc_available())

    def test_independent_attribute_and_definition_regressions(self):
        for q in ('Qual a mensalidade da Smart?','What is the monthly cost of Smart?'):
            r=self.ask(q);self.assertIn('Não consigo confirmar',r.answer);self.assertNotIn('touchscreen',r.answer)
        r=self.ask('Explique antecipação de recebíveis e diga a taxa da Smart.')
        self.assertIn('simular',r.answer);self.assertIn('Não consigo confirmar',r.answer)
        r=self.ask('O que são recebíveis?');self.assertFalse(r.sources);self.assertFalse(any(e.ferramenta for e in r.eventos))
    def test_pix_account_question_is_not_individual_receivable(self):
        for q in ('Do I need a bank account to receive my sales via Pix?','Preciso de conta para receber minhas vendas via Pix?'):
            r=self.ask(q);self.assertFalse(any(e.ferramenta for e in r.eventos));self.assertNotIn('De qual data',r.answer);self.assertTrue(r.sources)
    def test_future_sale_not_forecast_from_fixture(self):
        r=self.ask('Quando recebo as vendas que farei amanhã?')
        self.assertIn('ainda não realizadas',r.answer);self.assertFalse(any(e.ferramenta for e in r.eventos))
    def test_installment_quantity_keeps_offer_and_condition(self):
        for q in ('Posso vender no crediário em 6 vezes?', 'Crediário em 48 parcelas no Brasil'):
            r=self.ask(q);self.assertTrue(r.sources);self.assertIn('48',r.answer);self.assertIn('emissor',r.answer)
    def test_chile_link_costs_not_free_creation_as_free_transactions(self):
        r=self.ask('Qual a taxa do Link de Pagamento Getnet no Chile?')
        self.assertFalse(r.sources);self.assertIn('Getnet Brasil',r.answer);self.assertNotIn('MDR',r.answer)
    def test_foreign_composition_cannot_restore_brazil(self):
        r=self.ask('Compare Smart e Clássica; qual taxa do Link no Chile?')
        self.assertTrue(r.sources);self.assertTrue(all('getnet.com.br' in x for x in r.sources));self.assertIn('Getnet Brasil',r.answer);self.assertIn('touchscreen',r.answer)
    def test_chile_wifi_for_unknown_customer_has_country_limitation(self):
        r=self.service.public({'message':'Como configurar Wi-Fi na maquininha Getnet no Chile? Onde digito a senha?','user_id':'synthetic_unknown'})
        self.assertIn('Getnet Brasil',r.answer);self.assertNotIn('Procurar Redes',r.answer)

    def test_query_date_is_not_an_ambiguous_device_fact(self):
        q="When will the money from yesterday's sales be deposited?";sid=self.service.create('cliente1988')
        proposal={'devices':[],'observations':[{'entity':None,'incident':'','field':'date','value':'yesterday','status':'asserted','origin':'customer','quote':q}], 'focus':[],'resolve_pending':[],'requests':[{'kind':'information','topic':'settlement','entities':[],'quote':q}]}
        r=self.service.step('cliente1988',sid,q,proposal=proposal)
        self.assertFalse(r['state']['pending']);self.assertNotIn('A qual aparelho',r['answer'])
        self.assertEqual(r['state']['observations'][0]['role'],'query_parameter');self.assertFalse(r['state']['observations'][0]['actionable'])
    def test_missing_service_reference_does_not_create_wifi_goal(self):
        q='Where do I enter it?';sid=self.service.create('synthetic')
        p={'devices':[],'observations':[],'focus':[],'resolve_pending':[],'requests':[{'kind':'information','topic':'connectivity','entities':[],'quote':q}]}
        r=self.service.step('synthetic',sid,q,proposal=p)
        self.assertFalse(r['state']['goals']);self.assertNotIn('Procurar Redes',r['answer']);self.assertIn('assunto',r['answer'])
    def test_period_followup_preserves_today(self):
        sid=self.service.create('cliente1988');q='hoje'
        p={'devices':[],'observations':[],'focus':[],'resolve_pending':[],'requests':[{'kind':'information','topic':'settlement','entities':[],'quote':q}]}
        r=self.service.step('cliente1988',sid,q,proposal=p)
        self.assertIn('Não há vendas correspondentes',r['answer']);self.assertNotIn('1250',r['answer'])
    def test_commercial_goal_has_its_own_contract(self):
        sid=self.service.create('synthetic');q='Qual a mensalidade da Smart?'
        p={'devices':[],'observations':[],'focus':[],'resolve_pending':[],'requests':[{'kind':'information','topic':'commercial','entities':[],'quote':q}]}
        r=self.service.step('synthetic',sid,q,proposal=p)
        self.assertIn('Não consigo confirmar',r['answer']);self.assertEqual(r['state']['goals'][0]['topic'],'commercial')

    def test_ambiguous_topic_cannot_hide_explicit_unsupported_action(self):
        for action,q in [('transfer_funds','Transfira o saldo da minha conta.'),('cancel_registration','Cancele meu cadastro.')]:
            sid=self.service.create('synthetic')
            p={'devices':[],'observations':[],'focus':[],'resolve_pending':[],'requests':[{'kind':'unsupported_action','action':action,'topic':'connectivity','entities':[],'quote':q}]}
            r=self.service.step('synthetic',sid,q,proposal=p)
            self.assertEqual(r['state']['requests'][0]['kind'],'unsupported_action');self.assertIn('Não tenho ferramenta',r['answer']);self.assertNotIn('Preciso identificar',r['answer'])

if __name__=='__main__':unittest.main()
