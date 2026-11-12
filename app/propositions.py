"""Análise determinística limitada de proposições, sem diagnóstico ou ação.

Separação de orações e predicados evita atribuir a negação de uma operação a
outra. O texto original continua sendo a entrada dos guardrails e do escopo.
"""
from dataclasses import dataclass
import re
from app.intents import normalize

ALIASES = {'maq': 'maquininha', 'net': 'internet', 'recuzado': 'recusado',
           'recuzada': 'recusada', 'recuzados': 'recusados', 'recuzadas': 'recusadas'}
DECLINE = re.compile(r'\b(?:recusa|recusad[oa]s?|recusaram|recusou|negad[oa]s?|negaram|negou|rejeitad[oa]s?|rejected|refused|refuses|declin(?:e|ed)|denied)\b')
PAYMENT = re.compile(r'\b(?:cartao|cartoes|transaco?es|transacao|vendas?|pix|pagamentos?|transactions?|cards?|payments?)\b')
ACTION = re.compile(r'\b(?:transfira|transferir|transfere|transfer|contrate|contratar|altere|alterar|cancele|cancelar|cancel)\b')
INFORMATION = re.compile(r'\b(?:como|how|o que|what|explique|explain|qual|quais|which)\b')

def canonical(text):
    return re.sub(r'\b\w+\b', lambda m: ALIASES.get(m[0], m[0]), normalize(text))

@dataclass(frozen=True)
class Proposition:
    text: str
    decline: bool
    modality: str | None
    action: bool
    connectivity: bool

def propositions(message):
    text = canonical(message)
    # Conjunções só separam quando introduzem sujeito/predicado, nunca os dois
    # produtos de uma comparação ou os objetos de um mesmo predicado.
    parts = re.split(r'[;!?\n]|\.(?!\d)|\b(?:mas|but)\b|,\s*(?=not\b|nao\b)|'
                     r'\b(?:e|and)\s+(?=(?:(?:o|a|meu|minha|my)\s+)?(?:pix|cartao|card|transacao)\b|'
                     r'(?:informe|explique|explain|compare|quando|when|qual|quais|quanto|what|diga|tell|transfira|transfer|cancele|cancel)\b|'
                     r'(?:minha|meu|my)\s+(?:maquininha|terminal|machine)\b)', text)
    result = []
    for part in filter(None, (p.strip(' ,') for p in parts)):
        decline = False
        for match in DECLINE.finditer(part):
            prefix = part[:match.start()]
            negated = bool(re.search(r'\b(?:nao|not|never|nenhuma?)\b(?:\s+\w+){0,3}\s*$', prefix))
            negated = negated or bool(re.search(r'\bno\s+(?:card\s+)?(?:transaction|payment)\s+(?:was\s+)?$',prefix))
            if not negated and PAYMENT.search(part):
                decline = True
        modality = 'pix' if re.search(r'\bpix\b',part) else 'card' if re.search(r'\b(?:cartao|cartoes|cards?)\b',part) else None
        action = False
        for match in ACTION.finditer(part):
            prefix = part[:match.start()]
            negated = re.search(r'\b(?:nao|not|never)\s+(?:(?:quero|desejo|want\s+to)\s+)?$',prefix)
            if not negated and not INFORMATION.search(prefix):
                action = True
        if not INFORMATION.search(part) and re.search(r'\b(?:faca|efetue|execute|realize|quero|solicito)\b',part) and re.search(r'\b(?:transferencias?|contratacao|alteracao|cancelamento)\b',part):
            action = not bool(re.search(r'\bnao\b',part))
        # Ausência de rede é um sintoma, não uma afirmação de marca/país.
        # A negação pertence ao predicado local ('não está sem rede'), sem
        # apagar outro pedido de conexão na mesma mensagem.
        absent_network = False
        for match in re.finditer(r'\b(?:sem\s+(?:rede|sinal)|(?:no|without)\s+(?:network|signal))\b',part):
            prefix=part[:match.start()]
            denied=re.search(
                r'\b(?:nao|not|never)\b(?:\s+(?:esta|estao|estava|ficou|ficaram|fica|ficam|'
                r'parece|parecem|estar|aparece|aparecendo|exibe|exibindo|mostra|mostrando|'
                r'mais|agora|ainda|is|are|was|were|has|have|been|showing|shows|currently|still|no|longer))*\s*$',prefix)
            if not denied:absent_network=True
        connectivity = absent_network or bool(re.search(r'\b(?:wi-?fi|internet|conexao|connect\w*|conect\w*|reconect\w*|desconect\w*|offline)\b',part))
        if connectivity:
            question=bool(re.search(r'\b(?:como|how|configur|reconectar|procurar redes|tem|possui|suporta)\w*\b',part))
            negative_problem=bool(re.search(r'\b(?:nao|not)\s+(?:e|is|was)\s+(?:um |a )?(?:problema|problem|falta|falha|failure)\b|\b(?:nao ha|sem|no|without)\s+(?:queda|quedas|falha|falhas|problema|problemas|drops?|failures?)\b',part))
            restored=bool(re.search(r'\b(?:esta|estao|is|are)\s+(?:conectad[oa]s?|connected|online)|(?:internet|rede|conexao).{0,20}(?:funciona|normal|working|ok)|\b(?:conectou|connected successfully|voltou)\b',part))
            restored=restored or bool(re.search(r'\bvoltou a (?:acessar|conectar|funcionar)\b|\b(?:mesmo|ja|continua) conectad[oa]\b',part))
            declined_request=bool(re.match(r'^(?:(?:eu|i)\s+)?(?:nao|not|do not|don.t)\s+(?:quero|desejo|want(?: to)?)\s+',part))
            if declined_request or (not question and (negative_problem or restored)):connectivity=False

        result.append(Proposition(part, decline, modality, action, connectivity))
    return tuple(result)

