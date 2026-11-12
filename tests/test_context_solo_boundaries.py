"""Sixteen frozen independent Solo boundaries, no network or paid model.
P09/P10/P11 only adapted the fixture to explicit retracts target; original outcomes unchanged.
P13-P16 were frozen before execution of the new assertion-version contract.
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

def probe(case):
 with tempfile.TemporaryDirectory() as tmp:
  s,sid=setup(tmp);review={'devices':[],'observations':[]};expected=None
  if case=='P01':
   m='Selecionei a rede na Smart do caixa.';p=base(m,observations=[obs(m,'network_selected','true')]);r,e=execute(s,sid,m,p);ok=bool(values(r,'network_selected',value='true',status='asserted')) and len(e['payloads'])==1
  elif case in ('P02','P05','P06'):
   a='Selecionei a rede na Smart do caixa.';b='A Smart do caixa continua com problema.';m=a+' '+b;p=base(m,observations=[obs(a,'network_selected','true'),obs(b,'connected','true')])
   if case=='P02':review['observations']=[{'index':0,'verdict':'unsupported','origin':'hypothesis'},{'index':1,'verdict':'unsupported','origin':'hypothesis'}]
   elif case=='P05':review=TimeoutError('synthetic review timeout')
   else:review={'not_a_decision':True}
   r,e=execute(s,sid,m,p,review);ok=bool(values(r,'network_selected',value='true',status='asserted'))
  elif case=='P03':
   a='O manual descreve a Smart da entrada na Loja Norte.';b='A Smart do caixa continua com problema.';m=a+' '+b
   p=base(m,devices=[{'ref':'b','label':'Smart da entrada','store':'Loja Norte','quote':a}],observations=[obs(b,'connected','true')]);review={'devices':[{'index':0,'verdict':'supported','origin':'customer'}],'observations':[{'index':0,'verdict':'unsupported','origin':'hypothesis'}]}
   r,e=execute(s,sid,m,p,review);ok='b' not in r['state']['devices']
  elif case=='P04':
   a='Ontem selecionei a rede na Smart do caixa.';b='Hoje n\u00e3o selecionei a rede na Smart do caixa.';m=a+' '+b;p=base(m,observations=[obs(a,'network_selected','true',incident='yesterday'),obs(b,'network_selected','true',incident='today')]);review['observations']=[{'index':0,'verdict':'unsupported','origin':'hypothesis'},{'index':1,'verdict':'unsupported','origin':'hypothesis'}]
   r,e=execute(s,sid,m,p,review);ok=bool(values(r,'network_selected',value='true',status='asserted',incident='yesterday')) and e['payloads'][1]['disputed']['observations']==[1]
  elif case in ('P07','P08'):
   m='Provavelmente selecionei a rede na Smart do caixa.' if case=='P07' else 'N\u00e3o tenho certeza se selecionei a rede na Smart do caixa.';p=base(m,observations=[obs(m,'network_selected','true')]);review['observations']=[{'index':0,'verdict':'uncertain','origin':'customer'}]
   r,e=execute(s,sid,m,p,review);ok=not values(r,'network_selected',value='true',status='asserted')
  elif case in ('P09','P10','P11'):
   if case!='P11':
    old='true' if case=='P09' else 'false';text='Selecionei a rede na Smart do caixa.' if old=='true' else 'N\u00e3o selecionei a rede na Smart do caixa.';s.step('synthetic_A',sid,text,proposal=base(text,observations=[obs(text,'network_selected',old)]))
   a='Agora selecionei a rede na Smart do caixa.'
   b=('Retiro meu relato anterior de ter selecionado a rede ontem.' if case=='P09' else 'Retiro meu relato anterior de n\u00e3o ter selecionado a rede ontem.') if case!='P11' else 'Retiro o que acabei de dizer sobre ter selecionado a rede; n\u00e3o consigo confirmar.'
   m=a+' '+b;p=base(m,observations=[obs(a,'network_selected','true'),obs(b,'network_selected','true' if case in ('P09','P11') else 'false',status='retracted')]);p['observations'][1]['retracts']='turn:0' if case=='P11' else next(f['assertion_id'] for f in s.state('synthetic_A',sid)['facts'].values() if f['field']=='network_selected');r,e=execute(s,sid,m,p)
   ok=bool(values(r,'network_selected',value='true',status='asserted')) if case!='P11' else not values(r,'network_selected',value='true',status='asserted')
  else:
   m='Minha Smart da entrada da Loja Cedro est\u00e1 sem internet.';s.step('synthetic_A',sid,m,proposal=base(m,devices=[{'ref':'b','label':'Smart da entrada','store':'Loja Cedro','quote':m}],focus=['a']))
   a='Selecionei a rede na Smart da entrada.';b='A Smart do caixa continua com problema.';m=a+' '+b;p=base(m,observations=[obs(a,'network_selected','true',entity='a'),obs(b,'connected','true')]);review['observations']=[{'index':0,'verdict':'supported','origin':'customer'},{'index':1,'verdict':'unsupported','origin':'hypothesis'}]
   r,e=execute(s,sid,m,p,review);ok=not values(r,'network_selected',entity='a',value='true',status='asserted')
  return bool(ok),{'result':r,**e}

_original_probe=probe

def probe(case):
 if case not in ('P13','P14','P15','P16'):return _original_probe(case)
 with tempfile.TemporaryDirectory() as tmp:
  s,sid=setup(tmp);a='Selecionei a rede na Smart do caixa.';s.step('synthetic_A',sid,a,proposal=base(a,observations=[obs(a,'network_selected','true')]))
  if case=='P13':
   a='A Smart da entrada da Loja Cedro est\u00e1 sem internet.'.encode().decode('unicode_escape')
   # Source string uses ASCII escape only to avoid console encoding ambiguity.
   s.step('synthetic_A',sid,a,proposal=base(a,devices=[{'ref':'b','label':'Smart da entrada','store':'Loja Cedro','quote':a}],focus=['a']))
   a='Selecionei a rede na Smart da entrada.';s.step('synthetic_A',sid,a,proposal=base(a,observations=[obs(a,'network_selected','true',entity='b')],focus=['a']))
   prior=s.state('synthetic_A',sid);target=next(f['assertion_id'] for f in prior['facts'].values() if f['field']=='network_selected' and f['entity']=='b')
   m='Retiro o relato de ter selecionado a rede na Smart do caixa.';p=base(m,observations=[obs(m,'network_selected','true',status='retracted',retracts=target)]);r,e=execute(s,sid,m,p);first=bool(values(r,'network_selected',entity='a',status='asserted')) and bool(values(r,'network_selected',entity='b',status='asserted'))
   # Same entity, different modality is also isolated.
   s.interpreter=None;m='Na Smart do caixa o Pix foi aprovado e o cart\u00e3o foi recusado.'.encode().decode('unicode_escape');s.step('synthetic_A',sid,m,proposal=base(m,observations=[obs(m,'payment_status','approved',subject='pix',incident='pay1'),obs(m,'payment_status','declined',subject='card',incident='pay1')]))
   st=s.state('synthetic_A',sid);target=next(f['assertion_id'] for f in st['facts'].values() if f['field']=='payment_status' and f['subject']=='card')
   m='Retiro a confirma\u00e7\u00e3o do Pix na Smart do caixa.'.encode().decode('unicode_escape');p=base(m,observations=[obs(m,'payment_status','approved',subject='pix',incident='pay1',status='retracted',retracts=target)]);r2,e2=execute(s,sid,m,p);ok=first and bool(values(r2,'payment_status',subject='pix',value='approved',status='asserted')) and bool(values(r2,'payment_status',subject='card',value='declined',status='asserted'));return ok,{'entity_result':r,'entity_review':e,'modality_result':r2,'modality_review':e2}
  if case=='P14':
   evidence=[];ok=True
   for target in ('turn:1','turn:-1','turn:nope'):
    m='Retiro o relato de sele\u00e7\u00e3o na Smart do caixa.'.encode().decode('unicode_escape');p=base(m,observations=[obs(m,'network_selected','true',status='retracted',retracts=target)]);r,e=execute(s,sid,m,p);ok=ok and bool(values(r,'network_selected',status='asserted',value='true'));evidence.append({'target':target,'result':r,'interpretation':e})
   return ok,{'subcases':evidence}
  old=next(f['assertion_id'] for f in s.state('synthetic_A',sid)['facts'].values() if f['field']=='network_selected')
  a='Agora selecionei a rede na Smart do caixa.';b='A Smart do caixa est\u00e1 imprimindo.'.encode().decode('unicode_escape');c='Retiro meu relato antigo de sele\u00e7\u00e3o de rede.' if case=='P15' else 'Retiro a sele\u00e7\u00e3o de rede que acabei de relatar.';c=c.encode().decode('unicode_escape');m=a+' '+b+' '+c
  p=base(m,observations=[obs(a,'network_selected','true'),obs(b,'printing_ok','true'),obs(c,'network_selected','true',status='retracted',retracts=old if case=='P15' else 'turn:0')]);r,e=execute(s,sid,m,p);selected=bool(values(r,'network_selected',value='true',status='asserted'));ok=bool(values(r,'printing_ok',status='asserted',value='true')) and (selected if case=='P15' else not selected and bool(values(r,'network_selected',status='retracted')));return ok,{'result':r,**e}
DATA=[['P01', 'Direct valid report requires no second verdict and preserves U01 utility.'], ['P02', 'Extraneous reviewer verdict cannot erase nondisputed accepted index.'], ['P03', 'Review present for another item cannot admit rejected quoted identity.'], ['P04', 'Same entity/field across separate incidents must not expand disputes to locally accepted item.'], ['P05', 'Review timeout must preserve valid independent local report.'], ['P06', 'Malformed review must preserve valid independent local report.'], ['P07', 'Explicitly probable report cannot become confirmed progress through local acceptance.'], ['P08', 'Explicit uncertainty with se remains nonactionable after reviewer uncertainty.'], ['P09', 'Historical retraction must not erase current independent report even when value unchanged.'], ['P10', 'Historical retraction of different old value preserves current report.'], ['P11', 'Withdrawal of just-made report must remove its actionable certainty.'], ['P12', 'Malformed/extra reviewer supported index cannot approve wrong named subject.'], ['P13', 'Retraction ID from another entity or modality cannot withdraw either claim.'], ['P14', 'Invalid/future turn index cannot withdraw a current claim.'], ['P15', 'Historical target preserves new equivalent claim and independent field.'], ['P16', 'Current-turn target withdraws only referenced claim, preserving independent field.']]
class SoloBoundaries(unittest.TestCase):
 def setUp(self):
  p=patch.dict('os.environ',{'GETNET_WEB_SEARCH':'0'});p.start();self.addCleanup(p.stop)
def make_case(case,expected):
 def test(self):
  passed,evidence=probe(case);self.assertTrue(passed,expected+' '+json.dumps(evidence,ensure_ascii=True))
 return test
for case,expected in DATA:setattr(SoloBoundaries,'test_'+case,make_case(case,expected))
if __name__=='__main__':unittest.main(verbosity=2)

class VersionAndPendingRegressions(unittest.TestCase):
 def test_repeated_text_has_distinct_claim_version(self):
  with tempfile.TemporaryDirectory() as tmp:
   service,sid=setup(tmp)
   message='Selecionei a rede na Smart do caixa.'
   p=base(message,observations=[obs(message,'network_selected','true')])
   service.step('synthetic_A',sid,message,proposal=p)
   old=next(f['assertion_id'] for f in service.state('synthetic_A',sid)['facts'].values() if f['field']=='network_selected')
   service.step('synthetic_A',sid,message,proposal=p)
   current=next(f['assertion_id'] for f in service.state('synthetic_A',sid)['facts'].values() if f['field']=='network_selected')
   self.assertNotEqual(old,current)
   text='Retiro o relato antigo de ter selecionado a rede.'
   result=service.step('synthetic_A',sid,text,proposal=base(text,observations=[obs(text,'network_selected','true',status='retracted',retracts=old)]))
   self.assertTrue(values(result,'network_selected',value='true',status='asserted'))
   self.assertTrue(result['validation']['rejected'])
 def test_unknown_pending_resolves_only_grounded_same_subject(self):
  with tempfile.TemporaryDirectory() as tmp:
   service,sid=setup(tmp)
   message='Reiniciei uma delas, mas nao sei qual.'
   result=service.step('synthetic_A',sid,message,proposal=base(message,observations=[obs(message,'restart_attempted','unknown',entity=None,status='uncertain')]))
   pending=result['state']['pending'][0]['id']
   text='Reiniciei a Smart do caixa.'
   result=service.step('synthetic_A',sid,text,proposal=base(text,observations=[obs(text,'restart_attempted','true')],resolve_pending=[pending]))
   self.assertEqual(result['state']['pending'],[])
   self.assertTrue(values(result,'restart_attempted',value='true',status='asserted'))

class RealRoundRegressions(unittest.TestCase):
 def test_unstored_retracted_claim_is_history_not_pending(self):
  with tempfile.TemporaryDirectory() as tmp:
   service,sid=setup(tmp)
   a='Eu disse que tinha selecionado a rede, mas estava lendo o tutorial.'
   b='Ainda nao selecionei a rede na Smart do caixa.';message=a+' '+b
   result=service.step('synthetic_A',sid,message,proposal=base(message,observations=[obs(a,'network_selected','true',status='retracted'),obs(b,'network_selected','false',status='corrected')]))
   self.assertEqual(result['state']['pending'],[])
   self.assertTrue(values(result,'network_selected',value='false',status='corrected'))
 def test_unsupported_configuration_retains_local_guidance(self):
  with tempfile.TemporaryDirectory() as tmp:
   service,sid=setup(tmp);message='Configure minha Smart por mim e receba a senha no chat.'
   result=service.step('synthetic_A',sid,message,proposal=base(message,requests=[{'kind':'unsupported_action','action':'configure_device','topic':'connectivity','entities':['a'],'quote':message}]))
   self.assertTrue(result['sources']);self.assertIn('no próprio aparelho',result['answer']);self.assertNotIn('transferir saldo',result['answer'])
 def test_diagnosis_does_not_repeat_unrequested_procedure(self):
  with tempfile.TemporaryDirectory() as tmp:
   service,sid=setup(tmp);message='Selecionei a rede na Smart do caixa.'
   service.step('synthetic_A',sid,message,proposal=base(message,observations=[obs(message,'network_selected','true')]))
   message='Nao apareceu pedido de senha na minha tela. Isso confirma defeito?'
   result=service.step('synthetic_A',sid,message,proposal=base(message,observations=[obs('Nao apareceu pedido de senha na minha tela.','symptom','Nao apareceu pedido de senha')],requests=[{'kind':'diagnosis','topic':'connectivity','entities':['a'],'quote':message}]))
   self.assertIn('não permitem confirmar',result['answer']);self.assertIn('Nao apareceu pedido de senha',result['answer']);self.assertNotIn('Como você já selecionou a rede',result['answer'])

class ActionScopeRegressions(unittest.TestCase):
 def test_cancel_action_in_connectivity_topic_remains_explicit(self):
  with tempfile.TemporaryDirectory() as tmp:
   service,sid=setup(tmp);message='Cancele meu cadastro e continue a orientar o Wi-Fi.'
   result=service.step('synthetic_A',sid,message,proposal=base(message,requests=[{'kind':'unsupported_action','action':'cancel_registration','topic':'connectivity','entities':['a'],'quote':message}]))
   self.assertIn('Nenhum cadastro foi cancelado',result['answer']);self.assertTrue(result['sources']);self.assertIn('no próprio aparelho',result['answer'])
 def test_unspecified_action_cannot_borrow_topic_as_permission(self):
  with tempfile.TemporaryDirectory() as tmp:
   service,sid=setup(tmp);message='Faça essa alteração na minha Smart.'
   result=service.step('synthetic_A',sid,message,proposal=base(message,requests=[{'kind':'unsupported_action','topic':'connectivity','entities':['a'],'quote':message}]))
   self.assertIn('apenas consultam dados fictícios',result['answer']);self.assertIn('nenhuma dessas ações foi realizada',result['answer'])

class MarketEvidenceRegressions(unittest.TestCase):
 def test_foreign_missing_source_explains_scope_without_erasing_outage(self):
  with tempfile.TemporaryDirectory() as tmp:
   service,sid=setup(tmp);service._core=lambda message,principal:('A fonte esta indisponivel nesta tentativa.',[],[])
   message='Minha operacao esta no Chile. Posso usar a antecipacao do tutorial brasileiro?'
   p=base(message,observations=[obs('Minha operacao esta no Chile.','country','Chile',scope='conversation',entity=None,incident='')],requests=[{'kind':'information','topic':'advance','entities':[],'quote':message}])
   result=service.step('synthetic_A',sid,message,proposal=p)
   self.assertIn('Getnet Brasil',result['answer']);self.assertEqual(result['sources'],[]);self.assertEqual(result['mode'],'scope_policy')
 def test_foreign_supported_source_not_replaced_by_universal_abstention(self):
  with tempfile.TemporaryDirectory() as tmp:
   service,sid=setup(tmp);service._core=lambda message,principal:('Informacao simulada com fonte pertinente.',['https://example.invalid/synthetic-chile'],[])
   message='Minha operacao esta no Chile. Explique antecipacao.'
   p=base(message,observations=[obs('Minha operacao esta no Chile.','country','Chile',scope='conversation',entity=None,incident='')],requests=[{'kind':'information','topic':'advance','entities':[],'quote':message}])
   result=service.step('synthetic_A',sid,message,proposal=p)
   self.assertNotIn('Informacao simulada',result['answer']);self.assertIn('Getnet Brasil',result['answer']);self.assertEqual(result['sources'],[])

class ConditionalProcedureRegressions(unittest.TestCase):
 def test_third_party_progress_is_acknowledged_conditionally(self):
  with tempfile.TemporaryDirectory() as tmp:
   service,sid=setup(tmp);message='Meu colega disse que selecionou a rede, mas nao confirmei. Como continuo?'
   p=base(message,observations=[obs(message,'network_selected','unknown',origin='third_party',status='uncertain')],requests=[{'kind':'next_step','topic':'connectivity','entities':['a'],'quote':message}])
   result=service.step('synthetic_A',sid,message,proposal=p)
   self.assertIn('não tenho confirmação direta',result['answer']);self.assertIn('apenas as que faltarem',result['answer']);self.assertTrue(result['sources']);self.assertFalse(values(result,'network_selected',status='asserted',origin='customer'))
 def test_known_negative_step_remains_useful_without_false_uncertainty(self):
  with tempfile.TemporaryDirectory() as tmp:
   service,sid=setup(tmp);message='Nao selecionei a rede na Smart do caixa. Como continuo?'
   p=base(message,observations=[obs(message,'network_selected','false',status='false')],requests=[{'kind':'next_step','topic':'connectivity','entities':['a'],'quote':message}])
   result=service.step('synthetic_A',sid,message,proposal=p)
   self.assertNotIn('não tenho confirmação direta',result['answer']);self.assertIn('Procurar Redes',result['answer'])
 def test_direct_progress_supersedes_uncertain_history_in_response(self):
  with tempfile.TemporaryDirectory() as tmp:
   service,sid=setup(tmp);message='Meu colega disse que selecionou a rede, mas nao confirmei.'
   service.step('synthetic_A',sid,message,proposal=base(message,observations=[obs(message,'network_selected','unknown',origin='third_party',status='uncertain')]))
   message='Agora selecionei a rede na Smart do caixa. Resuma e oriente.'
   p=base(message,observations=[obs(message,'network_selected','true')],requests=[{'kind':'summary','topic':'connectivity','entities':['a'],'quote':message},{'kind':'next_step','topic':'connectivity','entities':['a'],'quote':message}])
   result=service.step('synthetic_A',sid,message,proposal=p)
   self.assertIn('histórico, não é o estado atual',result['answer']);self.assertIn('Como você já selecionou',result['answer']);self.assertNotIn('não tenho confirmação direta',result['answer'])

class ObservationChronologyRegression(unittest.TestCase):
 def test_current_independent_hypothesis_is_not_labelled_superseded(self):
  with tempfile.TemporaryDirectory() as tmp:
   service,sid=setup(tmp)
   text='Meu colega acha que a Smart esta bloqueada. Nao apareceu pedido de senha na minha tela.'
   p=base(text,observations=[obs('Meu colega acha que a Smart esta bloqueada.','symptom','bloqueada',origin='third_party',status='uncertain'),obs('Nao apareceu pedido de senha na minha tela.','symptom','Nao apareceu pedido de senha')])
   result=service.step('synthetic_A',sid,text,proposal=p)
   self.assertIn('bloqueada',result['answer']);self.assertIn('não confirmado; origem third_party',result['answer']);self.assertNotIn('histórico, não é o estado atual',result['answer'])
