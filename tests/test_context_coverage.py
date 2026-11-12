import unittest
from app.context_contract import Turn
from app.context_model import SemanticInterpreter
from app.context_review import SemanticReview
from app.context_store import Store
from app.context_state import apply_turn
class Client:
    def __init__(self,result):self.result=result
    def complete(self,*args):return self.result
class Coverage(unittest.TestCase):
    def test_missing_opinion_is_preserved_non_actionable(self):
        message='Meu colega acha que a Smart está bloqueada. Eu não confirmei.'
        proposal={'devices':[],'observations':[],'requests':[{'kind':'diagnosis','topic':'connectivity','entities':[],'quote':message}],'focus':[],'resolve_pending':[]}
        omission={'incident':'','entity':None,'field':'symptom','value':'bloqueada','quote':message,'origin':'third_party','status':'uncertain'}
        reviewer=SemanticReview(Client({'devices':[],'observations':[],'context_omissions':[omission],'requests':[]}))
        interpreter=SemanticInterpreter(Client(proposal),reviewer)
        turn=interpreter.interpret(message,Store.empty(),'2026-11-10')
        state,result=apply_turn(Store.empty(),turn,message,review=interpreter.last_review)
        self.assertFalse(state['facts']);self.assertEqual(len(state['pending']),1);self.assertFalse(state['pending'][0]['actionable']);self.assertEqual(state['pending'][0]['observation']['origin'],'third_party')
    def test_omission_cannot_authorize_positive_progress(self):
        message='Não selecionei a rede.'
        p=Turn(devices=[],observations=[],focus=[],resolve_pending=[],requests=[{'kind':'next_step','topic':'connectivity','entities':[],'quote':message}])
        raw={'devices':[],'observations':[],'context_omissions':[{'entity':None,'incident':'','field':'network_selected','value':'true','origin':'customer','status':'asserted','quote':message}]}
        review=SemanticReview(Client(raw)).review(message,Store.empty(),p)
        self.assertEqual(review['context_omissions'],[])
    def test_negative_progress_does_not_resolve_positive_pending(self):
        state=Store.empty();state['devices']={'a':{'label':'Smart','store':'Loja A'}}
        state['pending']=[{'id':'p1','observation':{'field':'restart_attempted','value':'true'},'actionable':False}]
        message='Não reiniciei a Smart.'
        p={'devices':[],'focus':['a'],'observations':[{'entity':'a','incident':'i1','origin':'customer','field':'restart_attempted','value':'false','quote':message,'status':'false'}],'requests':[{'kind':'summary','topic':'connectivity','entities':['a'],'quote':message}],'resolve_pending':['p1']}
        after,v=apply_turn(state,p,message)
        self.assertEqual(len(after['pending']),1)
    def test_rejected_dependency_preserves_pending(self):
        state=Store.empty();state['devices']={'a':{'label':'Smart','store':'Loja A'}}
        state['pending']=[{'id':'p1','observation':{'field':'attempt','value':'reiniciei'},'actionable':False}]
        message='Reiniciei a Smart. Não reiniciei a outra.'
        p={'devices':[],'focus':['a'],'observations':[{'entity':'missing','incident':'i1','origin':'customer','status':'asserted','field':'attempt','value':'Reiniciei','quote':message},{'entity':'a','incident':'i1','origin':'customer','status':'asserted','field':'attempt','value':'Não reiniciei','quote':message}],'requests':[{'kind':'summary','topic':'connectivity','entities':['a'],'quote':message}],'resolve_pending':['p1']}
        after,v=apply_turn(state,p,message)
        self.assertEqual(len(after['pending']),1);self.assertTrue(v['rejected'])
