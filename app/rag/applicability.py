"""Reviewed applicability metadata, not facts inferred from keyword presence."""
import json,re
from pathlib import Path
from hashlib import sha256
from app.intents import normalize
from .core import tokens

SERVICE_NAMES={
 'crediario':r'\bcrediario\b',
 'anticipation':r'\b(?:antecip\w*|advance|advancement)\b',
 'pix':r'\bpix\b',
 'link':r'\b(?:link|whatsapp)\b',
 'dcc':r'\b(?:dcc|conversor|conversao de moedas|currency conversion|currency converter)\b',
}
PRODUCT_PATTERN = r'\b(?:get\s*)?(smart|classica|a920|dx8000)\b'


def request_relations(question):
    """Conservative clause relations, not a general semantic parser.

    Force is anchored: a question mark/interrogative head or informational
    directive. A capability verb or 'como' inside a declaration is not force.
    Relations annotate the intact input; retrieval still embeds it unchanged.
    Unsupported syntax stays reference, rather than inventing a demand.
    """
    interrogative = r'^(?:e\s+|and\s+)?(?:como|qual|quais|quanto|quantos|quando|onde|por que|what|which|how|when|where)\b'
    directive = r'^(?:e\s+|and\s+)?(?:explique|compare|descreva|informe|explique-me|explain|describe|compare|quero\s+(?:saber|entender)|gostaria\s+de\s+saber)\b'
    decline = r'^(?:nao|not|do not|don.t)\s+(?:quero|desejo|want|explique|compare|descreva|explain|describe)\b'
    rows = []
    for match in re.finditer(r'[^.!?;\n]+(?:[.!?;\n]|$)', question):
        original = match.group().strip()
        text = normalize(original)
        is_question = original.endswith('?')
        head = text
        # A labeled directive retains its force; labels are not request entities.
        if not (re.search(interrogative, head) or re.search(directive, head)) and ':' in head:
            tail = head.rsplit(':', 1)[1].strip()
            if re.search(directive, tail):head = tail
        kind = ('exclusion' if not is_question and re.search(decline, head) else
                'request' if is_question or re.search(interrogative, head) or re.search(directive, head) else
                'reference')
        excluded_products = set()
        if kind == 'exclusion':
            excluded_products.update(re.findall(PRODUCT_PATTERN, head))
        elif kind in ('request','reference') and not is_question:
            # Nominal exclusion ('not the X'), not negation of a predicate
            # ('X does not print'). A preceding product declaration can also
            # bind a later question. Interrogative negation remains a question.
            excluded_products.update(re.findall(
                r'\b(?:nao|not)\s+(?:(?:a|o|the)\s+)?(?:get\s*)?(smart|classica|a920|dx8000)\b', head))
        rows.append({'kind':kind,'text':head,'excluded_products':excluded_products})
    return tuple(rows)


def requested_products(question):
    """Explicit request targets, with conservative fallback on ambiguity.

    Legacy synthetic queries must not use this discourse annotation. The
    canonical applicability layer receives the intact original question.
    """
    all_products=set(re.findall(PRODUCT_PATTERN, normalize(question)))
    requested=set(); excluded=set()
    for relation in request_relations(question):
        excluded.update(relation['excluded_products'])
        if relation['kind']=='request':
            requested.update(re.findall(PRODUCT_PATTERN, relation['text']))
    return (requested-excluded) or (all_products-excluded) or all_products


class CorpusScopes:
 def __init__(self,index,path=None):
  data=json.loads(Path(path or Path(__file__).with_name('corpus_scopes.json')).read_text('utf-8'))
  if data.get('version')!=1 or data.get('reviewed') is not True or not isinstance(data.get('blocks'),list):
   raise ValueError('Invalid reviewed scope manifest')
  self.rows={}
  for b in data['blocks']:
   key=(b['source'],b['title'],b['text_sha256'],b['raw_sha256'])
   if key in self.rows and self.rows[key]!=b:raise ValueError('Conflicting scope metadata')
   self.rows[key]=b
  # Fail closed on corpus changes; a title/URL alone does not approve new text.
  for e in index.entries:
   if self.metadata(e) is None:raise ValueError('Unreviewed corpus applicability')
 def metadata(self,e):
  return self.rows.get((e['source'],e['title'],sha256(e['text'].encode()).hexdigest(),e.get('raw_sha256')))
 def compatible(self,question,e):
  b=self.metadata(e)
  if b is None or b['market']!='BR':return False
  from app.request_plan import without_declined_requests
  text=normalize(without_declined_requests(question))
  products=requested_products(question)
  source_products=set(b['products'])
  if products and source_products and not products&source_products:return False
  services={name for name,pattern in SERVICE_NAMES.items() if re.search(pattern,text)}
  source_services=set(b['services'])
  # A service mentioned incidentally in a different service's document is not
  # evidence of general applicability. Multi-service questions retain each side.
  if services and not services&source_services:return False
  if products and not services and not source_products and not source_services&{'terminal','terminal_connectivity'}:
   return False
  years=set(re.findall(r'\b(?:19|20)\d{2}\b',text))
  if not years<=tokens(e['title']+' '+e['text']):return False
  code=re.search(r'ADQ\s+(\d+)[- ](\d+)',e['title'],re.I)
  if code and not {'adq',code[1],code[2]}<=tokens(question):return False
  return True

 @staticmethod
 def validated_services(question,labels):
    """Validate immutable caller-supplied ranking demands, never infer them.

    Alias presence is necessary provenance, not request intent or factual
    support. The explicit goal planner owns that relation. Labels cannot
    alter eligibility or the original embedded question.
    """
    if type(labels) is not tuple or any(type(label) is not str for label in labels):
      raise ValueError('requested_services must be a tuple of service labels')
    if len(labels)>3 or len(set(labels))!=len(labels):
      raise ValueError('requested_services must contain at most three unique labels')
    text=normalize(question)
    for label in labels:
      if label not in SERVICE_NAMES or not re.search(SERVICE_NAMES[label],text):
        raise ValueError('Requested service is unknown or absent from goal')
    return labels

 def retrieval_facets(self,question,e,requested_services=()):
    """Explicit validated ranking labels intersect reviewed source metadata."""
    demands=self.validated_services(question,requested_services)
    b=self.metadata(e)
    if b is None:return ()
    return tuple(label for label in demands if label in b['services']) if len(demands)>1 else ()


validated_services = CorpusScopes.validated_services
