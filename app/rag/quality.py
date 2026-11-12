"""Pertinência e conflitos verificáveis, separados da integridade das citações.

Filtro de conceitos limitado: não promete detectar contradições universais.
Conflitos numéricos são comparados somente com mesma afirmação e condições.
"""
import re
from app.intents import normalize

CONCEPTS = (
    {'crediario','parcelamento','parcelas','installments','instalments'},
    {'antecipacao','antecipar','advance','advancement'},
)

COUNTRIES = set('brazil brasil mexico chile argentina uruguay uruguai colombia spain espanha portugal japan japao germany alemanha canada peru australia'.split())


def predicate_supported(question, candidate):
    """Cobertura limitada do predicado no corpo; título/data não provam atributos.

    Não é inferência semântica universal. Marcadores suportados são conservadores;
    trechos e condições permanecem integrais para a apresentação.
    """
    q = normalize(question)
    body = normalize(candidate['text'])
    words = set(re.findall(r'\w+', q))
    body_words = set(re.findall(r'\w+', body))
    from .scope import BANK_RELATION
    if BANK_RELATION.search(q):
        if not re.search(r'\b(?:conta|account|cuenta)\b', body) or not re.search(r'\b(?:banco\w*|bank\w*|santander)\b', body):
            return False
    if words & {'paises','countries','presence'}:
        if not re.search(r'\b(?:presence in|present in|presenca (?:em|no|na)|atua (?:em|no|na)|operat\w* in)\b', body) or not body_words & COUNTRIES:
            return False
    # Assunto institucional novo não pode aparecer apenas no título de um corpo alheio.
    topics = ({'sustentabilidade','sustainability','sustainable','sustentavel','ambiental','environmental','emissoes','emissions','carbono','carbon'},
              {'seguranca','security','fraude','fraudes','fraud','suspeitas','suspeitos','suspeita','suspeito','suspicious','antifraude','antifraud'})
    for group in topics:
        if words & group and not body_words & group:
            return False
    if re.search(r'\b(?:sem|without)\b.{0,45}\b(?:maquininha|maquina|terminal|machine|device)\b', q):
        if not re.search(r'\b(?:sem|without)\b.{0,65}\b(?:maquininha|maquina|terminal|machine|device)\b', body):
            return False
    if re.search(r'\b(?:imprim\w*|impress\w*|print\w*|bobina|papel)\b', q):
        if not re.search(r'\b(?:imprim\w*|impress\w*|print\w*|bobina|papel)\b', body):
            return False
    # O assunto Pix em um manual de aparelho não confirma capacidade de aceitar Pix.
    if 'pix' in words and words & {'smart','classica'} and 'pix' not in body_words:
        return False
    timing = re.search(r'\b(?:prazo|prazos|plazo|plazos|frequencia|frequency|quanto tempo|quantos dias|how long)\b', q)
    if timing and re.search(r'\b(?:receb\w*|abono\w*|deposit\w*|liquida\w*|settle\w*)\b', q):
        if not re.search(r'\b(?:receb\w*|abono\w*|deposit\w*|liquida\w*|settle\w*)\b', body):
            return False
        if not re.search(r'\b(?:dias?|days?|horas?|hours?|prazo|plazo|frequencia|frecuencia|frequency|imediat\w*|instant\w*|pactada)\b|d\s*\+\s*\d', body):
            return False
    return True


