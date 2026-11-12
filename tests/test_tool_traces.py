import unittest
from unittest.mock import Mock
from pydantic import ValidationError
from app.contracts import ToolTrace
from app.support import SupportSintetico,DEMO_PRINCIPAL
from app.orchestration import Orquestrador

class ToolTracesTest(unittest.TestCase):
    def run_support(self,message='meu saldo e minha maquininha',user='demo_A',tools=None):
        return Orquestrador(support=SupportSintetico(tools=tools)).executar({'message':message,'user_id':user})
    def test_both_success(self):
        r=self.run_support();events=[e for e in r.eventos if e.ferramenta]
        self.assertEqual([e.ferramenta for e in events],['consultar_recebiveis','consultar_terminal'])
        self.assertTrue(all(e.status=='ok' and e.duracao_ms>=0 for e in events))
    def test_failure_sanitized(self):
        tools=Mock(principal=DEMO_PRINCIPAL);tools.consultar_recebiveis.side_effect=RuntimeError('secret-card-123456')
        r=self.run_support(tools=tools);events=[e for e in r.eventos if e.ferramenta]
        self.assertEqual(r.status,'indisponivel');self.assertEqual(events[0].status,'falha')
        self.assertNotIn('secret-card',r.model_dump_json());tools.consultar_terminal.assert_not_called()
    def test_denied_before_calls_no_tool_event(self):
        self.assertFalse(any(e.ferramenta for e in self.run_support(user='demo_B').eventos))
    def test_no_arguments_or_results(self):
        events=[e.model_dump() for e in self.run_support().eventos]
        for e in events:self.assertEqual(set(e),{'agente','status','ferramenta','duracao_ms'})
        for forbidden in ['demo_A','loja_ficticia','125000','DEMO-A-001']:
            self.assertNotIn(forbidden,str(events))
    def test_trace_schema_rejects_untrusted_fields(self):
        for data in [{'ferramenta':'arbitrary-secret','status':'ok','duracao_ms':1.0},{'ferramenta':'consultar_terminal','status':'ok','duracao_ms':-1.0},{'ferramenta':'consultar_terminal','status':'ok','duracao_ms':1.0,'input':'secret'}]:
            with self.assertRaises(ValidationError):ToolTrace.model_validate(data)
    def test_trace_state_not_shared(self):
        o=Orquestrador(support=SupportSintetico())
        a=o.executar({'message':'meu saldo','user_id':'demo_A'})
        b=o.executar({'message':'minha maquininha','user_id':'demo_A'})
        self.assertEqual([e.ferramenta for e in a.eventos if e.ferramenta],['consultar_recebiveis'])
        self.assertEqual([e.ferramenta for e in b.eventos if e.ferramenta],['consultar_terminal'])
