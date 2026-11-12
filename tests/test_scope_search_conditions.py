"""Regressões de condições, busca permitida e escopo Brasil-only; sem rede/modelo pago."""
import unittest
from pathlib import Path
from unittest.mock import Mock
from fastapi.testclient import TestClient
from app.main import create_app
from app.knowledge import KnowledgeRag, KnowledgeGenerated
from app.contracts import Entrada
from app.rag.generation import validated_draft, UnsupportedDraft
from app.rag.general_web import GeneralWebSearch, subject_terms, search_query

ROOT=Path(__file__).resolve().parents[1]

class Conditions(unittest.TestCase):
    def validate(self,text,quote):
        g=Mock();g.generate.return_value={'answer':quote,'citations':[{'evidence_id':0,'quote':quote}]}
        return validated_draft(g,'O serviço está incluído?',[
            {'text':text,'source':'https://site.getnet.com.br/duvidas/','captured_at':'2026-11-09T00:00:00+00:00'}])

    def test_conditions_before_and_after_cannot_be_removed(self):
        quote='O serviço está incluído sem custo adicional.'
        conditions=['Caso o cliente tenha contratado o pacote X, aplicam-se as condições abaixo.',
                    'Se contratar o pacote X, esta oferta fica disponível.',
                    'Oferta válida desde que haja contratação do pacote X.',
                    'Oferta sujeita à contratação do pacote X.',
                    'A oferta não se aplica a outro pacote.',
                    'Somente clientes elegíveis podem aderir.',
                    'O benefício depende da contratação.',
                    'A oferta tem valor mínimo contratado.',
                    'Válido salvo cancelamento do pacote.']
        for condition in conditions:
            for text in (condition+' '+quote,quote+' '+condition):
                with self.subTest(text=text),self.assertRaises(UnsupportedDraft):self.validate(text,quote)

    def test_complete_conditional_block_is_preserved(self):
        text='Caso contrate o pacote X, a oferta fica disponível. O serviço está incluído.'
        self.assertEqual(self.validate(text,text)[0],text)

    def test_english_scope_is_preserved(self):
        quote='The service is included.'
        for clause in ('If the package is active.','When the package is active.',
                       'Unless the package is canceled.','Provided that the package is active.',
                       'The offer is not available for other packages.'):
            with self.subTest(clause=clause),self.assertRaises(UnsupportedDraft):self.validate(clause+' '+quote,quote)

    def test_neutral_complete_block_is_still_usable(self):
        text='A tela é touchscreen. O manual descreve os botões.'
        self.assertEqual(self.validate(text,text)[0],text)
        # Novo contrato: o validador não presume independência entre frases.
        with self.assertRaises(UnsupportedDraft):self.validate(text,'A tela é touchscreen.')

    def test_model_invalid_scope_falls_back_to_full_source(self):
        text='Caso contrate o pacote X, a oferta fica disponível. O serviço está incluído.'
        row={'text':text,'source':'https://site.getnet.com.br/duvidas/','captured_at':'2026-11-09T00:00:00+00:00','title':'Oferta'}
        index=Mock();index.search.return_value={'status':'candidates','candidates':[row]}
        g=Mock();g.generate.return_value={'answer':'O serviço está incluído.','citations':[{'evidence_id':0,'quote':'O serviço está incluído.'}]}
        response=KnowledgeGenerated(index,g).responder(Entrada(message='Como funciona o serviço?',user_id='cliente1988'),())
        self.assertEqual(response.status,'evidencias');self.assertEqual(response.modo,'extrativo')
        self.assertIn(text,response.texto)

class GeneralSearch(unittest.TestCase):
    def test_person_names_without_interrogatives(self):
        row={'title':'Ada Lovelace','snippet':'Ada Lovelace wrote an algorithm for the Analytical Engine.','url':'https://example.org/ada'}
        transport=Mock(return_value=[row])
        client=TestClient(create_app(mode='rag',enable_web=True,web_search=GeneralWebSearch(transport)))
        for q in ('Who was Ada Lovelace?','Quem foi Ada Lovelace?','Explique quem foi Ada Lovelace'):
            r=client.post('/chat',json={'message':q,'user_id':'cliente1988'}).json()
            self.assertEqual(r['status'],'limitado');self.assertEqual(r['sources'],[])
            transport.assert_not_called()

    def test_brazil_product_categories_remain_searchable(self):
        for word,expected in [('programação','programacao'),('sistema','sistema'),('linguagem','linguagem'),('documentação','documentacao')]:
            self.assertEqual(subject_terms('Explique '+word),{expected})
        for word in ('Pix','crediário','pagamentos','recebíveis'):
            row={'title':word+' Getnet Brasil','snippet':word+' Getnet Brasil é o assunto deste resultado sintético.','url':'https://site.getnet.com.br/conceito'}
            transport=Mock(return_value=[row])
            r=GeneralWebSearch(transport,official_only=True).search('Explique '+word+' Getnet Brasil')
            self.assertEqual(r['status'],'results');self.assertEqual(r['results'],[row])
            transport.assert_called_once()

    def test_concept_parser_and_brazil_system_search(self):
        self.assertEqual(subject_terms('O que é uma linguagem de programação?'),{'linguagem','programacao'})
        row={'title':'Sistema Pix Getnet Brasil','snippet':'O sistema Pix Getnet Brasil permite pagamentos.','url':'https://site.getnet.com.br/sistema-pix'}
        transport=Mock(return_value=[row])
        self.assertEqual(GeneralWebSearch(transport,official_only=True).search('Explique o sistema Pix Getnet Brasil')['results'],[row])
        transport.assert_called_once()

    def test_named_category_does_not_require_exact_query_language(self):
        self.assertEqual(subject_terms('What is the Python programming language?'),{'python'})
        self.assertEqual(subject_terms('O que é o sistema DNS?'),{'dns'})

    def test_question_words_can_be_part_of_a_name(self):
        self.assertEqual(subject_terms('Who was The Who?'),{'who'})

    def test_irrelevant_results_for_brazil_products_still_rejected(self):
        row={'title':'Prefeitura','snippet':'Sistemas municipais.','url':'https://site.getnet.com.br/municipal'}
        for q in ('Como funciona o Pix Getnet Brasil?','Explique antecipação de recebíveis Getnet Brasil'):
            transport=Mock(return_value=[row])
            self.assertEqual(GeneralWebSearch(transport,official_only=True).search(q)['status'],'insufficient_evidence')
            transport.assert_called_once()

    def test_brazil_receivables_query_rejects_payment_homonym(self):
        unrelated={'title':'Pagamentos Getnet Brasil','snippet':'Getnet Brasil descreve pagamentos com cartão.','url':'https://site.getnet.com.br/pagamentos'}
        definition={'title':'Antecipação de recebíveis Getnet Brasil','snippet':'Antecipação de recebíveis Getnet Brasil permite antecipar o recebimento de vendas.','url':'https://site.getnet.com.br/antecipacao'}
        transport=Mock(return_value=[unrelated,definition])
        rows=GeneralWebSearch(transport,official_only=True).search('Explique antecipação de recebíveis Getnet Brasil')['results']
        self.assertEqual(rows,[definition]);transport.assert_called_once()

    def test_privacy_precedes_brazil_question_reformulation(self):
        transport=Mock()
        for q in ('Explique Pix Getnet Brasil cpf 123.456.789-00','Explique recebíveis Getnet Brasil a@b.com','Explique Wi-Fi Getnet Brasil password secret'):
            with self.assertRaises(ValueError):GeneralWebSearch(transport,official_only=True).search(q)
        transport.assert_not_called()

