"""Explicit conservative accounting for one authorized batch, never default policy.

Confirmed costs and unknown provisions are distinct. Prior ledgers stay immutable;
all new reservations are serialized in the existing active ledger. No provider
charge is inferred. The ordinary Budget still blocks every uncertain reservation.
"""
import json,sqlite3
from hashlib import sha256
from decimal import Decimal
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timezone
from .agentic_client import Budget,BudgetExhausted,ModelUnavailable

COLUMNS='id,model,reserved,cost,status,created,input_tokens,output_tokens'
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'))
def digest(value):return sha256(encoded(value).encode()).hexdigest()
def rows(db):return [list(r) for r in db.execute('SELECT '+COLUMNS+' FROM calls ORDER BY id')]
def model_ceiling(ceiling,model):
 if isinstance(ceiling,dict):
  if model not in ceiling:raise ModelUnavailable('Model outside authorized campaign')
  return Decimal(ceiling[model])
 return ceiling

def totals(records,ceiling):
 confirmed=Decimal(0);uncertain=Decimal(0);unknown=0
 if [r[0] for r in records]!=list(range(1,len(records)+1)):raise ModelUnavailable('Missing budget records')
 for r in records:
  reserved=Decimal(r[2]);status=r[4]
  if not reserved.is_finite() or reserved<=0:raise ModelUnavailable('Invalid reservation')
  if status=='reserved' and r[3] is None:uncertain+=max(reserved,model_ceiling(ceiling,r[1]));unknown+=1
  elif status=='billed' and r[3] is not None:
   cost=Decimal(r[3])
   if not cost.is_finite() or not 0<=cost<=reserved:raise ModelUnavailable('Invalid confirmed cost')
   confirmed+=cost
  else:raise ModelUnavailable('Unexpected or invalid billing remains blocked')
 return {'calls':len(records),'confirmed':confirmed,'provisioned':uncertain,'uncertain_calls':unknown}
def validate_policy(policy):
 common={'version','authorization','global_max_calls','global_cost_cap','prior_ledgers'}
 version=policy.get('version')
 if not policy.get('authorization'):raise ValueError('Explicit supported policy required')
 if version==1:
  if set(policy)!=common|{'model','uncertain_ceiling'} or policy['model']!='openai/gpt-5-mini':raise ValueError('Invalid provision policy')
  call_limit=190;cost_limit=Decimal('1')
  ceiling=Decimal(policy['uncertain_ceiling'])
  if not ceiling.is_finite() or ceiling<Decimal('.02'):raise ValueError('Invalid uncertainty ceiling')
 elif version==2:
  original={'openai/gpt-5-mini':'0.02','google/gemini-2.5-flash-lite':'0.01'}
  # Existing ledgers keep their original policy. The alternative judge requires
  # an explicit, journaled policy change; it never inherits another model's ID.
  alternative={**original,'openai/gpt-4.1-mini':'0.01'}
  if set(policy)!=common|{'models'} or policy['models'] not in (original,alternative):raise ValueError('Invalid authorized model envelope')
  call_limit=1599;cost_limit=Decimal('27.10');ceiling=policy['models']
 else:raise ValueError('Unsupported policy version')
 if type(policy['global_max_calls']) is not int or not 1<=policy['global_max_calls']<=call_limit:raise ValueError('Global call cap')
 cap=Decimal(policy['global_cost_cap'])
 largest=max(map(Decimal,ceiling.values())) if isinstance(ceiling,dict) else ceiling
 if not cap.is_finite() or not 0<cap<=cost_limit or largest>cap:raise ValueError('Global monetary cap')
 if not isinstance(policy['prior_ledgers'],list):raise ValueError('Prior ledger list required')
 return cap,ceiling

def prior_totals(path,policy):
 _,ceiling=validate_policy(policy);total={'calls':0,'confirmed':Decimal(0),'provisioned':Decimal(0),'uncertain_calls':0};seen={path.resolve()}
 for item in policy['prior_ledgers']:
  name=item['file'];prior=path.parent/name
  if Path(name).name!=name or prior.resolve().parent!=path.parent.resolve() or prior.resolve() in seen:raise ModelUnavailable('Duplicate or invalid prior ledger')
  seen.add(prior.resolve())
  if sha256(prior.read_bytes()).hexdigest()!=item['sha256']:raise ModelUnavailable('Prior ledger changed')
  with sqlite3.connect(prior.as_uri()+'?mode=ro',uri=True) as db:part=totals(rows(db),ceiling)
  for key in total:total[key]+=part[key]
 return total

