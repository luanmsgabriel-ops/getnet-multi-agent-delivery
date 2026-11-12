import unittest
from datetime import date
from app.support import SupportSintetico,SyntheticTools,DEMO_PRINCIPAL,RecebiveisResult,Principal
from app.contracts import Entrada
class SyntheticSchedule(unittest.TestCase):
 def test_yesterday_is_relative_to_injected_clock(self):
  r=SupportSintetico(today=lambda:date(2026,11,7)).responder(Entrada(message="When will the money from yesterday's sales be deposited?",user_id='demo_A'),())
  self.assertEqual(r.status,'simulado');self.assertIn('2026-11-07',r.texto);self.assertIn('2026-11-06',r.texto);self.assertIn('2026-11-09',r.texto)
  self.assertIn('750,00',r.texto);self.assertNotIn('2026-11-10',r.texto);self.assertIn('Nao e promessa',r.texto)
 def test_schedule_deep_copy(self):
  tools=SyntheticTools(DEMO_PRINCIPAL);data=tools.consultar_recebiveis();data['schedule'][0]['amount_centavos']=1
  self.assertEqual(tools.consultar_recebiveis()['schedule'][0]['amount_centavos'],75000)
 def test_other_tenant_schedule(self):
  r=SupportSintetico(Principal('demo_B','loja_ficticia_B',DEMO_PRINCIPAL.scopes),today=lambda:date(2026,11,7)).responder(Entrada(message='vendas de ontem quando',user_id='demo_B'),())
  self.assertIn('2026-11-12',r.texto);self.assertNotIn('2026-11-09',r.texto)
 def test_invalid_sum_and_dates(self):
  data=SyntheticTools(DEMO_PRINCIPAL).consultar_recebiveis();data['total_centavos']=1
  with self.assertRaises(ValueError):RecebiveisResult.model_validate(data)
  data=SyntheticTools(DEMO_PRINCIPAL).consultar_recebiveis();data['schedule'][0]['expected_date']=date(2026,1,1)
  with self.assertRaises(ValueError):RecebiveisResult.model_validate(data)
