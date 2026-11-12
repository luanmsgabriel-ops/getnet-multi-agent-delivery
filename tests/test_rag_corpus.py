"""Separacao de mercado, deduplicacao e extratores fail-closed."""
import unittest
from copy import deepcopy
from app.rag.core import Index,extract,snapshot
from test_rag_local import doc
class CorpusExpansionTest(unittest.TestCase):
    def global_doc(self):
        d=doc();d.update(requested_url='https://www.getnet.net/',final_url='https://www.getnet.net/en/',market='GLOBAL',title='Global payments',chunks=['Global payments secure technology.']);return d
    def test_global_not_used_for_brazil(self):
        index=Index([self.global_doc()]);self.assertEqual(index.search('global payments')['status'],'insufficient_evidence')
    def test_global_explicit(self):self.assertEqual(Index([self.global_doc()]).search('global payments',market='GLOBAL')['status'],'candidates')
    def test_redirect_duplicate_indexed_once(self):
        a=self.global_doc();b=deepcopy(a);b['requested_url']='https://www.getnet.net/en'
        self.assertEqual(len(Index([a,b]).entries),1)
    def test_false_market_refused(self):
        d=self.global_doc();d['market']='BR'
        with self.assertRaises(ValueError):Index([d])
    def test_adq_requires_exact_code(self):
        d=doc();d['title']='Erro ADQ 1-19';d['chunks']=['Erro de conexao na transacao.']
        index=Index([d]);self.assertEqual(index.search('erro conexao')['status'],'insufficient_evidence')
        self.assertEqual(index.search('ADQ 1-19')['status'],'candidates')
    def test_global_boundaries(self):
        title,chunks=extract(b'<h1>Global</h1><p>Secure payments.</p><h2>BUILT FOR EVERY BUSINESS</h2><p>not included</p>',marker='BUILT FOR EVERY BUSINESS')
        self.assertEqual(chunks,['Secure payments.'])
    def test_sentence_boundaries(self):
        sentence=('word '*170).strip()+'.'
        raw=('<h1>Teste</h1><p>'+sentence+' '+sentence+'</p><p>Respondeu a sua duvida?</p>').encode()
        _,chunks=extract(raw);self.assertEqual(chunks,[sentence,sentence])
if __name__=='__main__':unittest.main()
