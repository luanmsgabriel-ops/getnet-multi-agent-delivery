import unittest,tempfile
from pathlib import Path
from unittest.mock import Mock
from app.rag.general_web import GeneralWebSearch
from app.rag.official_catalog import OfficialCatalogSearch,BR_LINK,link_howto_query
from app.context_service import ContextService
from app.context_store import Store
from app.context_state import apply_turn
from test_official_catalog_closure import body,download
from test_context_stateful import proposal,device

class SmallFixTests(unittest.TestCase):
    def test_howto_uses_complete_procedure_and_conditions(self):
        fetch=Mock(return_value=download(BR_LINK,body()));rss=Mock(return_value=[])
        r=GeneralWebSearch(transport=rss,official_only=True,catalog=OfficialCatalogSearch(fetch)).search('Como funciona o Link de Pagamento Getnet?')
        self.assertEqual(r['status'],'results');self.assertEqual(r['diagnostics']['rss_status'],'not_needed')
        self.assertIn('Use o app oficial.',r['results'][0]['snippet']);self.assertIn('elegíveis',r['results'][0]['snippet']);rss.assert_not_called()
    def test_catalog_failure_keeps_rss_fallback(self):
        catalog=Mock();catalog.search.return_value={'status':'unavailable','results':[]}
        rss=Mock(return_value=[{'title':'Link de Pagamento Getnet','snippet':'Link de pagamento permite vários produtos.','url':BR_LINK}])
        r=GeneralWebSearch(transport=rss,official_only=True,catalog=catalog).search('Como funciona o Link de Pagamento Getnet?')
        self.assertEqual(r['provider'],'Bing RSS');rss.assert_called_once()
    def test_foreign_query_does_not_fetch(self):
        rss=Mock();catalog=Mock()
        r=GeneralWebSearch(transport=rss,official_only=True,catalog=catalog).search('Como funciona o Link de Pagamento Getnet no Chile?')
        self.assertEqual(r['status'],'insufficient_evidence');rss.assert_not_called();catalog.search.assert_not_called()
    def test_private_query_does_not_fetch(self):
        rss=Mock();catalog=Mock()
        with self.assertRaises(ValueError):GeneralWebSearch(transport=rss,official_only=True,catalog=catalog).search('Minha senha é SYN_SECRET. Como funciona o Link de Pagamento Getnet?')
        rss.assert_not_called();catalog.search.assert_not_called()
    def test_attribute_queries_not_changed(self):
        for q in ['Qual a taxa do Link de Pagamento?','Como funciona o prazo de recebimento do Link de Pagamento Getnet?','Como funciona o Link de Pagamento Getnet no Chile?']:
            self.assertFalse(link_howto_query(q))
    def answer(self,labels):
        with tempfile.TemporaryDirectory() as t:
            svc=ContextService(Store(Path(t)/'s.db'));sid=svc.create('synthetic')
            m='Como configurar Wi-Fi '+', '.join(labels)+'?'
            devices=[device('new'+str(i+1),label,m,store='') for i,label in enumerate(labels)]
            p=proposal(m,devices=devices,requests=[{'kind':'information','topic':'connectivity','entities':['new1'],'quote':m}],focus=['new1'])
            return svc.step('synthetic',sid,m,proposal=p)['answer']
    def test_single_generic_label_not_echoed(self):
        answer=self.answer(['minha maquininha Getnet'])
        self.assertNotIn('minha maquininha Getnet:',answer);self.assertIn('Procurar Redes',answer);self.assertIn('nunca envie',answer)
    def test_named_label_preserved(self):
        self.assertIn('Smart entrada:',self.answer(['Smart entrada']))
    def test_multiple_devices_preserve_identification(self):
        self.assertIn('minha maquininha Getnet:',self.answer(['minha maquininha Getnet','Smart fundo']))
if __name__=='__main__':unittest.main()
