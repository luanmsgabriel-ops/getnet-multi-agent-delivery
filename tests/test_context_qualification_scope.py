"""Six prior frozen qualification-scope oracles. Mock interpretations/reviews; no network.
Two historical cases plus E01-E04: overlapping fixtures are intentional and not six independent behaviors.
"""
import json,copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from app.context_solo import SoloInterpreter
from app.context_service import ContextService
from app.context_state import apply_turn
from app.context_store import Store
def base(text,**kw):
 p={'devices':[],'observations':[],'requests':[{'kind':'summary','topic':'other','entities':['a'],'quote':text}],'focus':['a'],'resolve_pending':[]};p.update(kw);return p

def obs(text,field,value,**kw):
 p={'scope':'entity','entity':'a','subject':'device','incident':'net1','field':field,'value':value,'status':'asserted','origin':'customer','quote':text};p.update(kw);return p

class Sequence:
 def __init__(self,values):self.values=iter(values);self.payloads=[]
 def complete(self,system,payload,schema):
  self.payloads.append(copy.deepcopy(payload));value=next(self.values)
  if isinstance(value,Exception):raise value
  return copy.deepcopy(value)

def setup(tmp):
 s=ContextService(Store(Path(tmp)/'state.sqlite'));sid=s.create('synthetic_A');m='A Smart do caixa da Loja Cedro est\u00e1 sem internet.'
 s.step('synthetic_A',sid,m,proposal=base(m,devices=[{'ref':'a','label':'Smart do caixa','store':'Loja Cedro','quote':m}],observations=[obs(m,'connected','false')]))
 return s,sid

def execute(s,sid,text,p,review=None):
 c=Sequence([p]+([review] if review is not None else []));s.interpreter=SoloInterpreter(c);r=s.step('synthetic_A',sid,text);return r,{'payloads':c.payloads,'last_review':s.interpreter.last_review}

def values(result,field,**kw):return [f for f in result['state']['facts'].values() if f['field']==field and all(f.get(k)==v for k,v in kw.items())]


CASES=[{'id': 'historical_U04', 'message': 'Pelo que me lembro, selecionei a rede na Smart do caixa, mas não tenho certeza.', 'quote': None, 'verdict': 'uncertain', 'actionable': False}, {'id': 'independent_certainty_positive', 'message': 'Selecionei a rede na Smart do caixa. Pelo que me lembro, minha colega reiniciou a outra maquininha.', 'quote': None, 'verdict': 'uncertain', 'actionable': True}, {'id': 'E01', 'message': 'Pelo que me lembro, selecionei a rede na Smart do caixa, mas não tenho certeza.', 'quote': None, 'verdict': 'uncertain', 'actionable': False}, {'id': 'E02', 'message': 'Selecionei a rede na Smart do caixa. Pelo que me lembro, minha colega reiniciou a outra maquininha.', 'quote': None, 'verdict': 'supported', 'actionable': True}, {'id': 'E03', 'message': 'Selecionei a rede na Smart do caixa. Pelo que me lembro, minha colega reiniciou a outra maquininha.', 'quote': 'Selecionei a rede na Smart do caixa.', 'verdict': 'supported', 'actionable': True}, {'id': 'E04', 'message': 'Pelo que me lembro, selecionei a rede na Smart do caixa, mas não tenho certeza.', 'quote': 'selecionei a rede na Smart do caixa', 'verdict': 'uncertain', 'actionable': False}]
class QualificationScope(unittest.TestCase):
    def setUp(self):
        environment=patch.dict('os.environ',{'GETNET_WEB_SEARCH':'0','GETNET_CONTEXT_MODEL':'0'})
        environment.start();self.addCleanup(environment.stop)

def make_case(case):
    def test(self):
        with tempfile.TemporaryDirectory() as tmp:
            service,sid=setup(tmp)
            text=case['message'];quote=case['quote'] or text
            proposal=base(text,observations=[obs(quote,'network_selected','true')])
            review={'devices':[],'observations':[{'index':0,'verdict':case['verdict'],'origin':'customer'}]}
            result,trace=execute(service,sid,text,proposal,review)
            active=bool(values(result,'network_selected',value='true',status='asserted'))
            self.assertEqual(active,case['actionable'],json.dumps({'state':result['state'],'trace':trace},ensure_ascii=True))
    return test
for case in CASES:setattr(QualificationScope,'test_'+case['id'],make_case(case))
if __name__=='__main__':unittest.main(verbosity=2)
