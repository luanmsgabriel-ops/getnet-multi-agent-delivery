import unittest
from unittest.mock import Mock
from app.knowledge import KnowledgeWeb,KnowledgeDispatch
from app.contracts import Entrada
class TemporalAmbiguity(unittest.TestCase):
 def test_direct_and_prefixed_ambiguity_never_select_fixed_source(self):
  search=Mock();exchange=Mock();weather=Mock();web=KnowledgeWeb(search,exchange=exchange,weather=weather)
  dispatcher=KnowledgeDispatch(Mock(),web)
  for query in ('weather Porto Alegre and Lisbon tomorrow','euro USD exchange rate tomorrow','clima Porto Alegre hoje e amanha','cotacao euro para dolar','weather Porto Alegre tomorrow and next week'):
   with self.subTest(query=query):
    for handler,text in ((web,query),(dispatcher,'pesquise na web: '+query)):
     r=handler.responder(Entrada(message=text,user_id='demo_A'),())
     self.assertEqual(r.status,'limitado')
  exchange.assert_not_called();weather.assert_not_called();search.search.assert_not_called()
