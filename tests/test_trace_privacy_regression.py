"""Uma duração numérica não é evidência de saldo; verificar origem e schema."""
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from app.orchestration import Orquestrador
from app.support import SupportSintetico
import test_evaluation_flow as flow


def event(payload):
    return SimpleNamespace(ferramenta=payload.get('ferramenta'),
        model_dump=lambda **kw:{k:v for k,v in payload.items() if k not in kw.get('exclude',set())})

class TracePrivacyRegression(unittest.TestCase):
    def check_payload(self,payload):
        mocked=SimpleNamespace(executar=lambda *_:SimpleNamespace(eventos=[event(payload)]))
        with patch.object(flow,'Orquestrador',return_value=mocked):
            flow.FlowEvaluation().test_trace_minimizes_data()

    def good(self,duration=0.13612500333692878):
        return dict(agente='support',status='ok',ferramenta='consultar_recebiveis',duracao_ms=duration)

    def test_legitimate_duration_containing_amount_digits(self):
        self.check_payload(self.good())
        self.check_payload(self.good(1250.0))

    def test_data_leaks_in_every_text_field_fail(self):
        for field in ('agente','status','ferramenta'):
            for secret in ('UNIQUE-MESSAGE','demo_A','1250'):
                payload=self.good();payload[field]=secret
                with self.subTest(field=field,secret=secret), self.assertRaises(AssertionError):self.check_payload(payload)

    def test_extra_and_nested_leaks_fail(self):
        for value in ('1250',{'message':'UNIQUE-MESSAGE','user_id':'demo_A','balance':1250}):
            payload=self.good();payload['private']=value
            with self.assertRaises(AssertionError):self.check_payload(payload)

    def test_non_numeric_nonfinite_and_negative_duration_fail(self):
        for value in ('1250',float('nan'),float('inf'),-1.0):
            with self.subTest(value=value),self.assertRaises(AssertionError):self.check_payload(self.good(value))

    def test_controlled_clock_proves_duration_origin(self):
        for duration in (1250.0,37.5):
            seconds=duration/1000
            with patch('app.orchestration.perf_counter',side_effect=[0,seconds,2,2+seconds]), patch('app.support.perf_counter',side_effect=[10,10+seconds]):
                result=Orquestrador(support=SupportSintetico()).executar({'message':'meu saldo UNIQUE-MESSAGE','user_id':'demo_A'})
            self.assertEqual(len(result.eventos),3)
            for trace in result.eventos:self.assertAlmostEqual(trace.duracao_ms,duration)
            if duration!=1250:
                # Numeric private data cannot silently replace the measured time.
                altered=result.eventos[1].model_copy(update={'duracao_ms':1250.0})
                with self.assertRaises(AssertionError):self.assertAlmostEqual(altered.duracao_ms,duration)
