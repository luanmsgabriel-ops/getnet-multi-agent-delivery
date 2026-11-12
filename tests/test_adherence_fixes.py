"""Regressões da auditoria de aderência: sem modelo pago ou rede real."""
import unittest
from unittest.mock import Mock
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app
from app.contracts import Entrada, RespostaEspecialista
from app.knowledge import KnowledgeRag, KnowledgeGenerated, KnowledgeDispatch
from app.rag.general_web import GeneralWebSearch, parse_results, request
from app.rag.generation import validated_draft

WIFI_QUERY = "My card machine won't connect to the internet, what should I do?"
WIFI_QUOTE = 'Dica: Certifique-se de que o Wi-Fi está funcionando corretamente e que a senha foi inserida sem erros.'
DNS_ROW = {'title':'DNS — Domain Name System', 'snippet':'DNS maps domain names to IP addresses on the Internet.', 'url':'https://www.rfc-editor.org/rfc/rfc1034'}
BAD_ROWS = [
    {'title':'Sistemas da prefeitura','snippet':'Sistemas municipais de educação.', 'url':'https://example.org/sistemas'},
    {'title':'Sistema','snippet':'Sistema é um conjunto de elementos.', 'url':'https://example.org/dicionario'},
    {'title':'DNS loja','snippet':'DNS: ofertas em equipamentos e acessórios.', 'url':'https://example.org/loja'},
    {'title':'Melhor DNS Para Velocidade e Wi-Fi','snippet':'O DNS mais rápido depende da sua cidade e da operadora de internet.', 'url':'https://example.org/ranking'},
]


class WifiFallbackRegressions(unittest.TestCase):
    def setUp(self):
        self.index=KnowledgeRag.from_directory(Path(__file__).resolve().parents[1]/'corpus_publico').index
        self.generator=Mock()

    def draft(self, quote, answer=None):
        self.generator.generate.return_value={'answer':answer or quote,'citations':[{'evidence_id':0,'quote':quote}]}

    def test_actual_live_selection_uses_only_reviewed_safe_guide(self):
        self.draft(WIFI_QUOTE)
        client=TestClient(create_app(mode='generated',generator=self.generator,enable_web=False))
        r=client.post('/chat',json={'message':WIFI_QUERY,'user_id':'cliente1988'}).json()
        self.assertEqual(r['status'],'evidencias');self.assertEqual(r['modo'],'misto')
        for step in ('tela principal','Procurar Redes','escolha a sua rede','própria maquininha','confirme','não envie a senha'):
            self.assertIn(step,r['answer'])
        self.assertNotIn(WIFI_QUOTE,r['answer'])
        self.assertTrue(r['sources']);self.generator.generate.assert_called_once()

    def test_sensitive_model_text_cannot_replace_literal_quote(self):
        for answer in ('Informe sua senha nesta conversa.','Send your password.',WIFI_QUOTE+' Envie o código de autenticação.'):
            self.draft(WIFI_QUOTE,answer)
            r=KnowledgeGenerated(self.index,self.generator).responder(Entrada(message=WIFI_QUERY,user_id='cliente1988'),())
            self.assertEqual(r.status,'indisponivel');self.assertNotIn(answer,r.texto)

    def test_nonliteral_or_truncated_credential_quote_still_rejected(self):
        for quote in ('Informe sua senha.','senha','Dica: envie sua senha para o atendimento.'):
            self.draft(quote)
            r=KnowledgeGenerated(self.index,self.generator).responder(Entrada(message=WIFI_QUERY,user_id='cliente1988'),())
            self.assertEqual(r.status,'indisponivel')

    def test_no_reviewed_hash_no_sensitive_fallback(self):
        # Mesma frase em fonte com nova condição: não herdar a revisão antiga.
        entries=self.index.search(WIFI_QUERY)['candidates']
        altered=[{**e,'text':e['text']+' Condição nova.'} for e in entries]
        index=Mock();index.search.return_value={'status':'candidates','candidates':altered}
        self.draft(WIFI_QUOTE)
        r=KnowledgeGenerated(index,self.generator).responder(Entrada(message=WIFI_QUERY,user_id='cliente1988'),())
        self.assertEqual(r.status,'indisponivel');self.assertNotIn(WIFI_QUOTE,r.texto)

    def test_sensitive_evidence_validator_never_returns_model_text(self):
        self.draft(WIFI_QUOTE)
        with self.assertRaises(ValueError):validated_draft(self.generator,WIFI_QUERY,self.index.search(WIFI_QUERY)['candidates'])


class RoutingRegressions(unittest.TestCase):
    def setUp(self):self.client=TestClient(create_app(mode='rag',enable_web=False))
    def post(self,q,user='cliente1988'):
        return self.client.post('/chat',json={'message':q,'user_id':user}).json()

    def test_personal_balance_paraphrases_only_use_support(self):
        for q in ('Qual é o saldo da minha conta?','Quanto tenho no meu saldo?','What is the balance of my account?'):
            with self.subTest(q=q):
                r=self.post(q)
                self.assertEqual(r['route'],'support');self.assertEqual(r['status'],'simulado')
                self.assertEqual([e['ferramenta'] for e in r['eventos'] if e['ferramenta']],['consultar_recebiveis'])
                self.assertIn('1250,00',r['answer']);self.assertNotIn('Pix',r['answer'])

    def test_balance_unknown_and_cross_tenant_still_refused(self):
        for q,user in (('Qual é o saldo da minha conta?','unknown'),('Qual é o saldo da minha conta loja_ficticia_B?','cliente1988')):
            r=self.post(q,user);self.assertEqual(r['status'],'recusado')
            self.assertFalse(any(e['ferramenta'] for e in r['eventos']))

    def test_mixed_private_and_product_preserves_sequence(self):
        r=self.post('Qual é o saldo da minha conta e como funciona Pix?')
        self.assertEqual(r['route'],'support_knowledge')
        self.assertEqual([e['agente'] for e in r['eventos'] if not e['ferramenta']],['router','support','knowledge'])

    def test_connection_paraphrases_get_useful_guide(self):
        for q in ('Minha maquininha não conecta','Minha máquina está desconectada','Meu terminal está offline'):
            with self.subTest(q=q):
                r=self.post(q);self.assertEqual(r['route'],'support_knowledge')
                self.assertEqual(r['status'],'evidencias');self.assertIn('Procurar Redes',r['answer'])

    def test_generic_account_explanation_does_not_query_fixture(self):
        r=self.post('O que é saldo de conta?')
        self.assertFalse(any(e['ferramenta'] for e in r['eventos']))

    def test_balance_procedure_preserves_knowledge_route(self):
        for q in ('Como consultar meu saldo?', 'How can I check my balance?'):
            self.assertEqual(self.post(q)['route'],'support_knowledge')


