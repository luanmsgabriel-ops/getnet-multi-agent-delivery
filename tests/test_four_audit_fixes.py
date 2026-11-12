"""Regressões de escopo, citações e busca; rede e modelo substituídos."""
import unittest
from pathlib import Path
from unittest.mock import Mock
from fastapi.testclient import TestClient
from app.main import create_app
from app.knowledge import KnowledgeGenerated, KnowledgeRag
from app.contracts import Entrada
from app.rag.generation import validated_draft, UnsupportedDraft
from app.rag.general_web import GeneralWebSearch
from app.rag.scope import retrieval_plan

ROOT=Path(__file__).resolve().parents[1]

class CitationContext(unittest.TestCase):
    def validate(self,text,quote):
        g=Mock();g.generate.return_value={'answer':quote,'citations':[{'evidence_id':0,'quote':quote}]}
        return validated_draft(g,'Como funciona o serviço?',[
            {'text':text,'source':'https://site.getnet.com.br/duvidas/','captured_at':'2026-11-09T00:00:00+00:00'}])

    def test_scope_without_conditional_keywords_before_or_after(self):
        for scope,quote in [
            ('Clientes do plano X têm acesso aos benefícios abaixo.','O serviço está incluído sem custo adicional.'),
            ('Esta oferta contempla estabelecimentos credenciados na campanha.','O benefício é gratuito.'),
            ('Customers on plan X receive the following benefits.','The service is included at no extra cost.')]:
            for text in (scope+' '+quote,quote+' '+scope):
                with self.subTest(text=text),self.assertRaises(UnsupportedDraft):self.validate(text,quote)

    def test_full_scope_and_neutral_single_sentence_work(self):
        for text in ('Clientes do plano X têm acesso ao benefício. O serviço está incluído.',
                     'O equipamento possui tela sensível ao toque.'):
            self.assertEqual(self.validate(text,text)[0],text)

    def test_partial_scope_uses_full_document_fallback(self):
        text='Clientes do plano X têm acesso aos benefícios abaixo. O serviço está incluído sem custo adicional.'
        quote='O serviço está incluído sem custo adicional.'
        row={'text':text,'title':'Serviço','source':'https://site.getnet.com.br/duvidas/','captured_at':'2026-11-09T00:00:00+00:00'}
        index=Mock();index.search.return_value={'status':'candidates','candidates':[row]}
        generator=Mock();generator.generate.return_value={'answer':quote,'citations':[{'evidence_id':0,'quote':quote}]}
        r=KnowledgeGenerated(index,generator).responder(Entrada(message='Como funciona o serviço?',user_id='cliente1988'),())
        self.assertEqual((r.status,r.modo),('evidencias','extrativo'));self.assertIn(text,r.texto)

    def test_separate_citations_cannot_strip_context(self):
        text='Clientes do plano X têm acesso ao benefício. O serviço está incluído.'
        quotes=['O serviço está incluído.']
        g=Mock();g.generate.return_value={'answer':'\n\n'.join(quotes),'citations':[{'evidence_id':0,'quote':q} for q in quotes]}
        with self.assertRaises(UnsupportedDraft):validated_draft(g,'Serviço',[
            {'text':text,'source':'https://site.getnet.com.br/duvidas/','captured_at':'2026-11-09T00:00:00+00:00'}])

    def test_sensitive_fragment_is_never_accepted_as_answer(self):
        from app.rag.generation import SensitiveEvidence
        text='Abra o aplicativo. Digite a senha no dispositivo. Confirme a operação.'
        with self.assertRaises(SensitiveEvidence):self.validate(text,'Digite a senha no dispositivo.')
        with self.assertRaises(ValueError):self.validate(text,'Envie a senha nesta conversa.')

class CommercialMarket(unittest.TestCase):
    def setUp(self):
        self.generator=Mock();self.web=Mock()
        self.client=TestClient(create_app(mode='generated',generator=self.generator,enable_web=True,web_search=self.web))

    def test_canada_commercial_api_abstains_before_model_and_search(self):
        for q in ('Como funciona o crediário Getnet no Canadá?',
                  'What are Getnet fees in Canada?', 'Taxas Getnet canadenses',
                  'Como funciona o crediário Getnet no Canada e no Brasil?'):
            r=self.client.post('/chat',json={'message':q,'user_id':'cliente1988'}).json()
            self.assertEqual(r['status'],'limitado');self.assertFalse(r['sources'])
        self.generator.generate.assert_not_called();self.web.search.assert_not_called()

    def test_unlisted_locations_do_not_default_to_brazil(self):
        for q in ('Como funciona o crediário Getnet na França?',
                  'Getnet fees in New Zealand', 'Getnet Pix em Atlantis',
                  'Taxas Getnet no mercado canadense'):
            self.assertIsNone(retrieval_plan(q)[0],q)

    def test_known_operational_locations_are_not_foreign_markets(self):
        for q in ('Como habilitar Pix no app?', 'Como habilitar Pix pelo portal?',
                  'Crediário no Brasil', 'Getnet fees in Brazil',
                  'Como habilitar crediário na maquininha?', 'Qual o limite de parcelas no crediário?'):
            self.assertEqual(retrieval_plan(q)[0],'BR',q)

    def test_brazil_api_and_global_preserved(self):
        c=TestClient(create_app(mode='rag',enable_web=False))
        for q,domain in [('Como habilitar Pix pelo portal?','site.getnet.com.br'),
                         ('Qual o limite de parcelas no crediário?','site.getnet.com.br'),
                         ('Getnet Brasil crediário','site.getnet.com.br')]:
            r=c.post('/chat',json={'message':q,'user_id':'cliente1988'}).json()
            self.assertEqual(r['status'],'evidencias');self.assertTrue(all(domain in s for s in r['sources']))

    def test_unknown_global_presence_still_abstains(self):
        rag=KnowledgeRag.from_directory(ROOT/'corpus_publico')
        self.assertEqual(rag._retrieve('Does Getnet operate in Canada?')['status'],'insufficient_evidence')

