"""Published supervisor memory path: deterministic contracts, not LLM generalization.
All decisions/tools are controlled. No external/model calls or hidden holdout claim.
"""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from fastapi.testclient import TestClient
from app.agentic import Supervisor
from app.agentic_client import ModelUnavailable
from app.challenge_factory import create_app
from app.context_store import Store,Unavailable
from app.dialogue_memory import history_for
from test_agentic import Script,FakeCapabilities,consult,finish

USER='cliente1988'
INITIAL='A A920 do caixa azul está sem internet. Como verificar a conexão?'
CTX02='Corrigindo: ela é uma Get Smart. O problema continua no caixa azul.'

def bound_lookup(payload):
    prior=payload['conversation'][-1]
    text=prior['request']+' '+payload['request']
    proposal=consult(query=text)
    proposal['goals'][0]['context_turn_id']=prior['turn_id']
    return proposal

class MemoryFinalPoints(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict('os.environ',{'GETNET_AUTH_MODE':'demo','GETNET_WEB_SEARCH':'0','GETNET_ALLOW_MODEL_NETWORK':'0','GETNET_RAG_GENERATION':'disabled','GETNET_ORCHESTRATION':'deterministic'})
        self.env.start();self.addCleanup(self.env.stop)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.db';self.store=Store(self.path)
    def client(self,script,caps=None,store=None):
        return TestClient(create_app(store=store or self.store,supervisor=Supervisor(script,caps or FakeCapabilities())))
    def post(self,client,message,sid=None):
        body={'message':message,'user_id':USER}
        if sid:body['session_id']=sid
        return client.post('/context/chat',json=body)
    def test_ctx02_and_paraphrases_keep_current_correction_and_history(self):
        variants=[CTX02,'Me enganei sobre o modelo: é Get Smart; o caixa azul segue sem acesso à rede.','A máquina daquele caixa é a Get Smart, não a A920 que mencionei.']
        for message in variants:
            with self.subTest(message=message):
                script=Script(consult(query=INITIAL),finish(),bound_lookup,finish())
                c=self.client(script);first=self.post(c,INITIAL);self.assertEqual(first.status_code,200)
                sid=first.json()['session_id'];second=self.post(c,message,sid)
                self.assertEqual(second.status_code,200);self.assertEqual(second.json()['agentic']['stop'],'finish')
                payload=script.payloads[2];self.assertEqual(payload['request'],message)
                self.assertEqual(payload['conversation'][-1]['request'],INITIAL)
                self.assertFalse(payload['conversation'][-1]['outcome']['current_evidence'])
                history=history_for(self.store.read(USER,sid)[1]);self.assertEqual(history[-1]['request'],message)
                self.assertFalse(self.store.read(USER,sid)[1]['facts'])
    def test_followup_reference_bound_to_correct_turn_without_reviving_old_task(self):
        script=Script(consult(query=INITIAL),finish(),bound_lookup,finish())
        c=self.client(script);sid=self.post(c,INITIAL).json()['session_id']
        response=self.post(c,'E como configuro a rede nesse aparelho?',sid)
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['agentic']['stop'],'finish')
        goal=response.json()['agentic']['goals'][0]
        self.assertTrue(goal['context_turn_id']);self.assertIn('E como configuro',goal['request'])
    def test_process_restart_preserves_sanitized_history_not_live_facts(self):
        c=self.client(Script(consult(query=INITIAL),finish()));sid=self.post(c,INITIAL).json()['session_id']
        reopened=Store(self.path);script=Script(bound_lookup,finish());new=self.client(script,store=reopened)
        self.assertEqual(self.post(new,CTX02,sid).status_code,200)
        self.assertEqual(script.payloads[0]['conversation'][-1]['request'],INITIAL)
        self.assertTrue(script.payloads[0]['conversation'][-1]['outcome']['historical_only'])
    def test_reset_removes_reference_and_other_owner_cannot_read(self):
        script=Script(consult(query=INITIAL),finish());c=self.client(script);sid=self.post(c,INITIAL).json()['session_id']
        before=len(script.payloads)
        denied=c.post('/context/chat',json={'message':'E agora?','user_id':'other','session_id':sid})
        self.assertEqual(denied.status_code,403);self.assertEqual(len(script.payloads),before)
        self.assertEqual(c.post('/context/reset',json={'message':'reset','user_id':USER,'session_id':sid}).status_code,200)
        response=self.post(c,'Qual aparelho eu informei antes?',sid)
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['mode'],'context_reference_missing')
        self.assertEqual(len(script.payloads),before);self.assertEqual(history_for(self.store.read(USER,sid)[1]),[])
    def test_database_unavailable_blocks_model_and_tool_before_dispatch(self):
        sid=self.store.create(USER);script=Script(consult(query=INITIAL));caps=FakeCapabilities();c=self.client(script,caps)
        with patch.object(self.store,'read',side_effect=Unavailable('private db detail')):
            response=self.post(c,INITIAL,sid)
        self.assertEqual(response.status_code,503);self.assertEqual(script.payloads,[]);self.assertEqual(caps.calls,[])
        self.assertNotIn('private db detail',response.text)
        self.assertEqual(self.store.read(USER,sid)[0],0)
    def test_combined_tool_model_and_commit_failure_preserves_state(self):
        sid=self.store.create(USER);before=self.store.read(USER,sid)
        script=Script(consult(query=INITIAL),ModelUnavailable('private provider detail'))
        caps=FakeCapabilities();caps.run=Mock(side_effect=RuntimeError('private tool detail'))
        c=self.client(script,caps)
        with patch.object(self.store,'commit',side_effect=Unavailable('private db detail')):
            response=self.post(c,INITIAL,sid)
        self.assertEqual(response.status_code,503);self.assertEqual(len(script.payloads),2);self.assertEqual(caps.run.call_count,1)
        self.assertEqual(self.store.read(USER,sid),before)
        for secret in ['private provider detail','private tool detail','private db detail']:self.assertNotIn(secret,response.text)
        # Recovery is a fresh explicit request, never an implicit replay/retry.
        recovered=self.client(Script(consult(query=INITIAL),finish()))
        self.assertEqual(self.post(recovered,INITIAL,sid).status_code,200)
        self.assertEqual(self.store.read(USER,sid)[0],1)
    def test_model_unavailable_does_not_promote_successful_history(self):
        script=Script(consult(query=INITIAL),finish(),ModelUnavailable('private provider detail'))
        c=self.client(script);sid=self.post(c,INITIAL).json()['session_id']
        response=self.post(c,CTX02,sid)
        self.assertEqual(response.status_code,200);self.assertNotEqual(response.json()['agentic']['stop'],'finish')
        history=history_for(self.store.read(USER,sid)[1])
        self.assertEqual(history[-1]['outcome']['status'],'unavailable')
        self.assertEqual(history[0]['request'],INITIAL)
    def test_credentials_redacted_across_restart(self):
        message='Minha senha é CanaryMemory501. Como verificar a conexão da Get Smart?'
        def lookup(payload):return consult(query=payload['request'])
        script=Script(lookup,finish());c=self.client(script);r=self.post(c,message)
        self.assertEqual(r.status_code,200);sid=r.json()['session_id']
        saved=Store(self.path).read(USER,sid)[1]
        self.assertNotIn('CanaryMemory501',json.dumps(saved)+json.dumps(script.payloads)+r.text)

if __name__=='__main__':unittest.main(verbosity=2)
