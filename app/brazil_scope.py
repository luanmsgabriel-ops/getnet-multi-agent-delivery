
"""Fronteira de produto: atendimento Getnet Brasil, por cláusula e por entidade.

Esta política não usa texto externo como autorização. País do estabelecimento é
distinto da origem do cliente/cartão. Casos geográficos ambíguos pedem confirmação.
"""
from dataclasses import dataclass
import re
from app.intents import normalize

REDIRECT_BR = 'Meu atendimento é dedicado à Getnet Brasil; não atendo esse assunto. Posso ajudar com produtos, serviços ou suporte da Getnet Brasil.'
CLARIFY_BR = 'Essa dúvida se refere a uma operação da Getnet no Brasil? Atendo somente Getnet Brasil.'
COUNTRY_ALIASES = {
    'brasil':'BR','brazil':'BR','br':'BR',
    'chile':'CL','chilena':'CL','chileno':'CL','chilean':'CL',
    'argentina':'AR','argentino':'AR','argentine':'AR','mexico':'MX','mexicana':'MX','mexicano':'MX',
    'espanha':'ES','spain':'ES','espana':'ES','portugal':'PT','uruguai':'UY','uruguay':'UY',
    'colombia':'CO','peru':'PE','equador':'EC','ecuador':'EC','bolivia':'BO','paraguai':'PY','paraguay':'PY',
    'canada':'CA','canadian':'CA','canadense':'CA','canadenses':'CA','eua':'US','usa':'US',
    'estados unidos':'US','united states':'US','alemanha':'DE','germany':'DE',
    'franca':'FR','france':'FR','japao':'JP','japan':'JP','australia':'AU',
    'italia':'IT','italy':'IT','angola':'AO','mocambique':'MZ',
    'europa':'EU','europe':'EU','america latina':'LATAM','latin america':'LATAM',
}
COUNTRIES = re.compile(r'\b(?:'+ '|'.join(sorted(map(re.escape,COUNTRY_ALIASES),key=len,reverse=True))+r')\b')
BUSINESS = re.compile(r'\b(?:getnet|pix|crediario|maquininhas?|maquinas?|maq|terminais|terminal|recebiveis|saldo|antecip\w*|classica|smart|a920|dx8000|pax|pos|adquirencia|pagamentos?|payment|payments|pay|whatsapp|transac\w*|transactions?|cartoes|cartao|cards?|vendas?|sales|receivables|balance|wi.?fi|internet|link|tef|conta|account|cadastro|pacote|servico|dinheiro|senha|password|passphrase|autenticacao|authentication|parcelas?|taxas?|fees|prices|precos?|aluguel)\b')
CONTINUATION = re.compile(r'\b(?:aparelho|device|country|pais|modelo|model|conect\w*|rede|network|imprim\w*|print\w*|reinic\w*|restart\w*|selecionei|selected|menu|funcion\w*|resolvid\w*|voltou|entrada|caixa|balcao|estoque|checkout|counter|corrig\w*|retir\w*|resum\w*|summary|confirm\w*|continu\w*|retom\w*|proximo passo|next step|dela|dele|isso|daquela|daquele)\b')
OUTSIDE = re.compile(r'\b(?:clima|weather|forecast|temperatura|chover|chuva|python|dns|futebol|receita|horoscopo|programac\w*|programming|algoritmos?|poema|piada|politica|eleic\w*|filme|novela|capital|fotos?|musica)\b')
GLOBAL_REQUEST = re.compile(r'\b(?:global|worldwide|internacional|international|(?:quais|quantos) paises|(?:which|how many) countries|presenca|presence|america latina|latin america)\b')
@dataclass(frozen=True)
class Market:
    value: str  # BR, OUT, UNKNOWN, NONE
    countries: tuple[str,...] = ()