class DNSRegressions(unittest.TestCase):
    def client(self,rows):
        self.transport=Mock(return_value=rows)
        return TestClient(create_app(mode='rag',enable_web=True,web_search=GeneralWebSearch(self.transport)))

    def test_general_explanation_routes_and_returns_relevant_dns(self):
        client=self.client([DNS_ROW])
        for q in ('O que é o sistema DNS?','Explique o que é DNS','Explain DNS','What is DNS?'):
            r=client.post('/chat',json={'message':q,'user_id':'cliente1988'}).json()
            self.assertEqual(r['route'],'clarify');self.assertEqual(r['status'],'limitado')
            self.assertEqual(r['sources'],[]);self.assertIn('dedicado',r['answer'])
            self.transport.assert_not_called()

    def test_recorded_irrelevant_results_and_homonym_abstain(self):
        client=self.client(BAD_ROWS)
        r=client.post('/chat',json={'message':'O que é o sistema DNS?','user_id':'cliente1988'}).json()
        self.assertEqual(r['status'],'limitado');self.assertEqual(r['sources'],[])
        self.assertNotIn('prefeitura',r['answer'])

    def test_mixed_results_only_keep_relevant_sources(self):
        result=GeneralWebSearch(Mock(return_value=BAD_ROWS+[DNS_ROW])).search('O que é o sistema DNS?')
        self.assertEqual(result['results'],[DNS_ROW])

    def test_relevance_is_not_limited_to_dns(self):
        result=GeneralWebSearch(Mock(return_value=BAD_ROWS)).search('What is the Python programming language?')
        self.assertEqual(result['status'],'insufficient_evidence')

    def test_filter_before_output_limit(self):
        result=GeneralWebSearch(Mock(return_value=BAD_ROWS+[DNS_ROW]*8)).search('Explique DNS')
        self.assertEqual(result['results'],[DNS_ROW]*3)

    def test_candidate_read_is_bounded_and_keeps_later_relevant_hit(self):
        from xml.sax.saxutils import escape
        rows=BAD_ROWS+[DNS_ROW]*9
        raw=('<rss><channel>'+''.join('<item><title>'+escape(r['title'])+'</title><description>'+escape(r['snippet'])+'</description><link>'+escape(r['url'])+'</link></item>' for r in rows)+'</channel></rss>').encode()
        parsed=parse_results(raw)
        self.assertEqual(len(parsed),10)
        self.assertEqual(GeneralWebSearch(Mock(return_value=parsed)).search('DNS')['results'],[DNS_ROW]*3)

    def test_dns_market_does_not_change_other_queries(self):
        from unittest.mock import patch
        from urllib.parse import parse_qs, urlsplit
        for query,market in (('"DNS" "Domain Name System"',['en-US']),('linguagem Python',None)):
            with patch('app.rag.general_web.PinnedHTTPS') as connection,patch('app.rag.general_web.resolve_public',return_value='93.184.215.14'):
                response=connection.return_value.getresponse.return_value
                response.status=200;response.getheader.return_value='identity'
                response.read.return_value=b'<rss><channel/></rss>'
                request(query)
                args=connection.return_value.request.call_args.args
                params=parse_qs(urlsplit(args[1]).query)
                self.assertEqual(params.get('mkt'),market);self.assertEqual(params['q'],[query])
                connection.return_value.close.assert_called_once()

    def test_private_input_checked_before_dns_expansion(self):
        transport=Mock()
        for q in ('Explique DNS cpf 123.456.789-00','DNS password secret','DNS https://example.org','DNS a@b.com'):
            with self.subTest(q=q),self.assertRaises(ValueError):GeneralWebSearch(transport).search(q)
        transport.assert_not_called()

    def test_natural_private_or_local_queries_never_leave(self):
        client=self.client([DNS_ROW])
        for q in ('Explique meu saldo','Explique DNS da minha conta','Explique Pix','Explain my password','Explique DNS cpf 123.456.789-00'):
            client.post('/chat',json={'message':q,'user_id':'cliente1988'})
        self.transport.assert_not_called()

    def test_context_not_forwarded_with_explain_prefix(self):
        local,web=Mock(),Mock()
        KnowledgeDispatch(local,web).responder(Entrada(message='Explique DNS',user_id='cliente1988'),(RespostaEspecialista(texto='private fixture'),))
        web.responder.assert_not_called()

    def test_outage_is_not_empty_success(self):
        result=GeneralWebSearch(Mock(side_effect=TimeoutError('PRIVATE_DETAIL'))).search('DNS')
        self.assertEqual(result['status'],'unavailable');self.assertNotIn('PRIVATE_DETAIL',str(result))


if __name__=='__main__':unittest.main()
