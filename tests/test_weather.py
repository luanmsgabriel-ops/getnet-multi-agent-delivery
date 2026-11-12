import unittest
from unittest.mock import Mock
from app.knowledge import KnowledgeWeb
from app.contracts import Entrada

class WeatherTest(unittest.TestCase):
 def test_provider_gets_no_context(self):
  provider=Mock(return_value={'date':'2026-11-08','minimum':15,'maximum':24});search=Mock()
  r=KnowledgeWeb(search,weather=provider).responder(Entrada(message='Porto Alegre weather tomorrow',user_id='private_identity'),())
  self.assertEqual(r.status,'limitado');provider.assert_not_called();search.search.assert_not_called();self.assertIn('dedicado',r.texto)
 def test_fail_closed(self):
  r=KnowledgeWeb(Mock(),weather=Mock(side_effect=RuntimeError('PRIVATE'))).responder(Entrada(message='previsao Porto Alegre amanha',user_id='demo_A'),())
  self.assertEqual(r.status,'limitado');self.assertNotIn('PRIVATE',r.texto)
 def test_unknown_city_not_sent(self):
  provider=Mock();search=Mock();r=KnowledgeWeb(search,weather=provider).responder(Entrada(message='clima Curitiba amanha',user_id='demo_A'),())
  self.assertEqual(r.status,'limitado');provider.assert_not_called();search.search.assert_not_called()