def market_of(message):
    # Preserve the subject pronoun before accent folding: nós is not locative nos.
    text=normalize(re.sub(r'\bnós\b','we',message,flags=re.I))
    # A quotation/hypothesis is not a declaration of the establishment's location.
    if re.search(r'\b(?:manual|documento|fonte|exemplo|hipotese|se estivesse|if i were)\b',text):
        text=re.sub(r"['\"][^'\"]*['\"]",'',text)
    # The nationality/location of a customer/card is not the establishment market.
    text=re.sub(r'\b(?:clientes?|customers?|cartoes|cartao|cards?|turistas?)\s+(?:(?:e|is|sao|are)\s+)?(?:estrangeiros?|internacionais?|foreign|international)\b',' cliente estrangeiro ',text)
    ignored=[]
    for m in COUNTRIES.finditer(text):
        before=text[max(0,m.start()-55):m.start()]
        if re.search(r'\b(?:regra|regras|escopo|policy|rule|rules|scope)\s+(?:do |de |da )?$',before):
            ignored.append(m.span());continue
        # A country attached to customer/card origin remains informational, not merchant geography.
        if re.search(r'\b(?:cliente|customer|cartao|card|turista)\s+(?:(?:de|do|da|dos|das|from|no|na|in|is|e)\s+){0,3}$',before) or re.search(r'\b(?:cartao|card)\b.{0,35}\b(?:emitido|issued|origem|origin)\s+(?:(?:no|na|em|in|from|the)\s+)*$',before):
            ignored.append(m.span())
    values=[];negated=False
    for m in COUNTRIES.finditer(text):
        if m.span() in ignored:continue
        if m.group()=='usa' and not re.search(r'\bUSA\b|\b(?:nos|no|em|in)\s+usa\b',message,re.I if ' usa' not in text else 0):continue
        prefix=re.split(r'[.;!?]|\b(?:mas|but|porem|however)\b',text[:m.start()])[-1]
        if re.search(r'\b(?:nao|not|never|nunca|nem)\b',prefix) and not re.search(r'\b(?:nao (?:conecta|imprime|funciona)|not (?:connect|print|working))\b',prefix):
            negated=True;continue
        suffix=text[m.end():m.end()+55]
        if re.match(r'\s+nao (?:e|era|foi) (?:o |a )?(?:local|pais|mercado|operacao)',suffix):
            negated=True;continue
        value=COUNTRY_ALIASES[m.group()]
        if value not in values:values.append(value)
    if re.search(r'\b(?:nao sei|desconheco|incerto|uncertain|unknown|not sure)\b.{0,35}\b(?:pais|country|onde|where|brasil|brazil)\b',text):
        return Market('UNKNOWN',tuple(values))
    if re.search(r'\b(?:fora do brasil|outside (?:of )?brazil|outro pais|other countr|exterior|abroad)\w*\b',text):
        if not re.search(r'\b(?:nao|not)\b.{0,20}(?:fora|outside|exterior|abroad)',text):
            return Market('OUT',tuple(values))
    if len(values)>1:return Market('UNKNOWN',tuple(values))
    if values:return Market('BR' if values==['BR'] else 'OUT',tuple(values))
    if negated:return Market('UNKNOWN')
    # Global support/presence is outside the customer-service boundary.
    if GLOBAL_REQUEST.search(text) and not re.search(r'\b(?:cartao|cartoes|card|cards|cliente|customer|dcc|conversao|conversion)\b',text):
        return Market('OUT')
    from app.rag.scope import unsupported_location
    geographic=re.sub(r'\bpesquise na web\s*:', '',text)
    if unsupported_location(geographic) and (BUSINESS.search(geographic) or re.fullmatch(r'(?:em|no|na|in|at)\s+\w+',geographic)):return Market('UNKNOWN')
    return Market('NONE')

def clauses(message):
    # Split new requests/subjects; keep lists of products and installment amounts intact.
    pattern=r'[;?!\n]+|\.(?=\s|$)|\s+(?:e|and|mas|but)\s+(?=(?:(?:a|o|as|os|the)\s+)?(?:qual|como|what|how|quem|who|vai|meu\w*\b|minh\w*\b|my\b|explique|quanto|converta|calcule|clima|weather|euro\b|cota[çc][ãa]o|d[óo]lar|python|dns|pix\b|link\b|cartao\b|getnet\b|no brasil|no chile|a920\b|dx8000\b))'
    return [p.strip(' ,') for p in re.split(pattern,message,flags=re.I) if p.strip(' ,')]

def known_country(state,ref=None):
    boundary=state.get('service_boundary',{})
    restriction=boundary.get('entities',{}).get(ref) if ref else None
    if restriction is not None:return restriction
    fact=next((f for f in state.get('facts',{}).values() if f.get('entity')==ref and f.get('field')=='country'),None) if ref else None
    if fact:
        if fact.get('origin')!='customer' or fact.get('status') not in ('asserted','corrected'):return 'UNKNOWN'
        return 'BR' if normalize(fact['value']) in ('brasil','brazil','br') else 'OUT'
    if boundary.get('conversation') is not None:return boundary['conversation']
    fact=state.get('context',{}).get('country')
    if not fact:return 'BR'
    if fact.get('origin')!='customer' or fact.get('status') not in ('asserted','corrected'):return 'UNKNOWN'
    return 'BR' if normalize(fact['value']) in ('brasil','brazil','br') else 'OUT'


def device_alias(message):
    # Non-actionable routing label only: no product, incident or authorization fact.
    text=normalize(message)
    m=re.search(r'\b((?:(?:a920|dx8000|smart|classica|terminal|maquininha|aparelho)\s+)?(?:do|da)\s+(?:caixa|entrada|balcao|estoque|recepcao))\b',text)
    return m.group(1) if m else None

