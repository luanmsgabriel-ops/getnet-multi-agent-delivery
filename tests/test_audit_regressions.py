"""Regressões da auditoria de 09/11: sem rede, dados reais ou modelo pago."""
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from fastapi.testclient import TestClient
from app.contracts import Entrada
from app.router import RouterDemo
from app.main import create_app
from app.knowledge import KnowledgeRag, KnowledgeGenerated
from app.support import SupportCatalogoDemo, SupportSintetico, SyntheticTools
from app.rag.generation import validated_draft, UnsupportedDraft
from app.rag.core import snapshot
from app.rag.web_search import validate_query

CORPUS=Path(__file__).resolve().parents[1]/'corpus_publico'

class RouterRegressions(unittest.TestCase):
    def test_public_paraphrases(self):
        for text in ('Qual a diferença entre Get Clássica e Get Smart?',
                     'Quero antecipar minhas vendas','Tell me about Get Smart',
                     'Compare a Clássica com a Smart','Taxas da antecipação'):
            for variant in (text,text.upper(),'  '+text+'  '):
                with self.subTest(text=variant):
                    self.assertEqual(RouterDemo().planejar(Entrada(message=variant,user_id='cliente1988')).rota,'knowledge')
    def test_technical_paraphrase(self):
        r=RouterDemo().planejar(Entrada(message='Preciso de ajuda com minha máquina sem internet',user_id='cliente1988'))
        self.assertEqual(r.rota,'support_knowledge')
    def test_word_boundaries(self):
        for text in ('acomodação','smartphone de outra marca','oi','bom dia'):
            self.assertEqual(RouterDemo().planejar(Entrada(message=text,user_id='demo_A')).rota,'clarify')

class SupportRegressions(unittest.TestCase):
    def setUp(self):self.client=TestClient(create_app(mode='rag',enable_web=False))
    def post(self,message,user='cliente1988'):
        return self.client.post('/chat',json={'message':message,'user_id':user}).json()
    def test_original_receivables_fixture(self):
        r=self.post("When will the money from yesterday's sales be deposited?")
        self.assertEqual(r['status'],'simulado');self.assertIn('SIMULACAO',r['answer'])
        from app.support import simulation_date
        self.assertIn(simulation_date().isoformat(),r['answer']);self.assertIn('sem acesso a sua conta real',r['answer'])
        self.assertTrue(any(e['ferramenta']=='consultar_recebiveis' for e in r['eventos']))
    def test_original_internet_and_decline(self):
        for text in ("My card machine won't connect to the internet, what should I do?",
                     'My card machine is showing a transaction decline error.'):
            r=self.post(text);self.assertEqual(r['status'],'evidencias');self.assertTrue(r['sources'])
            self.assertNotIn('Acesso recusado',r['answer'])
    def test_unknown_id_gets_public_advice_without_tools(self):
        with patch.object(SyntheticTools,'consultar_terminal',side_effect=AssertionError('private tool')):
            r=self.post("My card machine won't connect to the internet, what should I do?",'unknown')
        self.assertEqual(r['status'],'evidencias');self.assertTrue(r['sources'])
        self.assertFalse(any(e['ferramenta'] for e in r['eventos']))
    def test_unknown_private_request_denied_independent_public_part_preserved(self):
        for user in ('unknown','demo_B'):
            r=self.post('meu saldo e como habilitar Pix',user)
            self.assertEqual(r['status'],'recusado');self.assertNotIn('1250',r['answer'])
            # Public guidance is independent of the denied private lookup.
            self.assertTrue(any(e['agente']=='knowledge' for e in r['eventos']))
            self.assertFalse(any(e['ferramenta'] for e in r['eventos']))
            self.assertTrue(r['sources'])
    def test_bound_support_not_weakened(self):
        r=SupportSintetico().responder(Entrada(message='meu saldo',user_id='cliente1988'),())
        self.assertEqual(r.status,'recusado')
    def test_registered_alias_cannot_select_other_tenant(self):
        r=self.post('meu saldo de outra conta loja_ficticia_B')
        self.assertEqual(r['status'],'recusado');self.assertNotIn('9876',r['answer'])