def enable_provisioning(path,*,max_calls,max_cost,policy):
 """One explicit transition, preserving all call rows and their status/cost."""
 base=Budget(path,max_calls=max_calls,max_cost=max_cost)
 validate_policy(policy);prior_totals(base.path,policy)
 with base.db() as db:
  if db.execute("SELECT name FROM sqlite_master WHERE name='provision_policy'").fetchone():raise ModelUnavailable('Policy already installed; do not reset')
  totals(rows(db),Decimal(policy['uncertain_ceiling']))
  db.execute('CREATE TABLE provision_policy(policy TEXT NOT NULL)')
  db.execute('INSERT INTO provision_policy VALUES(?)',(encoded(policy),))
  db.execute('CREATE TABLE provision_audit(seq INTEGER PRIMARY KEY, event TEXT NOT NULL, previous TEXT NOT NULL, digest TEXT NOT NULL)')
  event=encoded({'kind':'explicit_opt_in','at':datetime.now(timezone.utc).isoformat(),'rows_sha256':digest(rows(db)),'policy_sha256':digest(policy)})
  db.execute('INSERT INTO provision_audit VALUES(1,?,?,?)',(event,'',sha256(event.encode()).hexdigest()))

class ProvisionedBudget(Budget):
 def __init__(self,path,*,max_calls,max_cost,policy,allow_uncertain=False):
  if allow_uncertain is not True:raise ValueError('Explicit uncertain provisioning opt-in required')
  self.policy=json.loads(encoded(policy));self.global_cap,self.ceiling=validate_policy(self.policy)
  super().__init__(path,max_calls=max_calls,max_cost=max_cost)
 def _validate(self,db):
  super()._validate(db)
  if db.execute('SELECT policy FROM provision_policy').fetchall()!=[(encoded(self.policy),)]:raise ModelUnavailable('Provision policy changed')
  prior_totals(self.path,self.policy)
  events=db.execute('SELECT seq,event,previous,digest FROM provision_audit ORDER BY seq').fetchall();previous=''
  if not events:raise ModelUnavailable('Missing budget audit')
  for expected,(seq,event,prev,stamp) in enumerate(events,1):
   if seq!=expected or prev!=previous or sha256((prev+event).encode()).hexdigest()!=stamp:raise ModelUnavailable('Budget audit changed')
   previous=stamp
  latest=json.loads(events[-1][1])
  if latest['rows_sha256']!=digest(rows(db)) or latest['policy_sha256']!=digest(self.policy):raise ModelUnavailable('Unjournaled budget mutation')
 @contextmanager
 def db(self,*,validate=True):
  with super().db(validate=validate) as db:
   before=rows(db)
   yield db
   after=rows(db)
   if after!=before:
    old={r[0]:r for r in before};changed=[r for r in after if old.get(r[0])!=r]
    if len(changed)!=1 or len(after) not in (len(before),len(before)+1):raise ModelUnavailable('Unexpected budget mutation')
    seq,previous=db.execute('SELECT seq,digest FROM provision_audit ORDER BY seq DESC LIMIT 1').fetchone()
    event=encoded({'kind':'reserve' if len(after)>len(before) else 'provider_reconciliation','at':datetime.now(timezone.utc).isoformat(),'call':changed[0],'rows_sha256':digest(after),'policy_sha256':digest(self.policy)})
    db.execute('INSERT INTO provision_audit VALUES(?,?,?,?)',(seq+1,event,previous,sha256((previous+event).encode()).hexdigest()))
 def _summary(self,db):
  result=prior_totals(self.path,self.policy);local=totals(rows(db),self.ceiling)
  for key in result:result[key]+=local[key]
  result['conservative_total']=result['confirmed']+result['provisioned']
  result['conservative_remaining']=self.global_cap-result['conservative_total']
  return result,local
 def summary(self):
  with self.db() as db:return self._summary(db)[0]
 def reserve(self,model,amount):
  amount=Decimal(str(amount))
  ceiling=model_ceiling(self.ceiling,model)
  if (self.policy['version']==1 and model!=self.policy['model']) or not amount.is_finite() or not 0<amount<=ceiling:raise ModelUnavailable('Outside provisioned request envelope')
  with self.db() as db:
   total,local=self._summary(db)
   if total['calls']>=self.policy['global_max_calls'] or local['calls']>=self.max_calls or total['conservative_total']+ceiling>self.global_cap or local['confirmed']+local['provisioned']+ceiling>self.max_cost:raise BudgetExhausted('Global conservative budget exhausted')
   return db.execute('INSERT INTO calls(model,reserved,status,created) VALUES(?,?,?,?)',(model,str(ceiling),'reserved',datetime.now(timezone.utc).isoformat())).lastrowid