def referenced_entities(state,message,*,fallback=True):
    text=normalize(message);found=[]
    labels={ref:normalize(d['label']) for ref,d in state.get('devices',{}).items()}
    # Distinctive literal suffix (entrada/caixa/model) only if it has one owner.
    ignored={'a','o','do','da','de','the','at','no','na','aparelho','maquininha','terminal'}
    for ref,label in labels.items():
        words=set(re.findall(r'\w+',label))-ignored
        distinctive={w for w in words if sum(w in set(re.findall(r'\w+',v)) for v in labels.values())==1}
        if label in text or any(re.search(r'\b'+re.escape(w)+r'\b',text) for w in distinctive):found.append(ref)
    if found:return found
    if not fallback or device_alias(message):return []
    return list(state.get('focus',[]))

def remember_boundary(state,message,market,*,allow_global=True):
    """Only a routing restriction, never a tool authorization or an inferred device fact."""
    from copy import deepcopy
    after=deepcopy(state)
    refs=referenced_entities(state,message,fallback=allow_global)
    boundary=after.setdefault('service_boundary',{'entities':{}})
    alias=device_alias(message)
    if alias:boundary.setdefault('mentions',{})[alias]=market
    if not refs and not allow_global:return after
    if market in ('OUT','UNKNOWN'):
        for fact in after.get('facts',{}).values():
            if fact.get('field')=='country' and (not refs or fact.get('entity') in refs):
                fact['status']='unknown'  # Previous country no longer actionable; history retained.
    if len(refs)==1:boundary['entities'][refs[0]]=market
    elif not refs:boundary['conversation']=market
    else:boundary['conversation']='UNKNOWN'
    return after

def scoped_parts(message, *, state=None):
    """Partition explicit market changes; inherit current market within the message."""
    state=state or {};explicit_refs=referenced_entities(state,message)
    aliases=state.get('service_boundary',{}).get('mentions',{})
    alias=device_alias(message)
    matches={value for label,value in aliases.items() if alias and (alias==label or label.endswith(alias))}

    countries={known_country(state,r) for r in explicit_refs}
    default=next(iter(countries)) if len(countries)==1 else 'UNKNOWN' if len(countries)>1 else known_country(state)
    if len(matches)==1:default=next(iter(matches))
    pieces=clauses(message)
    # An explicit comparison has separate market obligations; a contract with an
    # unclear referent does not qualify for this decomposition.
    if len(pieces)==1 and re.match(r'^(?:compare|comparar|compare as|compare os)\b',normalize(message)):
        split=re.split(r'\s+com\s+(?:as|os)\s+(?:da|do|de)\s+(?=Getnet\b)',message,flags=re.I)
        if len(split)==2 and market_of(split[0]).value=='BR' and market_of(split[1]).value=='OUT':pieces=[re.sub(r'^compare\b','Explique',split[0],flags=re.I),split[1]]
    qualifiers=[]
    for part in pieces:
        if not BUSINESS.search(normalize(part)) and re.fullmatch(r'(?:(?:em|no|na|nos|nas|in|at)\s+)?[\w\s-]+',normalize(part)):
            m=market_of(part)
            if m.value!='NONE' and (COUNTRIES.search(normalize(part)) or len(part.split())<=3):qualifiers.append(m.value)
    # A declaração autônoma de país desconhecido qualifica também o sintoma
    # anterior. Não promover a primeira oração ao BR antes de pedir o país.
    for part in pieces:
        plain=normalize(part)
        if (market_of(part).value=='UNKNOWN' and not BUSINESS.search(plain)
                and not device_alias(part) and not referenced_entities(state,part,fallback=False)
                and re.search(r'\b(?:nao sei|desconheco|incerto|uncertain|unknown|not sure)\b.{0,35}\b(?:pais|country|onde|where)\b',plain)):
            qualifiers.append('UNKNOWN')
    if len(set(qualifiers))==1:default=qualifiers[0]
    affirmative={market_of(p).value for p in pieces if market_of(p).countries and market_of(p).value in ('BR','OUT')}
    parts=[];active=default
    for part in pieces:
        # A denied alternative is not an unresolved operational country when a
        # later clause explicitly provides the location. It has no service obligation.
        if market_of(part).value=='UNKNOWN' and not market_of(part).countries and re.search(r'\b(?:nao|not)\b',normalize(part)) and len(affirmative)==1:
            continue

        market=market_of(part)
        refs=referenced_entities(state,part,fallback=False)
        part_alias=device_alias(part)
        mention={value for label,value in aliases.items() if part_alias and (part_alias==label or label.endswith(part_alias))}
        if market.value!='NONE':active=market.value
        elif refs:
            values={known_country(state,ref) for ref in refs}
            active=next(iter(values)) if len(values)==1 else 'UNKNOWN'
        elif len(mention)==1:active=next(iter(mention))
        parts.append((part,active))
    return parts

