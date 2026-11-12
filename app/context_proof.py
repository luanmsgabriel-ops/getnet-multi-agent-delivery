"""Verificações locais de proveniência/polaridade: complementam a extração semântica.
Não reconhecem toda linguagem; item sem suporte permanece não acionável.
"""
import re,unicodedata

def norm(s):return ''.join(c for c in unicodedata.normalize('NFKD',s.lower()) if not unicodedata.combining(c))
REPORTED=re.compile(r'\b(?:manual|tutorial|documento|exemplo|hipotese)\b|(?:colega|cliente|terceiro).{0,25}(?:acha|disse|diz|pensa|afirma)|segundo.{0,20}(?:colega|manual)')
CUES={'restart_attempted':r'reinici|restart|reboot','network_selected':r'selecion|escolh.*rede','network_menu_open':r'abri|abert|acessei', 'password_entered_on_device':r'digit|inform|inseri|coloquei', 'credential_correct':r'corret|certa', 'network_ok':r'rede.*funcion|internet.*funcion|(?:network|internet).*(?:work|online|operational)', 'connected':r'conect|conex|internet|offline|online', 'printing_ok':r'imprim|impress', 'resolved':r'resolv|voltou.*funcion|problema.*acab'}
NEGATIVE=re.compile(r'\b(?:nao|nunca|nem|sem|ainda nao|not|never|without)\b|perdeu|desconect|offline')
def units(quote):return [norm(x) for x in re.split(r'[.;!?:]|\b(?:mas|porém|porem|porque|pois|embora|but|however|although|because)\b|,|\s+(?:e|and)\s+',quote,flags=re.I) if x.strip()]
def evidence_guard(observation):
    if observation.origin!='customer' or observation.status in ('unknown','uncertain','retracted'):return
    q=norm(observation.quote)
    if observation.field in CUES:
        clauses=[c for c in units(observation.quote) if re.search(CUES[observation.field],c)]
        if not clauses:raise ValueError('field_not_evidenced')
        possible=[]
        for c in clauses:
            if REPORTED.search(c):continue
            if re.search(r'\b(?:se|caso|talvez|acho|parece|suponha|provavelmente|possivelmente|aparentemente|presumo|acredito|suspeito)\b|nao (?:tenho certeza|sei|consigo confirmar)|pelo que (?:lembro|recordo)',c):continue
            if re.search(r'\b(?:marque|registre|considere|anote|finja|diga)\b',c):continue
            possible.append('false' if NEGATIVE.search(c) else 'true')
        if observation.value not in possible:raise ValueError('polarity_or_origin_not_evidenced')
    elif observation.field in ('country','product','connection'):
        # Validate the assertion's own categorical predicate, not an unrelated
        # negative symptom in the same utterance (e.g. 'A920 não imprime').
        value=norm(observation.value)
        clauses=[c for c in units(observation.quote) if value and value in c]
        if not clauses:raise ValueError('categorical_value_not_evidenced')
        possible=[]
        for clause in clauses:
            if REPORTED.search(clause):continue
            if re.search(r'\b(?:talvez|acho|parece|nao sei|nao tenho certeza|maybe|perhaps|unsure)\b',clause):continue
            if re.search(r'\b(?:ou|or)\b',clause):continue
            at=clause.find(value);prefix=clause[:at]
            negative=bool(re.search(r'\b(?:nao|not|never|nem)\s+(?:(?:estou|estamos|fica|e|sou|uso|usamos|utilizo|tenho|possuo|is|in|am|are|use|using|have|at|located|based|do|does|mais|no|na|em|a|o|do|da|loja|operacao|store|operation|it|we|i)\s+){0,7}$',prefix))
            possible.append('false' if negative else 'true')
        wanted='false' if observation.status=='false' else 'true'
        if wanted not in possible:raise ValueError('categorical_polarity_not_evidenced')
    elif REPORTED.search(q) and observation.status in ('asserted','corrected'):
        raise ValueError('reported_cannot_be_direct')

def identity_guard(quote):
    q=norm(quote)
    if REPORTED.search(q) and not re.search(r'\b(?:minha|meu)\s+(?:smart|classica|maquininha|terminal|aparelho)\b|^(?:eu )?(?:tenho|possuimos|acompanho)\b',q):raise ValueError('reported_identity')


def explicit_categorical(message, field):
    """Recuperação limitada de declaração direta, jamais hipótese ou terceiro.

    Usada só após rejeitar uma categoria de proposta, com entidade já inequívoca.
    Ausência ou conflito retorna None e exige esclarecimento.
    """
    patterns={
        'country':r'\b(?:eu estou|estou|estamos|i am|we are)\s+(?:no|na|em|in)\s+([\w-]+)',
        'product':r'\b(?:meu (?:terminal|aparelho|modelo)|o modelo|my (?:terminal|device|model))\s+(?:e|is)\s+([a-z]+[0-9]+[a-z0-9-]*|smart|classica)',
    }
    if field not in patterns:return None
    found=[]
    # Keep the exact evidence substring for provenance, while matching folded text.
    for clause in re.split(r'[;.!?]',message):
        folded=norm(clause)
        if REPORTED.search(folded) or re.search(r'\b(?:nao|not|se|if|ou|or|talvez|maybe|acho)\b',folded):continue
        m=re.search(patterns[field],folded)
        if m:
            value=clause[m.start(1):m.end(1)]
            found.append((value,clause.strip()))
    return found[0] if len(found)==1 else None
