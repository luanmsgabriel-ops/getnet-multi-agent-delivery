"""Página oficial real; mutações estruturais negativas não são testes LLM reais."""
import unittest
from pathlib import Path
from datetime import datetime,timezone
from hashlib import sha256
from app.rag.pix_faq import extract_pix_faq
from app.rag.core import snapshot,Index,extract,save_snapshot,load_snapshot

RAW=(Path(__file__).parent / 'fixtures' / 'getnet_duvidas_real.html').read_bytes()
TEXT=RAW.decode()
class PixCapture(unittest.TestCase):
    def test_real_page(self):
        title,chunks=extract_pix_faq(RAW)
        self.assertEqual(len(chunks),8)
        self.assertTrue(all(len(x)<=1200 for x in chunks))
        self.assertIn('corrente, poupança ou conta de pagamento pré-paga',chunks[0])
        contract=next(x for x in chunks if 'Como faço para contratar' in x)
        self.assertIn('mesma chave',contract);self.assertIn('PSP já integrados',contract)
        self.assertIn('Central de Atendimento',contract)
        self.assertIn('somente uma chave',chunks[5])
        self.assertNotIn('Plano Light',' '.join(chunks))
        self.assertNotIn('Chargeback',' '.join(chunks))
        self.assertNotIn('Receba suas vendas em segundos',' '.join(chunks))
    def test_reproduces_old_failure(self):
        with self.assertRaisesRegex(ValueError,'Limite editorial'):
            extract(RAW)
    def test_snapshot_gate(self):
        doc=snapshot(dict(requested_url='https://site.getnet.com.br/duvidas/',final_url='https://site.getnet.com.br/duvidas/',captured_at=datetime.now(timezone.utc).isoformat(),raw_sha256=sha256(RAW).hexdigest(),body=RAW))
        self.assertIs(doc['reviewed'],False)
        self.assertEqual(doc['raw_sha256'],sha256(RAW).hexdigest())
        self.assertEqual(doc['market'],'BR')
        with self.assertRaisesRegex(ValueError,'revisao explicita'): Index([doc])
    def test_absent_section(self):
        with self.assertRaises(ValueError): extract_pix_faq(TEXT.replace('Mais respostas sobre o Pix','Outro título').encode())
    def test_duplicate_section(self):
        heading=TEXT.index('Mais respostas sobre o Pix')
        start=TEXT.rfind('<div class="c-all-faq__content">',0,heading)
        end=TEXT.index('</div>',TEXT.index('c-all-faq__see-more',heading))+6
        raw=(TEXT+TEXT[start:end]).encode()
        self.assertLess(len(raw),1_000_000)
        with self.assertRaisesRegex(ValueError,'ambígua'): extract_pix_faq(raw)
    def test_missing_answer_class(self):
        marker='data-modal="38138">\n'
        i=TEXT.index(marker);j=TEXT.index('o-modal__text-content',i)
        with self.assertRaises(ValueError): extract_pix_faq((TEXT[:j]+TEXT[j:].replace('o-modal__text-content','removed',1)).encode())
    def test_missing_pair(self):
        with self.assertRaises(ValueError): extract_pix_faq(TEXT.replace('data-modal="38138"','data-modal="new"',1).encode())
    def test_duplicate_id(self):
        with self.assertRaises(ValueError): extract_pix_faq(TEXT.replace('data-modal="38142"','data-modal="38138"').encode())
    def test_truncated(self):
        with self.assertRaises(ValueError): extract_pix_faq(TEXT[:TEXT.index('Como funciona o Pix na Getnet?')].encode())
    def test_divergent_title(self):
        with self.assertRaises(ValueError): extract_pix_faq(TEXT.replace('O que é o Pix? E quais as vantagens?','Pergunta alterada?',1).encode())
    def test_oversize_answer(self):
        with self.assertRaises(ValueError): extract_pix_faq(TEXT.replace('O Pix é um meio','Longo '*250+'O Pix é um meio',1).encode())
    def test_menu_exclusion(self):
        raw=TEXT.replace('O Pix é um meio','<nav>MENU TESTE</nav>O Pix é um meio',1).encode()
        self.assertNotIn('MENU TESTE',' '.join(extract_pix_faq(raw)[1]))
    def test_changed_condition_still_requires_review(self):
        # Mudança editorial não é automaticamente aprovada, mesmo com HTML válido.
        raw=TEXT.replace('PSP já integrados','PSP').encode()
        doc=snapshot(dict(requested_url='https://site.getnet.com.br/duvidas/',final_url='https://site.getnet.com.br/duvidas/',captured_at=datetime.now(timezone.utc).isoformat(),raw_sha256=sha256(raw).hexdigest(),body=raw))
        self.assertIs(doc['reviewed'],False)
        with self.assertRaises(ValueError): Index([doc])
if __name__=='__main__': unittest.main(verbosity=2)
