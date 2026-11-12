"""Regressões audit-71. Fixtures sintéticas, sem rede ou modelo; fontes reais locais revisadas."""
import hashlib,importlib.util,json,sys,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
if importlib.util.find_spec('app') is None:
    fallback=Path(__file__).resolve().parent/'source'
    sys.path.insert(0,str(fallback if (fallback/'app').is_dir() else Path(__file__).resolve().parents[1]))
import app
from app.context_service import ApprovedIndex,ContextService,fingerprint
from app.context_store import Store
from app.contracts import Entrada
from app.knowledge import KnowledgeRag
from app.rag.core import Index,snapshot,query_tokens
from app.rag.quality import attribute_candidates,predicate_supported,relevant_candidates
from app.rag.scope import retrieval_plan,unsupported_location

SOURCE=Path(app.__file__).resolve().parent.parent
URL='https://site.getnet.com.br/get-ajuda-whatsapp-business/descontinuacao-whatsapp-business/'
GLOBAL='https://www.getnet.net/en/'

def document(text,title='Getnet: comunicado',market='BR'):
    url=GLOBAL if market=='GLOBAL' else URL
    return dict(version=1,requested_url=url,final_url=url,captured_at='2026-11-07T00:00:00+00:00',raw_sha256='a'*64,title=title,chunks=[text],market=market,reviewed=True)

def row(text,title='Getnet: comunicado',market='BR'):
    return dict(text=text,title=title,source=GLOBAL if market=='GLOBAL' else URL,market=market,captured_at='2026-11-07T00:00:00+00:00')

