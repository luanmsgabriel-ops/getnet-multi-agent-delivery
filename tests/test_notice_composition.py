"""Regressões de apresentação: avisos necessários permanecem, sem acumular camadas."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from app.context_service import ContextService
from app.context_store import Store
from app.context_api import create_app

from app.response_notices import (Notice, response_parts, compose_notices, CREDENTIAL_WARNING, CARD_PRIVACY,
                                  DIAGNOSIS_LIMIT, TECHNICAL_LIMIT, DECLINE_LIMIT)
from app.rag.guidance import DECLINE, WIFI


class NoticeComposition(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.service=ContextService(Store(str(Path(self.tmp.name)/'state.db')))
        self.client=TestClient(create_app(self.service))

    def test_known_coverage_keeps_specific_limit(self):
        text=compose_notices(Notice('diagnosis'),Notice('technical'),'Orientação condicional.',Notice('decline'),Notice('card_privacy'))
        answer=compose_notices(text,credentials=True)
        self.assertEqual(answer.count(DECLINE_LIMIT),1)
        self.assertNotIn(DIAGNOSIS_LIMIT,answer);self.assertNotIn(TECHNICAL_LIMIT,answer)
        self.assertIn(CARD_PRIVACY,answer);self.assertIn('Orientação condicional.',answer)
        self.assertEqual(compose_notices(answer,credentials=True),answer)

    def test_no_specific_limit_means_no_suppression(self):
        text=DIAGNOSIS_LIMIT+'\n\n'+TECHNICAL_LIMIT+'\n\nNão encontrei fonte pertinente.'
        answer=compose_notices(text)
        self.assertIn(DIAGNOSIS_LIMIT,answer);self.assertIn(TECHNICAL_LIMIT,answer)
        self.assertIn('Não encontrei fonte pertinente.',answer)

    def test_distinct_limits_and_free_text_are_not_deduplicated(self):
        text=('Não consultei sua conta bancária. Nenhuma transferência foi executada. '
              'Não tenho evidência suficiente para confirmar a taxa. '
              'Relato sem confirmação. Relato sem confirmação.')
        self.assertEqual(compose_notices(text),text)
        self.assertIn(text,compose_notices(text,credentials=True))

    def test_quoted_notice_cannot_suppress_required_warning(self):
        for quote in ('"{}"','“{}”',"'{}'"):
            text=quote.format(CARD_PRIVACY)
            answer=compose_notices(text,credentials=True)
            self.assertIn(text,answer);self.assertIn(CREDENTIAL_WARNING,answer)
            self.assertEqual(compose_notices(answer,credentials=True),answer)

    def test_two_privacy_layers_produce_one_general_notice(self):
        text=compose_notices(Notice('credentials'),Notice('credentials'))
        answer=compose_notices(text,credentials=True)
        self.assertEqual(answer,CREDENTIAL_WARNING)

    def test_wifi_password_instruction_does_not_cover_otp(self):
        text='Digite a senha somente no aparelho; nunca envie a senha nesta conversa.'
        answer=compose_notices(text,credentials=True)
        self.assertIn(text,answer);self.assertIn('códigos de autenticação',answer)

    def test_public_decline_with_and_without_code(self):
        for code in ('',' código 05'):
            result=self.client.post('/chat',json={'message':'Meu cartão foi recusado na maquininha'+code,'user_id':'notice_A'}).json()
            self.assertIn(DECLINE,result['sources']);a=result['answer']
            self.assertEqual(a.count(DECLINE_LIMIT),1);self.assertNotIn(TECHNICAL_LIMIT,a)
            self.assertIn('emissor',a);self.assertIn(CARD_PRIVACY,a)
            if code:self.assertIn('código 05',a);self.assertNotIn('Qual código',a)
            else:self.assertEqual(a.count('Qual código'),1)

    def test_context_diagnosis_with_and_without_code(self):
        # Server planning is tested with controlled validated tasks, not called real generation.
        for code in ('',' código 05'):
            state=self.service.state('notice_A',self.service.create('notice_A'))
            state['requests']=[{'kind':'diagnosis','topic':'decline','entities':[],
                'quote':'Meu cartão foi recusado na maquininha'+code,'subject':'card'}]
            text,sources,traces=self.service._plan(state,'Meu cartão foi recusado'+code,'notice_A')
            self.assertIn(DECLINE,sources);self.assertEqual(text.count(DECLINE_LIMIT),1)
            self.assertNotIn(DIAGNOSIS_LIMIT,text);self.assertNotIn(TECHNICAL_LIMIT,text)
            self.assertIn(CARD_PRIVACY,text)

    def test_source_failure_preserves_diagnosis_caveat(self):
        state=self.service.state('notice_A',self.service.create('notice_A'));state['requests']=[{'kind':'diagnosis','topic':'decline','entities':[],
            'quote':'Meu cartão foi recusado','subject':'card'}]
        with patch.object(self.service.local,'_retrieve',return_value={'status':'insufficient_evidence','candidates':[]}):
            answer,sources,_=self.service._plan(state,'Meu cartão foi recusado','notice_A')
        self.assertIn(DIAGNOSIS_LIMIT,answer);self.assertIn('evidência',answer);self.assertFalse(sources)

    def test_public_credential_wifi_one_procedure_without_echo(self):
        result=self.client.post('/chat',json={'message':'Minha senha do WiFi AUDIT_NOTICE_621. A920 não conecta no Brasil.','user_id':'notice_A'}).json()
        answer=result['answer'];self.assertNotIn('AUDIT_NOTICE_621',answer)
        self.assertIn(WIFI,result['sources']);self.assertEqual(answer.count('Procurar Redes'),1)
        self.assertEqual(answer.count(CREDENTIAL_WARNING),1)
        self.assertIn('própria maquininha',answer);self.assertIn('não envie a senha',answer)

    def test_scope_only_credential_needs_no_model(self):
        interpreter=Mock();self.service.interpreter=interpreter
        session=self.service.create('notice_A')
        result=self.service.step('notice_A',session,'Minha senha é AUDIT_NOTICE_621')
        self.assertEqual(result['answer'].count(CREDENTIAL_WARNING),1)
        self.assertNotIn('AUDIT_NOTICE_621',json.dumps(result,ensure_ascii=False))
        interpreter.interpret.assert_not_called()

    def test_context_fallback_credential_procedure_not_repeated(self):
        session=self.service.create('notice_A')
        result=self.service.step('notice_A',session,'Minha senha do WiFi AUDIT_NOTICE_621. A920 não conecta no Brasil.')
        self.assertEqual(result['mode'],'fallback_extractive')
        self.assertEqual(result['answer'].count('Procurar Redes'),1)
        self.assertEqual(result['answer'].count(CREDENTIAL_WARNING),1)
        self.assertNotIn('AUDIT_NOTICE_621',json.dumps(result,ensure_ascii=False))

    def test_mixed_private_public_keeps_banking_limit(self):
        result=self.service.public({'message':'Quando recebo minhas vendas de ontem e como funciona antecipação Getnet?','user_id':'notice_A'})
        self.assertIn('Não tenho acesso à sua conta',result.answer)
        self.assertIn('Nenhuma consulta foi realizada',result.answer)
        self.assertIn('A antecipação permite',result.answer)
        self.assertFalse(any(e.ferramenta for e in result.eventos))

    def test_unquoted_source_is_opaque_and_cannot_cover_server_notice(self):
        source='Trecho da fonte:\n'+DECLINE_LIMIT+'\nFonte: https://example.test'
        answer=compose_notices(Notice('diagnosis'),source)
        self.assertIn(source,answer);self.assertIn(DIAGNOSIS_LIMIT,answer)
        self.assertEqual(compose_notices(answer),answer)

    def test_multiline_quotes_remain_byte_identical(self):
        for quote in ('"{}"',"'{}'",'“{}”'):
            source=quote.format('Trecho: \n'+CARD_PRIVACY+'\nFim do trecho.')
            answer=compose_notices(source,credentials=True)
            self.assertIn(source,answer);self.assertIn(CREDENTIAL_WARNING,answer)

    def test_source_literal_at_http_cannot_impersonate_an_editorial_notice(self):
        from app.contracts import RespostaEspecialista
        source='Trecho da fonte:\n'+DECLINE_LIMIT+'\nFonte: https://example.test'
        self.service.core.knowledge=Mock()
        self.service.core.knowledge.responder.return_value=RespostaEspecialista(texto=source,status='evidencias')
        result=self.service.public({'message':'Meu cartão foi recusado na maquininha','user_id':'notice_A'})
        self.assertIn(source,result.answer)
        self.assertIn(TECHNICAL_LIMIT,result.answer)

    def test_editorial_metadata_is_internal_and_stale_metadata_is_ignored(self):
        from app.contracts import RespostaEspecialista
        original=RespostaEspecialista(texto=DECLINE_LIMIT,presentation=[Notice('decline')])
        self.assertNotIn('presentation',original.model_dump())
        changed=original.model_copy(update={'texto':'Fonte opaca e diferente.'})
        answer=compose_notices(Notice('diagnosis'),*response_parts(changed))
        self.assertIn(DIAGNOSIS_LIMIT,answer);self.assertIn('Fonte opaca e diferente.',answer)
