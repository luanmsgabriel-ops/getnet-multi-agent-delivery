import copy,json,unittest
from evals.execution_observations import execution_references, URN
from evals.judging import make_packet, _checked_packet
from app.public_information import ENDPOINTS

class ExecutionObservations(unittest.TestCase):
    def network(self):
        return [dict(turn=0,endpoint=ENDPOINTS['geo'],params={'countryCode':'BR','name':'Porto Alegre'},data={}),
                dict(turn=0,endpoint=ENDPOINTS['weather'],params={'timezone':'America/Sao_Paulo','start_date':'2026-11-17','end_date':'2026-11-17','token':'DO_NOT_COPY'},at='2026-11-16T13:03:08+00:00',completed_at='2026-11-16T13:03:10+00:00',data={'daily':{'temperature':[32.4]}})]
    def packet(self, refs):
        return make_packet({'message':'Qual a previsao?'},{'answer':'Consulta concluida.','status':'ok','sources':[]},refs,opaque_id='test_123',reference_date='2026-11-16',service_context='synthetic_demo')
    def test_independent_and_bounded(self):
        n=self.network(); refs=execution_references(n,0);self.packet(refs)
        text=refs[0]['text'];self.assertIn('BR',text)
        for hidden in ['DO_NOT_COPY','32.4','Porto Alegre','temperature']:self.assertNotIn(hidden,text)
        n[1]['data']={'daily':{'temperature':[999]}}
        self.assertEqual(refs,execution_references(n,0))
        self.assertEqual(execution_references(n,1),[])
    def test_no_inferred_execution(self):
        self.assertEqual(execution_references([],0),[])
        for change in [{'error_type':'TimeoutError'},{'completed_at':'invalid'},{'completed_at':'2026-11-16T13:03:07+00:00'},{'endpoint':'https://invalid.example'}]:
            n=self.network();n[1].update(change);self.assertEqual(execution_references(n,0),[])
    def test_closed_provenance_and_privacy(self):
        packet=self.packet(execution_references(self.network(),0))
        for mutate in [('source','urn:getnet:execution:other'),('text','Senha: CanaryPrivate42.')]:
            p=copy.deepcopy(packet);p['references'][0][mutate[0]]=mutate[1]
            with self.assertRaises(ValueError):_checked_packet(p)
        p=copy.deepcopy(packet);p['references'][0]['extra']='x'
        with self.assertRaises(ValueError):_checked_packet(p)
    def test_fx_only_proves_observed_endpoint(self):
        n=self.network()[1];n['endpoint']=ENDPOINTS['fx'];n['params']={'secret':'DO_NOT_COPY'}
        refs=execution_references([n],0);self.packet(refs)
        self.assertNotIn('BR',refs[0]['text']);self.assertNotIn('DO_NOT_COPY',refs[0]['text'])
        self.assertNotIn('temperature',refs[0]['text'])

    def test_receipt_window_does_not_copy_answer(self):
        n=self.network();n[1]['response_received_at']='2026-11-16T13:03:11.500000+00:00'
        info=json.loads(execution_references(n,0)[0]['text'])
        self.assertEqual(info['response_received_at'],'2026-11-16T13:03:11.500000+00:00')
        n[1]['response_received_at']='2026-11-16T13:03:09+00:00'
        self.assertNotIn('response_received_at',json.loads(execution_references(n,0)[0]['text']))
