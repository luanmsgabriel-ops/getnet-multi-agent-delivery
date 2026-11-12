"""W04/W05: suporte público útil, segredos sintéticos e fronteiras preservadas.

Sem rede/modelo: corpus aprovado real, HTTP in-process e intérprete controlado.
"""
import contextlib
import io
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from app.context_service import ContextService
from app.context_store import Store
from app.privacy import clean_message
from app.intents import request_facts
from app.brazil_scope import market_of
from app.rag.guidance import WIFI, reviewed_guidance

W04='O manual manda digitar a senha do Wi-Fi na própria maquininha. Posso seguir essa orientação?'
W05='Minha senha de Wi-Fi é TESTE_SINTETICO_448. A920 aparece sem rede no Brasil.'

class ConnectivityRegression(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'state.db')
        self.service=ContextService(self.store,None)
        with patch('app.context_store.Store'):
            from app.context_api import create_app
        self.client=TestClient(create_app(self.service))

    def ask(self,message,endpoint='/chat',user='synthetic_a',sid=None):
        data={'message':message,'user_id':user}
        if sid:data['session_id']=sid
        response=self.client.post(endpoint,json=data)
        self.assertEqual(response.status_code,200)
        return response.json()

    def useful(self,body):
        self.assertIn(WIFI,body['sources'])
        self.assertIn('Procurar Redes',body['answer'])
        self.assertIn('confirme',body['answer'])
        self.assertNotIn('Essa dúvida se refere',body['answer'])
        self.assertNotIn('A920 tem',body['answer'])

    def test_w04_on_both_endpoints(self):
        for endpoint in ('/chat','/context/chat'):
            with self.subTest(endpoint=endpoint):
                body=self.ask(W04,endpoint);self.useful(body)
                self.assertIn('Sim:',body['answer'])
                self.assertIn('somente na própria maquininha',body['answer'])
                self.assertIn('não envie',body['answer'])

    def test_w05_on_both_endpoints(self):
        for endpoint in ('/chat','/context/chat'):
            with self.subTest(endpoint=endpoint):
                body=self.ask(W05,endpoint);self.useful(body)
                self.assertNotIn('TESTE_SINTETICO_448',json.dumps(body))
                self.assertIn('Não envie senhas',body['answer'])
                self.assertIn('qual mensagem de erro',body['answer'])

    def test_locative_requires_complete_device_noun(self):
        for text in ('na própria maquininha','no próprio aparelho','no seu próprio terminal','on my own device'):
            with self.subTest(text=text):
                self.assertNotEqual(market_of('Wi-Fi '+text).value,'UNKNOWN')
        for text in ('na própria cidade de Lisboa','na própria maquininha em Lisboa','na minha cidade','on my own device in Dublin'):
            with self.subTest(text=text):self.assertEqual(market_of('Wi-Fi '+text).value,'UNKNOWN')

    def test_absent_network_and_local_negation(self):
        for text in ('A920 sem rede','Terminal sem sinal','My terminal has no network','Machine without signal'):
            with self.subTest(text=text):self.assertTrue(request_facts(text).connectivity)
        for text in ('A920 não está sem rede','Terminal não ficou sem sinal','My terminal is not without network','Não quero configurar Wi-Fi','I do not want to configure Wi-Fi','Internet funcionando, transação recusada'):
            with self.subTest(text=text):self.assertFalse(request_facts(text).connectivity)
        self.assertTrue(request_facts('Não quero configurar Wi-Fi; outro terminal está sem rede').connectivity)

    def test_redaction_variations_preserve_useful_symptom(self):
        for text,secret in (
            ('Minha senha do WiFi FAKE_CANARY_127. A920 sem rede no Brasil.','FAKE_CANARY_127'),
            ('My password is FAKE_CANARY_128; my terminal has no network in Brazil.','FAKE_CANARY_128'),
            ('Minha senha de Wi-Fi é "na própria maquininha". A920 aparece sem rede no Brasil.','"na própria maquininha"')):
            with self.subTest(text=text):
                safe,removed=clean_message(text);self.assertTrue(removed);self.assertNotIn(secret,safe)
                body=self.ask(text);self.useful(body);self.assertNotIn(secret,json.dumps(body,ensure_ascii=False))

    def test_foreign_uncertain_and_geographic_device_complement(self):
        for text in ('Minha senha de Wi-Fi é FAKE_CANARY_129; A920 sem rede no Chile.',
                     'A920 está sem rede. Não sei em qual país fica a operação.',
                     'Posso digitar a senha de Wi-Fi na própria maquininha da Getnet que está em Lisboa?',
                     'A maquininha está na própria cidade de Lisboa e não conecta.'):
            for endpoint in ('/chat','/context/chat'):
                with self.subTest(text=text,endpoint=endpoint):
                    body=self.ask(text,endpoint);self.assertNotIn(WIFI,body['sources'])
                    self.assertNotIn('Procurar Redes',body['answer']);self.assertNotIn('FAKE_CANARY_129',str(body))

    def test_bare_model_never_proves_market_or_specific_procedure(self):
        for endpoint in ('/chat','/context/chat'):
            body=self.ask('A920 aparece sem rede.',endpoint)
            self.assertIn('Para uma maquininha Getnet Brasil: Se estiver usando Wi-Fi',body['answer'])
            self.assertNotIn('A920',body['answer'])

    def test_declined_wifi_does_not_hide_pix(self):
        msg='Minha senha de Wi-Fi é FAKE_CANARY_130. Não quero configurar Wi-Fi; quero saber se a Getnet Brasil exige conta corrente para receber Pix.'
        for endpoint in ('/chat','/context/chat'):
            body=self.ask(msg,endpoint)
            self.assertNotIn(WIFI,body['sources']);self.assertNotIn('Procurar Redes',body['answer'])
            self.assertIn('conta de pagamento',body['answer']);self.assertNotIn('FAKE_CANARY_130',str(body))

    def test_sanitized_search_never_bypasses_credentials_boundary(self):
        with patch.object(self.service.local,'responder') as knowledge:
            for endpoint in ('/chat','/context/chat'):
                body=self.ask('Pesquise na web: minha senha de Wi-Fi é FAKE_CANARY_131; A920 sem rede no Brasil.',endpoint)
                self.assertEqual(body['sources'],[]);self.assertNotIn('FAKE_CANARY_131',str(body))
            knowledge.assert_not_called()

    def test_missing_source_has_no_invented_steps(self):
        with patch.object(self.service.local,'_retrieve',return_value={'status':'insufficient_evidence','candidates':[]}):
            for msg in (W04,W05):
                for endpoint in ('/chat','/context/chat'):
                    body=self.ask(msg,endpoint);self.assertEqual(body['sources'],[])
                    self.assertNotIn('Procurar Redes',body['answer']);self.assertNotIn('Sim:',body['answer'])
                    self.assertRegex(body['answer'],'evidência|orientação Wi-Fi revisada')

    def test_reviewed_guidance_requires_hash_and_title(self):
        rows=self.service.local._retrieve('Como configurar Wi-Fi?')['candidates']
        row=next(c for c in rows if c['source']==WIFI)
        self.assertIsNotNone(reviewed_guidance(W04,[row]))
        for changed in ({**row,'text':row['text']+' conteúdo adulterado'}, {**row,'title':row['title']+' outra condição'}, {**row,'source':'https://example.invalid/'}):
            self.assertIsNone(reviewed_guidance(W04,[changed]))
            with patch.object(self.service.local,'_retrieve',return_value={'status':'candidates','candidates':[changed]}):
                text,sources=self.service._wifi(Store.empty(),'device')
                self.assertEqual(sources,[]);self.assertNotIn('Procurar Redes',text)

    def test_secret_absent_from_interpreter_state_response_and_logs(self):
        captured=[]
        def failed_interpreter(message,state,today):
            captured.append(json.dumps([message,state,today],ensure_ascii=False))
            raise RuntimeError('controlled provider failure')
        self.service.interpreter=Mock();self.service.interpreter.interpret.side_effect=failed_interpreter
        buffer=io.StringIO();handler=logging.StreamHandler(buffer);logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler,handler)
        with contextlib.redirect_stdout(buffer),contextlib.redirect_stderr(buffer):
            first=self.ask(W05,'/context/chat');self.useful(first)
            second=self.ask('A maquininha continua sem rede no Brasil.','/context/chat',sid=first['session_id'])
            self.useful(second)
        _,state=self.store.read('synthetic_a',first['session_id'])
        all_output=' '.join(captured)+json.dumps([first,second,state])+buffer.getvalue()
        self.assertNotIn('TESTE_SINTETICO_448',all_output)
        self.assertNotIn(b'TESTE_SINTETICO_448',Path(self.store.path).read_bytes())
        self.assertTrue(captured);self.assertIn('A920',captured[0]);self.assertIn('sem rede',captured[0])
        forbidden=self.client.post('/context/chat',json={'message':'Retome o problema','user_id':'synthetic_b','session_id':first['session_id']})
        self.assertEqual(forbidden.status_code,403)

    def test_restored_network_is_not_new_connection_problem(self):
        body=self.ask('A maquininha Getnet está no Brasil. Internet funcionando, transação recusada.')
        self.assertNotIn('Procurar Redes',body['answer']);self.assertNotIn(WIFI,body['sources'])
        self.assertRegex(body['answer'].lower(),'recusa|negada|transa')

    def test_request_to_enter_password_in_chat_never_gets_yes(self):
        for endpoint in ('/chat','/context/chat'):
            body=self.ask('Posso digitar a senha do Wi-Fi aqui no chat?',endpoint)
            self.assertNotIn('Sim:',body['answer'])
            self.assertIn('não envie',body['answer'])

    def test_extended_negation_and_independent_symptoms(self):
        for message in ('A920 não está mais aparecendo sem rede.', 'The terminal is not currently showing no network.'):
            self.assertFalse(request_facts(message).connectivity)
        self.assertTrue(request_facts('A920 não imprime e está sem rede no Brasil.').connectivity)
        self.assertTrue(request_facts('A920 não está mais sem rede; outro terminal está sem sinal.').connectivity)
        body=self.ask('A920 não está mais aparecendo sem rede. A operação é no Brasil.')
        self.assertNotIn('Procurar Redes',body['answer'])

    def test_outside_scope_stays_polite_and_tool_free(self):
        with patch.object(self.service.local,'responder') as knowledge:
            body=self.ask('Qual a previsão do tempo amanhã?')
            self.assertIn('Getnet Brasil',body['answer']);self.assertEqual(body['sources'],[])
            knowledge.assert_not_called()

if __name__=='__main__':unittest.main()