class SearchContext(unittest.TestCase):
    SNAKE={'title':'Python','snippet':'The python is a large nonvenomous snake.','url':'https://example.org/snake'}
    LANGUAGE={'title':'Python','snippet':'Python is a programming language with readable code.','url':'https://example.org/python'}

    def search(self,q,rows):return GeneralWebSearch(Mock(return_value=rows)).search(q)

    def test_python_named_context_rejects_snake_pt_en(self):
        for q in ('What is the Python programming language?','O que é a linguagem de programação Python?',
                  'pesquisa sobre linguagem Python'):
            self.assertEqual(self.search(q,[self.SNAKE])['status'],'insufficient_evidence')

    def test_mixed_hits_keep_language_only(self):
        for q in ('What is the Python programming language?','O que é a linguagem Python?'):
            self.assertEqual(self.search(q,[self.SNAKE,self.LANGUAGE])['results'],[self.LANGUAGE])

    def test_context_synonyms_allow_compiler(self):
        row={'title':'Python compiler','snippet':'Run Python code online.','url':'https://example.org/compiler'}
        self.assertEqual(self.search('O que é a linguagem de programação Python?',[row])['results'],[row])

    def test_other_language_homonym_uses_same_rule(self):
        island={'title':'Java','snippet':'Java is an island in Indonesia.','url':'https://example.org/island'}
        language={'title':'Java','snippet':'Java is a programming language.','url':'https://example.org/java'}
        self.assertEqual(self.search('What is the Java programming language?',[island,language])['results'],[language])

    def test_unqualified_entity_does_not_force_programming(self):
        self.assertEqual(self.search('Python',[self.SNAKE])['results'],[self.SNAKE])

    def test_python_api_snake_only_abstains(self):
        c=TestClient(create_app(mode='rag',enable_web=True,web_search=GeneralWebSearch(Mock(return_value=[self.SNAKE]))))
        r=c.post('/chat',json={'message':'What is the Python programming language?','user_id':'cliente1988'}).json()
        self.assertEqual(r['status'],'limitado');self.assertFalse(r['sources']);self.assertNotIn('snake',r['answer'])

class PublicPlural(unittest.TestCase):
    def test_plural_singular_and_polite_prefix_use_same_search(self):
        row={'title':'Algoritmos e algoritmo','snippet':'Algoritmos são sequências finitas de instruções.','url':'https://example.org/algoritmos'}
        transport=Mock(return_value=[row])
        c=TestClient(create_app(mode='rag',enable_web=True,web_search=GeneralWebSearch(transport)))
        for q in ('O que são algoritmos?','O que é algoritmo?','Por favor o que são algoritmos?'):
            before=transport.call_count
            r=c.post('/chat',json={'message':q,'user_id':'cliente1988'}).json()
            self.assertEqual(r['status'],'limitado');self.assertEqual(transport.call_count,0)
            self.assertEqual(r['sources'],[])

    def test_plural_private_queries_never_leave(self):
        transport=Mock()
        c=TestClient(create_app(mode='rag',enable_web=True,web_search=GeneralWebSearch(transport)))
        for q in ('O que são meus recebíveis?','O que são minhas contas?',
                  'O que são tokens da minha conta?', 'O que são algoritmos cpf 123.456.789-00'):
            c.post('/chat',json={'message':q,'user_id':'cliente1988'})
        transport.assert_not_called()

    def test_plural_disabled_web_explicit(self):
        c=TestClient(create_app(mode='rag',enable_web=False))
        r=c.post('/chat',json={'message':'O que são algoritmos?','user_id':'cliente1988'}).json()
        self.assertEqual(r['route'],'clarify');self.assertEqual(r['status'],'limitado');self.assertIn('dedicado',r['answer'])

if __name__=='__main__':unittest.main()