def relevant_candidates(question, candidates):
    from app.request_plan import split_questions, without_declined_requests
    from app.intents import request_facts
    excluded=set()
    for part in split_questions(question):
        if re.match(r'^(?:nao|not|do not|don.t)\s+(?:quero|desejo|want|want to)\s+',normalize(part.text)):
            excluded.update(request_facts(part.text).entities)
    question=without_declined_requests(question)
    words=set(re.findall(r'\w+',normalize(question)))
    if excluded:
        candidates=[c for c in candidates if not (excluded & set(re.findall(r'\w+',normalize(c.get('title','')+' '+c['text']))))]
    candidates=[c for c in candidates if predicate_supported(question,c)]
    from app.intents import request_facts
    facts=request_facts(question);entities=facts.entities
    if entities:
        def compatible(c):
            if entities & set(re.findall(r'\w+',normalize(c.get('title','')+' '+c['text']))):return True
            # The separately reviewed Brazilian Wi-Fi procedure is generic to a
            # machine, conditional on Wi-Fi; its exact body may omit product names.
            if facts.connectivity:
                from hashlib import sha256
                from .guidance import WIFI,REVIEWED,REVIEWED_TITLES
                return c.get('source')==WIFI and c.get('title')==REVIEWED_TITLES[WIFI] and sha256(c['text'].encode()).hexdigest()==REVIEWED[WIFI]
            return False
        candidates=[c for c in candidates if compatible(c)]
    # Produtos com condições distintas não são intercambiáveis mesmo quando
    # a consulta/index fornece IDs e URLs sintaticamente válidos.
    if words & {'recebiveis','receivables'} and not words & {'antecipacao','antecipar','advance','advancement'}:
        candidates=[c for c in candidates if re.search(r'\b(?:recebiveis|receivables)\s+(?:sao|are|consistem|representam)\b',normalize(c['text']))]
    required=[group for group in CONCEPTS if words & group]
    if not required:return candidates
    return [c for c in candidates if all(set(re.findall(r'\w+',normalize(c.get('title','')+' '+c['text']))) & group for group in required)]

def conflicting_rates(candidates):
    claims={}
    for c in candidates:
        for sentence in re.split(r'[.!?](?!\d)',normalize(c['text'])):
            if not re.search(r'\b(?:taxa|tarifa|rate|fee)\b',sentence):continue
            values=re.findall(r'\d+(?:[.,]\d+)?\s*%',sentence)
            if len(values)!=1:continue
            scope=re.sub(r'\d+(?:[.,]\d+)?\s*%','<rate>',sentence).strip()
            # Conserva condições do título, mercado e data de captura. Só os
            # títulos genéricos de tarifa não acrescentam outra condição.
            title=normalize(c.get('title','')).strip()
            if re.fullmatch(r'(?:tarifa|taxa|rate|fee)(?: atualizada| atual| vigente)?',title):title=''
            key=(scope,title,c.get('market','BR'),c.get('captured_at'))
            claims.setdefault(key,set()).add(values[0].replace(',','.').replace(' ',''))
    return any(len(values)>1 for values in claims.values())


def commercial_attribute(question):
    words=set(re.findall(r'\w+',normalize(question)))
    if words & {'preco','precos','custo','custos','custa','custam','price','prices','cost','valor','mensalidade','aluguel','rental','monthly'}:return 'preço'
    if words & {'taxa','taxas','tarifa','tarifas','cobranca','cobrancas','charge','charges','fee','fees','rate','rates','juros'}:return 'taxa'
    return None


def attribute_candidates(question,candidates):
    """Coincidência de produto não prova seu preço/tarifa.

    Valores monetários/percentuais devem estar na mesma evidência do atributo;
    condições e título continuam anexos. Sem valor, a saída declara a lacuna.
    """
    attribute=commercial_attribute(question)
    if not attribute:return candidates
    from app.intents import request_facts
    entities=request_facts(question).entities
    terms={'preço':r'preco|custo|custa|costo|price|cost|valor|mensalidade|aluguel|rental|monthly', 'taxa':r'taxa|tarifa|fee|rate|juros|comision|mdr'}[attribute]
    found=[]
    for c in candidates:
        context=normalize(c.get('title','')+' '+c['text'])
        if entities and not entities <= set(re.findall(r'\w+',context)):continue
        # Título pode restringir modelo/plano; o valor deve estar no corpo e na
        # mesma afirmação do atributo. Ano, desconto ou mínimo de outro assunto
        # não se tornam tarifa só porque o título contém "taxa".
        claims=re.split(r'[.!?;\n](?!\d)',normalize(c['text']))
        for claim in claims:
            if not re.search(r'\b(?:'+terms+r')\b',claim):continue
            value=(r'\d+(?:[.,]\d+)?\s*%|sem taxa|(?:tarifa|comision|mdr)[^.]*depend'
                   if attribute=='taxa' else
                   r'(?:preco|custa|custo|price|cost|aluguel|mensalidade)[^.!?]{0,80}(?:r\$|usd|clp|\$)\s*\d|\d+[.,]\d+\*?\s*uf\s*\+\s*iva|sem custo|free of charge')
            if re.search(value,claim):
                found.append(c);break
    return found