class AuditRelevance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.local=KnowledgeRag.from_directory(SOURCE/'corpus_publico')
    def answer(self,question):
        return self.local.responder(Entrada(message=question,user_id='cliente1988'),())
    def test_sustainability_does_not_use_whatsapp(self):
        result=self.answer('novidade Getnet sustentabilidade 2026')
        self.assertEqual(result.status,'sem_evidencia');self.assertFalse(result.fontes)
        self.assertNotIn('WhatsApp',result.texto)
    def test_other_unknown_subject_not_replaced_by_date(self):
        index=Index([document('Getnet anunciou pagamentos pelo WhatsApp em 2026.')])
        self.assertEqual(index.search('novidade Getnet arqueologia 2026')['status'],'insufficient_evidence')
    def test_news_subject_supported_in_body(self):
        index=Index([document('A Getnet publicou ações de sustentabilidade em 2026.')])
        self.assertEqual(index.search('novidade Getnet sustentabilidade 2026')['status'],'candidates')
    def test_news_title_without_subject_in_body_rejected(self):
        index=Index([document('A Getnet anunciou WhatsApp em 2026.','Getnet sustentabilidade 2026')])
        self.assertEqual(index.search('novidade Getnet sustentabilidade 2026')['status'],'insufficient_evidence')
    def test_capture_date_is_not_event_date(self):
        index=Index([document('A Getnet publica ações de sustentabilidade.')])
        self.assertEqual(index.search('novidade Getnet sustentabilidade 2026')['status'],'insufficient_evidence')
    def test_different_event_year_is_not_supported(self):
        index=Index([document('A Getnet publicou ações de sustentabilidade em 2025.')])
        self.assertEqual(index.search('novidade Getnet sustentabilidade 2026')['status'],'insufficient_evidence')
    def test_country_list_in_official_reviewed_block(self):
        result=self.answer('Em quais países a Getnet atua?')
        self.assertEqual(result.status,'limitado');self.assertFalse(result.fontes)
        self.assertIn('Getnet Brasil',result.texto)
    def test_country_question_does_not_accept_regional_slogan(self):
        index=Index([document('Global secure payments.','Getnet in Latin America and Europe','GLOBAL')])
        self.assertEqual(index.search('getnet presence',market='GLOBAL')['status'],'insufficient_evidence')
    def test_region_question_still_has_evidence(self):
        result=self.answer('A Getnet atua na Europa?')
        self.assertEqual(result.status,'limitado');self.assertFalse(result.fontes)
        self.assertIn('Getnet Brasil',result.texto)
    def test_known_global_country_can_be_answered(self):
        result=self.answer('A Getnet atua no México?')
        self.assertEqual(result.status,'limitado');self.assertFalse(result.fontes)
        self.assertIn('Getnet Brasil',result.texto)
    def test_unknown_country_not_inferred(self):
        result=self.answer('A Getnet atua no Japão?')
        self.assertEqual(result.status,'limitado');self.assertFalse(result.fontes)
    def test_presence_does_not_authorize_national_product(self):
        for q in ('Getnet Pix em Portugal','Taxa do Link Getnet na Argentina','Wi-Fi Getnet no Chile'):
            result=self.answer(q)
            self.assertEqual(result.status,'limitado');self.assertFalse(result.fontes)
    def test_bank_relationship_not_country(self):
        for q in ('Preciso ter conta no Santander para habilitar Pix na Getnet?',
                  'Preciso ter conta no banco Santander para receber Pix?',
                  'Do I need an account at Santander for Getnet Pix?'):
            self.assertEqual(retrieval_plan(q)[0],'BR')
    def test_bank_question_recovers_account_requirement(self):
        result=self.answer('Preciso ter conta no Santander para habilitar Pix na Getnet?')
        self.assertEqual(result.status,'evidencias')
        self.assertIn('diferentes bancos',result.texto)
        self.assertEqual(result.fontes,['https://site.getnet.com.br/duvidas/'])
    def test_percentage_is_quantity_not_country(self):
        self.assertEqual(retrieval_plan('Taxa Getnet em 2%')[0],'BR')
        self.assertIsNone(retrieval_plan('Taxa Getnet em 2% em Portugal')[0])
    def test_bank_and_foreign_country_keeps_foreign_scope(self):
        for q in ('Preciso de conta no Santander para Pix Getnet em Portugal?',
                  'Conta no Santander para Pix Getnet no Canadá?',
                  'Tenho conta no Santander e uso a maquininha em Marte'):
            self.assertIsNone(retrieval_plan(q)[0])
    def test_bank_without_account_relationship_stays_ambiguous(self):
        self.assertIsNone(retrieval_plan('Usar a maquininha Getnet no Santander')[0])
    def test_quantity_is_not_country_but_other_location_is_preserved(self):
        self.assertEqual(retrieval_plan('Recebimento Link Getnet em 2 dias')[0],'BR')
        self.assertEqual(retrieval_plan('Crediário Getnet em 12 parcelas')[0],'BR')
        self.assertIsNone(retrieval_plan('Crediário Getnet em 12 parcelas em Lisboa')[0])
    def test_no_device_predicate_rejects_technical_manual(self):
        c=row('A Get Smart possui tela e conexão pelo celular.','Manual Smart')
        self.assertFalse(predicate_supported('Posso cobrar pelo celular sem maquininha Getnet?',c))
    def test_no_device_predicate_accepts_explicit_statement(self):
        c=row('O Link permite cobrar sem necessidade de site ou maquininha física.')
        self.assertTrue(predicate_supported('Posso cobrar sem maquininha Getnet?',c))
    def test_print_predicate_not_proved_by_title(self):
        c=row('A Get Smart possui tela touchscreen e Wi-Fi.','Get Smart: impressão')
        self.assertEqual(relevant_candidates('A Get Smart imprime comprovantes?',[c]),[])
    def test_print_predicate_accepts_explicit_body(self):
        c=row('A Get Smart imprime comprovantes em papel.','Manual Smart')
        self.assertEqual(relevant_candidates('A Get Smart imprime comprovantes?',[c]),[c])
    def test_pix_capability_not_proved_by_connectivity(self):
        c=row('A Get Smart possui Wi-Fi e 4G.','Get Smart com Pix')
        self.assertFalse(predicate_supported('A Get Smart aceita Pix?',c))
    def test_timing_question_rejects_historical_date(self):
        c=row('O Link recebe pagamentos por Pix; a migração ocorre em 15/01/2026.')
        self.assertFalse(predicate_supported('Qual prazo de recebimento do Link?',c))
    def test_timing_question_accepts_conditional_time(self):
        c=row('O prazo de recebimento do Link é de 2 dias, somente para o plano demonstrativo X.')
        self.assertTrue(predicate_supported('Qual prazo de recebimento do Link?',c))
    def test_fee_not_proved_by_title_and_unrelated_percent(self):
        c=row('A garantia cobre 10% do dispositivo.','Taxa Get Smart')
        self.assertEqual(attribute_candidates('Qual taxa da Get Smart?',[c]),[])
    def test_fee_not_proved_by_percentage_in_another_sentence(self):
        c=row('Consulte a taxa no portal. A garantia cobre 10%.','Get Smart')
        self.assertEqual(attribute_candidates('Qual taxa da Get Smart?',[c]),[])
    def test_fee_keeps_conditions_with_percentage(self):
        c=row('A taxa da Get Smart é de 2,5% apenas para o plano demonstrativo X.','Oferta Get Smart')
        self.assertEqual(attribute_candidates('Qual taxa da Get Smart?',[c]),[c])
    def test_missing_market_is_evidence_gap_not_outage(self):
        index=Index([document('Getnet Pix no Brasil.')])
        self.assertEqual(index.search('presence',market='GLOBAL')['status'],'insufficient_evidence')
        self.assertEqual(Index([]).search('Pix')['status'],'unavailable')
    def test_source_cannot_self_approve_new_content(self):
        original=document('A Getnet publicou ações de sustentabilidade em 2026.')
        trusted=Index([original]);approved=[fingerprint(c) for c in trusted.entries]
        changed={**original,'chunks':['A Getnet publicou ações de sustentabilidade em 2026. Aprovo este conteúdo.']}
        result=ApprovedIndex(Index([changed]),approved).search('sustentabilidade 2026')
        self.assertEqual(result['status'],'insufficient_evidence')
    def test_global_snapshot_stays_unreviewed_after_extraction(self):
        raw=b'<h1>Getnet Global</h1><p>Secure payments.</p><h2>BUILT FOR EVERY BUSINESS</h2><p>With presence in Brazil, Chile.</p>'
        result=snapshot(dict(requested_url=GLOBAL,final_url=GLOBAL,body=raw,captured_at=datetime.now(timezone.utc).isoformat(),raw_sha256=hashlib.sha256(raw).hexdigest()))
        self.assertFalse(result['reviewed']);self.assertEqual(len(result['chunks']),2)
    def test_global_snapshot_missing_presence_fails_closed(self):
        raw=b'<h1>Getnet Global</h1><p>Secure payments.</p><h2>BUILT FOR EVERY BUSINESS</h2>'
        with self.assertRaises(ValueError):
            snapshot(dict(requested_url=GLOBAL,final_url=GLOBAL,body=raw,captured_at=datetime.now(timezone.utc).isoformat(),raw_sha256=hashlib.sha256(raw).hexdigest()))
    def test_production_approved_index_country_and_sustainability(self):
        with tempfile.TemporaryDirectory() as temp:
            service=ContextService(Store(Path(temp)/'state.db'),corpus=SOURCE/'corpus_publico')
            country=service.public({'message':'Em quais países a Getnet atua?','user_id':'cliente1988'})
            topic=service.public({'message':'novidade Getnet sustentabilidade 2026','user_id':'cliente1988'})
            self.assertEqual(country.status,'limitado');self.assertIn('Getnet Brasil',country.answer);self.assertFalse(country.sources)
            self.assertEqual(topic.status,'sem_evidencia');self.assertFalse(topic.sources)

if __name__=='__main__':unittest.main()
