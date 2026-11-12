"""Propriedades metamorfica/sinteticas; nao benchmark semantico de LLM."""
import random
import unittest
from copy import deepcopy
from app.rag.core import Index
from app.router import RouterDemo
from app.contracts import Entrada
from test_rag_local import doc

class IndependentEvaluation(unittest.TestCase):
    def test_generated_corpus_retrieval_and_permutation(self):
        rng=random.Random(7241)
        docs=[]
        for i in range(40):
            d=doc();d.update(requested_url=f'https://site.getnet.com.br/fixture-{i}',final_url=f'https://site.getnet.com.br/fixture-{i}',title=f'Produto codigo{i}',chunks=[f'codigo{i} recurso{i} orientacao sintetica exclusiva.'])
            docs.append(d)
        shuffled=deepcopy(docs);rng.shuffle(shuffled)
        for index in (Index(docs),Index(shuffled)):
            for i in rng.sample(range(40),20):
                with self.subTest(i=i):
                    r=index.search(f'codigo{i} recurso{i}')
                    self.assertEqual(r['candidates'][0]['source'],f'https://site.getnet.com.br/fixture-{i}')
                    self.assertEqual(len(r['candidates']),1)
    def test_query_case_accents_punctuation_metamorphic(self):
        d=doc();d.update(title='Credito antecipacao',chunks=['Credito antecipacao taxas contratuais.'])
        index=Index([d]);expected=index.search('credito antecipacao')
        for q in ['CREDITO ANTECIPACAO','Crédito antecipação','credito, antecipacao!','  credito   antecipacao  ']:
            self.assertEqual(index.search(q),expected)
    def test_unknown_terms_do_not_hallucinate(self):
        index=Index([doc()])
        for i in range(30):self.assertEqual(index.search(f'unknownfixture{i}')['status'],'insufficient_evidence')
    def test_unreviewed_documents_rejected(self):
        d=doc();d['reviewed']=False
        with self.assertRaises(ValueError):Index([d])
    def test_router_paraphrase_variants(self):
        router=RouterDemo()
        groups={'support':['my balance please','Check my terminal','meu saldo por favor','consultar vendas de ontem'], 'knowledge':['How do payment fees work?','Compare the difference between products','como funcionam as taxas?'], 'support_knowledge':['What should I do with my card machine?','Como consultar meu saldo?']}
        for expected,messages in groups.items():
            for message in messages:
                for variant in [message,message.upper(),'  '+message+'  ']:
                    self.assertEqual(router.planejar(Entrada(message=variant,user_id='demo_A')).rota,expected)
    def test_web_prefix_invariant(self):
        for prefix in ['pesquise na web:','PESQUISE NA WEB:','  Pesquise na web:']:
            self.assertEqual(RouterDemo().planejar(Entrada(message=prefix+' adquirencia',user_id='demo_A')).rota,'knowledge')