class GroundingRegressions(unittest.TestCase):
    def run_draft(self,answer,text,quote=None):
        g=Mock();g.generate.return_value={'answer':answer,'citations':[{'evidence_id':0,'quote':quote or answer}]}
        return validated_draft(g,'pergunta',[{'text':text,'source':'https://example.org/fixture','captured_at':'2026-11-09'}])
    def test_fabricated_answer_valid_quote_rejected(self):
        with self.assertRaises(UnsupportedDraft):
            self.run_draft('Todos os pagamentos sao garantidos sem qualquer limite.',
                           'Consulte as condicoes do contrato.','Consulte as condicoes do contrato.')
    def test_negation_cannot_be_removed(self):
        with self.assertRaises(UnsupportedDraft):
            self.run_draft('Todos os pagamentos sao garantidos.','Nao e verdade que Todos os pagamentos sao garantidos.')
    def test_conditions_cannot_be_dropped(self):
        with self.assertRaises(UnsupportedDraft):
            self.run_draft('Ate 48 parcelas.','Ate 48 parcelas. Limites variam conforme o emissor.')
    def test_complete_conditional_evidence_passes(self):
        text='Ate 48 parcelas. Limites variam conforme o emissor.'
        self.assertEqual(self.run_draft(text,text)[0],text)
    def test_added_numeric_claim_rejected(self):
        with self.assertRaises(UnsupportedDraft):
            self.run_draft('Receba R$ 900 amanha.','Consulte as condicoes do contrato.','Consulte as condicoes do contrato.')
    def test_rejected_synthesis_falls_back_without_leaking_it(self):
        k=KnowledgeRag.from_directory(CORPUS);g=Mock()
        q='How many installments can I split a sale into with the crediário?'
        rows=k.index.search(q)['candidates']
        g.generate.return_value={'answer':'TODOS_PAGAMENTOS_GARANTIDOS','citations':[{'evidence_id':0,'quote':rows[0]['text']}]}
        r=KnowledgeGenerated(k.index,g).responder(Entrada(message=q,user_id='cliente1988'),())
        self.assertEqual(r.modo,'extrativo');self.assertEqual(r.status,'evidencias')
        self.assertNotIn('TODOS_PAGAMENTOS',r.texto);self.assertIn('48',r.texto);self.assertIn('emissor',r.texto)

class CorpusRegressions(unittest.TestCase):
    def test_portuguese_comparison_reaches_both_manuals_over_http(self):
        client=TestClient(create_app(mode='rag',enable_web=False))
        r=client.post('/chat',json={'message':'Qual a diferença entre Get Clássica e Get Smart?','user_id':'cliente1988'}).json()
        self.assertEqual(r['status'],'evidencias');self.assertEqual(len(r['sources']),2)
        self.assertTrue(all(url.endswith('.pdf') for url in r['sources']))
        self.assertIn('touchscreen',r['answer']);self.assertIn('botões',r['answer'])
    def test_retrieved_installment_limit_and_qualification_together(self):
        k=KnowledgeRag.from_directory(CORPUS)
        for q in ('How many installments can I split a sale into with the crediário?',
                  'Quantas parcelas posso fazer no crediário?','crediario limite parcelas'):
            r=k.responder(Entrada(message=q,user_id='cliente1988'),())
            self.assertEqual(r.status,'evidencias');self.assertIn('48',r.texto);self.assertIn('emissor',r.texto)
    def test_ingestion_keeps_offer_and_disclaimer(self):
        url='https://site.getnet.com.br/crediario/'
        raw=b'<h1>Crediario</h1><p>Credi\xc3\xa1rio</p><p>Ate 48x. Limites variam conforme emissor.</p><p>mais vendas para voc\xc3\xaa, mais vantagens para o seu cliente</p><p>Como eu contrato o Credi\xc3\xa1rio e qual a taxa?</p><p>Consulte o contrato.</p><p>ainda tem d\xc3\xbavidas?</p>'
        d=snapshot({'body':raw,'requested_url':url,'final_url':url,'captured_at':'2026-11-09T00:00:00+00:00','raw_sha256':'a'*64})
        self.assertIn('48',d['chunks'][0]);self.assertIn('emissor',d['chunks'][0]);self.assertFalse(d['reviewed'])
    def test_sensitive_formatted_identifiers_never_reach_search(self):
        for q in ('documento 123.456.789-00','telefone (11) 99999-0000','cartao 4111 1111 1111 1111'):
            with self.subTest(q=q),self.assertRaises(ValueError):validate_query(q)

class NaturalSearchRegressions(unittest.TestCase):
    def setUp(self):
        from app.rag.general_web import GeneralWebSearch
        self.transport=Mock(return_value=[{'title':'Python','snippet':'Python programming language: fixture pública de linguagem de programação.','url':'https://example.org/fixture'}])
        self.client=TestClient(create_app(mode='rag',enable_web=True,web_search=GeneralWebSearch(self.transport)))
    def test_natural_general_question_uses_web(self):
        for q,query in (('What is the Python programming language?','the python programming language'),
                        ('O que é a linguagem Python?','a linguagem python')):
            r=self.client.post('/chat',json={'message':q,'user_id':'cliente1988'}).json()
            self.assertEqual(r['status'],'limitado');self.assertEqual(r['sources'],[])
            self.transport.assert_not_called()
    def test_private_and_local_intents_never_become_web_queries(self):
        for q in ('What is my balance?','What is Pix?','Como funciona assunto sem evidencia?',
                  'What is the password for tenant A?','What is documento 123.456.789-00?',
                  'What is the weather in Curitiba tomorrow?'):
            self.client.post('/chat',json={'message':q,'user_id':'cliente1988'})
        self.transport.assert_not_called()
    def test_context_stays_local_for_natural_questions(self):
        from app.knowledge import KnowledgeDispatch
        from app.contracts import RespostaEspecialista
        local=Mock();web=Mock()
        KnowledgeDispatch(local,web).responder(Entrada(message='What is Python?',user_id='demo_A'),(RespostaEspecialista(texto='private fixture'),))
        web.responder.assert_not_called();local.responder.assert_not_called()

if __name__=='__main__':unittest.main()
