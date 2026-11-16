"""Conservative, server-owned constraints and literal goal focus. No tool selection."""
import re
from app.intents import normalize

# Closed explicit prohibitions only: never classify arbitrary model text as a
# constraint to excuse an omitted request.
CONSTRAINTS = (
 r'\b(?:(?:n[aã]o\s+fa[cç]a\s+altera[cç][oõ]es)|(?:sem|without)\s+(?:mudar|alterar|modificar|changing|modifying)\s+(?:(?:o|a|meu|minha|my|the)\s+)*(?:contrato|plano|servi[cç]o|contract|plan|service))\b',
 r"\b(?:sem|n[aã]o|do not|don't|never|nunca|without)\s+(?:consultar|consulte|acessar|acesse|consult|check|access|checking|consulting|accessing)\s+(?:(?:os\s+)?dados\s+(?:da|de)\s+)?(?:(?:a|as|os|minha|minhas|meu|meus|my|the)\s+)*(?:conta|vendas|receb[ií]veis|account|sales|receivables)\b",
 r'\b(?:Se s[oó] houver evid[eê]ncia para um dos dois,\s*n[aã]o conclua o outro por analogia|sem deduzir um recurso do outro)\b',
)
CONSTRAINTS=(*CONSTRAINTS,r'^(?:Esque[cç]a|Forget)\s+[^.;!?\n]{1,100}\s+(?:por enquanto|for now)[.!?]\s*(?=Agora|Now)')
COMPILED=tuple(re.compile(p,re.I) for p in CONSTRAINTS)
def constraints(text):
 return [{'text':m.group(),'kind':('no_receivables_lookup' if re.search(r'\b(?:receb[ií]veis|receivables|vendas|sales)\b',m.group(),re.I) else 'no_account_lookup') if i==1 else 'no_changes' if i==0 else 'evidence_only' if i==2 else 'topic_reset',
          'start':m.start(),'end':m.end()} for i,p in enumerate(COMPILED) for m in p.finditer(text)]
def forbids_support(text,capability=None):
 # A ban on financial data does not ban an explicitly requested terminal read.
 # Account-wide bans still block every Support capability; no model permission.
 return any(c['kind']=='no_account_lookup' or
            (c['kind']=='no_receivables_lookup' and capability!='support_terminal')
            for c in constraints(text))
ATTRS={'Wi-Fi':r'\bwi[\s-]?fi\b','eSIM':r'\besim\b','Bluetooth':r'\bbluetooth\b',
       'NFC':r'\bnfc\b','4G':r'\b4g\b','3G':r'\b3g\b'}
def attributes(text):
 return {name for name,p in ATTRS.items() if re.search(p,normalize(text),re.I)}
def target(goal):
 return goal.focus or goal.request
def validate_focus(goals):
 pairs=[(normalize(g.request),normalize(g.focus or '')) for g in goals]
 if len(set(pairs))!=len(pairs):raise ValueError('Duplicate goal')
 for g in goals:
  if g.focus and g.focus not in g.request:raise ValueError('Invented focus')
  if g.focus and not re.fullmatch(r'\w+(?:-\w+)?',g.focus):raise ValueError('Focus must be one atomic label')
 for request in {g.request for g in goals}:
  group=[g for g in goals if g.request==request]
  if len(group)>1 and any(not g.focus for g in group):raise ValueError('Ambiguous duplicate goal')
  if any(g.focus for g in group):
   if len(group)==1 and group[0].focus!=request:raise ValueError('Unproven single focus')
   requested=attributes(request)
   represented=set().union(*(attributes(target(g)) for g in group))
   if requested-represented:raise ValueError('Omitted requested attribute')
   marked=[False]*len(request);starts=[]
   for g in group:
    pos=request.find(g.focus);starts.append(pos)
    marked[pos:pos+len(g.focus)]=[True]*len(g.focus)
   for c in constraints(request):marked[c['start']:c['end']]=[True]*(c['end']-c['start'])
   prefix=normalize(request[:min(starts)])
   framing={'a','o','da','do','get','smart','classica','getnet','brasil','brazil','maquininha','terminal',
            'sobre','confirme','confirma','confirmei','separadamente','se','aceita','possui','tem','does','the',
            'support','supports','has','confirm','separately','whether','suporta','e','and','qual','quais'}
   if any(w not in framing for w in re.findall(r'\w+',prefix)):raise ValueError('Unproven focus framing')
   tail=''.join(ch if not marked[i] else ' ' for i,ch in enumerate(request) if i>=min(starts))
   connectors={'diga','separadamente','ha','e','and','ou','or','se','if','aceita','possui','tem','has','supports','support','does','it','the'}
   if any(w not in connectors for w in re.findall(r'\w+',normalize(tail))):raise ValueError('Uncovered focus tail')
   for i,g in enumerate(group):
    for other in group[i+1:]:
     if g.focus in other.focus or other.focus in g.focus:raise ValueError('Overlapping focus')
def missing_attributes(goal,contents):
 text=' '.join(contents)
 missing=attributes(target(goal))-attributes(text)
 if goal.focus and normalize(goal.focus) not in normalize(text) and not (attributes(goal.focus) and not (attributes(goal.focus)-attributes(text))):
  missing.add(goal.focus)
 return missing