def knowledge_tasks(message, *, support_answered=False):
    """Plano público limitado; cada tarefa é respondida ou recebe limitação.

    Retorna pares (assunto, consulta). A mensagem original deve ser validada
    antes de usar consultas canônicas. Não envia fixtures ou contexto ao LLM.
    """
    from app.intents import request_facts, YESTERDAY_SALES
    # Remove only standalone status questions already answered by Support.
    # The original message still goes through scope/privacy checks upstream.
    if support_answered:
        from app.intents import terminal_status_query
        from app.request_plan import split_questions
        questions = split_questions(message)
        remaining = [p.text for p in questions if not terminal_status_query(p.text)]
        if len(remaining) != len(questions):
            if not remaining:
                return []
            public_message = '. '.join(remaining)
            return knowledge_tasks(public_message, support_answered=True) or [
                ('information', part) for part in remaining]
    facts = request_facts(message)
    parts = propositions(message)
    from app.request_plan import split_questions, informational_part
    questions=split_questions(message)
    explicit=[p for p in questions if informational_part(p.text)]
    # Keep independently asked questions verbatim. Only inherit an unambiguous
    # product name; scope and credentials are validated on the original first.
    redacted_other = len(explicit)==1 and len(questions)>1 and all('[credencial removida]' in p.text for p in questions if p not in explicit)
    if (len(explicit)>1 or redacted_other) and not facts.unsupported_action:
        products=' e '.join(sorted(facts.entities))
        from app.request_plan import TOPIC_ANCHORS
        def inherited_product(part):
            # A self-contained service question is not an anaphor to a product
            # named in a different question (e.g. advance followed by Link).
            own_topic=any(re.search(pattern,canonical(part)) for topic,pattern in TOPIC_ANCHORS.items() if topic!='comparison')
            return products and not request_facts(part).entities and not own_topic
        return [('information',p.text+((' sobre Get '+products) if inherited_product(p.text) else '')) for p in explicit]
    if facts.comparison and not facts.unsupported_action:
        attrs=__import__('app.request_plan',fromlist=['requested_attributes']).requested_attributes(message)
        if 'printing' in attrs:
            return [('comparison','Compare Get Clássica e Get Smart.'),('information','A Get Clássica e a Get Smart imprimem comprovante?')]
    from app.request_plan import requested_attributes
    attrs=requested_attributes(message)
    # Multi-attribute product question: retain a separate evidence obligation for
    # each attribute instead of letting the fee template hide settlement.
    if facts.entities==frozenset({'link'}) and 'commercial' in attrs and 'settlement' in attrs and not facts.unsupported_action:
        obligations=[]
        if re.search(r'whatsapp|compartilh|mandar|enviar|share|send',canonical(message)):
            obligations.append(('link','Como criar e compartilhar Link de Pagamento pelo WhatsApp?'))
        obligations.extend([('commercial','Qual a taxa do Link de Pagamento?'),('information','Qual o prazo de recebimento do Link de Pagamento?')])
        return obligations
    tasks = []
    if facts.unsupported_action:
        tasks.append(('action', 'Transfira valores.'))
    if facts.account_migration:
        tasks.append(('migration', 'Minha conta já foi migrada?'))
    modalities = dict.fromkeys(p.modality for p in parts if p.decline)
    for modality in modalities:
        subject = {'pix':'Pix','card':'cartão',None:'transação'}[modality]
        code = f' Código {facts.error_code}.' if facts.error_code else ''
        tasks.append(('decline', f'Minha transação {subject} foi recusada.'+code))
    if facts.comparison:
        tasks.append(('comparison', 'Compare Get Clássica e Get Smart.' +
                      (' A Get Clássica tem Wi-Fi?' if facts.connectivity and 'classica' in facts.entities else '')))
    if facts.connectivity and not facts.comparison:
        tasks.append(('connectivity', 'A Get Clássica tem Wi-Fi?' if 'classica' in facts.entities else 'Minha maquininha não conecta à internet. Como configurar Wi-Fi?'))
    text = canonical(message)
    if re.search(r'\b(?:antecipacao|antecipar|advance|advancement)\b',text) and not re.search(r'\b(?:nao|not|without|sem)\s+(?:quero |want to )?(?:antecip|advance)',text):
        tasks.append(('advance', 'Como antecipar minhas vendas pelo app?'))
    if 'link' in facts.entities and not facts.account_migration:
        tasks.append(('link', 'Qual a taxa do Link de Pagamento?' if facts.fee else 'Como criar e compartilhar Link de Pagamento pelo WhatsApp?'))
    if re.search(r'\bpix\b',text) and not facts.decline:
        for part in parts:
            if 'pix' in part.text and not part.connectivity and informational_part(part.text):
                tasks.append(('information',part.text))
    if facts.fee:
        for part in parts:
            local=request_facts(part.text)
            if local.fee and ('link' not in local.entities or local.comparison):
                tasks.append(('commercial',part.text))
    from app.intents import receivable_query
    if support_answered and receivable_query(message).individual and tasks:
        # A agenda individual já foi respondida pelo Support; não a converter
        # em prazo público ou enviar dados sintéticos ao gerador.
        return tasks
    # Uma única intenção mantém formulação/condições originais. Composição
    # usa consultas por assunto, mas o escopo original é checado pelo caller.
    return tasks if len(tasks)>1 else []