class BrazilOnlyKnowledge(unittest.TestCase):
    def setUp(self):
        self.local=KnowledgeRag.from_directory(ROOT/'corpus_publico')
        self.search=Mock()
        self.client=TestClient(create_app(mode='rag',enable_web=True,web_search=self.search))

    def post(self,q):return self.client.post('/chat',json={'message':q,'user_id':'cliente1988'}).json()

    def test_global_company_questions_redirect_to_brazil_without_tools(self):
        for q in ("Where does Getnet operate?",'Onde a Getnet atua?',
                  'Em quais países a Getnet opera?', "What is Getnet's presence in Latin America and Europe?",
                  'Qual a presença global da Getnet?','O que é a Getnet?'):
            with self.subTest(q=q):
                r=self.post(q);self.assertEqual(r['status'],'limitado')
                self.assertEqual(r['sources'],[]);self.assertIn('Getnet Brasil',r['answer'])
                self.assertFalse(any(e['ferramenta'] for e in r['eventos']))
        self.search.search.assert_not_called()

    def test_global_request_is_blocked_before_retrieval_and_generation(self):
        index=Mock();g=Mock()
        r=KnowledgeGenerated(index,g).responder(Entrada(message='Where does Getnet operate?',user_id='cliente1988'),())
        self.assertEqual(r.status,'limitado');self.assertEqual(r.fontes,[])
        self.assertIn('Getnet Brasil',r.texto)
        index.search.assert_not_called();g.generate.assert_not_called()

    def test_foreign_or_unknown_region_does_not_confirm_company_overlap(self):
        for q in ('A Getnet atua no Japão?','Does Getnet operate in Antarctica?'):
            r=self.post(q);self.assertEqual(r['status'],'limitado');self.assertEqual(r['sources'],[])
            self.assertIn('Getnet Brasil',r['answer'])
            self.assertFalse(any(e['ferramenta'] for e in r['eventos']))
        self.search.search.assert_not_called()

    def test_foreign_commercial_queries_redirect_without_brazilian_offer(self):
        for q in ('Quais taxas da Getnet na Europa?','Getnet Pix em Portugal',
                  'What are Getnet fees worldwide?','Em quais países a Getnet oferece crediário?'):
            r=self.post(q);self.assertEqual(r['status'],'limitado');self.assertEqual(r['sources'],[])
            self.assertIn('Getnet Brasil',r['answer'])
            self.assertFalse(any(e['ferramenta'] for e in r['eventos']))
        self.search.search.assert_not_called()

    def test_brazil_products_still_use_brazil_sources(self):
        for q in ('Como habilitar Pix pelo portal?','Qual o limite de parcelas no crediário?',
                  'Qual a diferença entre Get Clássica e Get Smart?'):
            r=self.post(q);self.assertEqual(r['status'],'evidencias')
            self.assertTrue(r['sources'])
            self.assertTrue(all('site.getnet.com.br' in url for url in r['sources']))
        self.search.search.assert_not_called()

    def test_global_request_does_not_query_brazil_index(self):
        index=Mock()
        r=KnowledgeRag(index).responder(Entrada(message='Where does Getnet operate?',user_id='cliente1988'),())
        self.assertEqual(r.status,'limitado');self.assertEqual(r.fontes,[])
        self.assertIn('Getnet Brasil',r.texto);index.search.assert_not_called()

    def test_global_query_does_not_call_web_or_support(self):
        search=Mock()
        client=TestClient(create_app(mode='rag',enable_web=True,web_search=search))
        r=client.post('/chat',json={'message':'Onde a Getnet atua?','user_id':'cliente1988'}).json()
        self.assertEqual(r['status'],'limitado');self.assertEqual(r['sources'],[])
        search.search.assert_not_called()
        self.assertFalse(any(e['ferramenta'] for e in r['eventos']))

if __name__=='__main__':unittest.main()
