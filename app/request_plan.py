"""Plano de perguntas públicas: preserva atributos e a origem de cada subpedido.

Não autoriza ferramentas nem fornece fatos. O código de política decide escopo;
a recuperação precisa demonstrar cobertura do atributo, não só citar o produto.
"""
from dataclasses import dataclass
import re
from app.intents import normalize

@dataclass(frozen=True)
class QuestionPart:
    text: str
    attributes: tuple[str, ...]

# Famílias de atributos, compartilhadas entre política, plano e cobertura.
ATTRIBUTES = {
    'commercial': r'\b(?:taxas?|tarifas?|cobrancas?|charges?|pre[cç]os?|cust[oa]s?|custam|valores?|mensalidade|aluguel|rental|monthly|fee|fees|rates?|price|cost)\b',
    'settlement': r'\b(?:prazos?|recebimentos?|recebive(?:l|is)|receber|recebo|recebe|recebem|deposita|depositam|deposits?|deposito|abono|settlement|when.*deposited)\b',
    'installments': r'\b(?:parcelas?|parcelamento|parcelad[oa]s?|prestacoes|vezes|installments?)\b',
    'printing': r'\b(?:imprim\w*|impress\w*|comprovante|bobina|print\w*|receipt)\b',
    'eligibility': r'\b(?:precis[ao]|requisit\w*|necessar\w*|exige|exigir|require\w*|need|elegiv\w*)\b',
    'capability': r'\b(?:aceita|aceitar|accept\w*|suporta|support\w*|tem|possui|permite)\b',
    'portability': r'\b(?:celular|smartphone|mobile|tap)\b',
}

def requested_attributes(text):
    plain=normalize(text)
    return tuple(name for name,pattern in ATTRIBUTES.items() if re.search(pattern,plain))

def financial_request(text):
    """Objeto financeiro + pergunta/consulta, sem transformar assunto solto em ação."""
    plain=normalize(text)
    object_=re.search(r'\b(?:recebimentos?|recebive(?:l|is)|taxas?|tarifas?|debitos?|creditos?|precos?|valores?|mensalidade|aluguel|rental|payments?|deposits?|receivables?|settlements?|fees?|rates?|prices?)\b',plain)
    predicate=re.search(r'\b(?:qual|quais|quanto|quando|como|quero|consultar|consulte|saber|ver|what|when|how|check|view|cost|price|fee|rate)\b',plain)
    implied=bool(re.search(r'\b(?:quanto (?:eu )?(?:tenho|vou|posso) (?:para |a )?receber|how much (?:will i|do i) (?:receive|get))\b',plain))
    return bool((object_ and predicate) or implied)

def split_questions(text):
    # Preserve list conjunctions and decimal/ISO dates. Only an explicit question
    # boundary creates a new part; product lists remain one comparison question.
    parts=re.split(r'[?!;\n]+|\.(?=\s|$)|\s+(?:e|and)\s+(?=(?:qual|quais|quanto|quando|como|what|when|how|posso|can i|o que)\b)',text,flags=re.I)
    return tuple(QuestionPart(p.strip(),requested_attributes(p)) for p in parts if p.strip())

def informational_part(text):
    return bool(re.search(r'\b(?:como|o que|qual|quais|quanto|quando|posso|preciso|precisa|exige|em quantas|em quantos|quero saber|explique|explain|informe|describe|aceita|suporta|permite|what|when|how|can i|do i|does|need|compare|diferenca)\b',normalize(text)))

def grounded_attribute_limit(question,candidates):
    """Avisa atributos sem apoio; nunca usa ausência do trecho como resposta negativa."""
    attrs=requested_attributes(question)
    corpus=normalize(' '.join(c['text'] for c in candidates))
    limits=[]
    if 'commercial' in attrs and not re.search(r'(?:taxa|tarifa|preco|custo|fee|price|cost)',corpus):
        limits.append('Não consigo confirmar a taxa ou o preço aplicável nas fontes pertinentes; consulte a oferta vigente no canal oficial Getnet.')
    if 'settlement' in attrs and not re.search(r'\b(?:dias?|horas?|prazo|abono|deposit|receba|recebe|recebimento|settlement)\w*',corpus):
        limits.append('Não tenho evidência pertinente para confirmar o prazo de recebimento solicitado.')
    if 'portability' in attrs and not corpus.strip():
        limits.append('Não tenho fonte pertinente para confirmar a solução solicitada usando só o celular. Consulte as opções e a compatibilidade do aparelho no canal oficial Getnet.')
    if 'printing' in attrs and not re.search(r'imprim|impress|print|bobina|comprovante',corpus):
        limits.append('Não tenho evidência suficiente para confirmar o recurso ou procedimento de impressão desse modelo.')
    if 'installments' in attrs and not re.search(r'parcela|prestac|installment|cuotas|\d+\s*x\b',corpus):
        limits.append('Não confirmei o parcelamento disponível para esse produto; depende de uma fonte pertinente e das condições aplicáveis.')
    if 'capability' in attrs and re.search(r'\bpix\b',normalize(question)) and re.search(r'\b(?:smart|classica|terminal|maquininha)\b',normalize(question)):
        if not (re.search(r'\bpix\b',corpus) and re.search(r'\b(?:smart|classica|terminal|maquininha)\b',corpus)):
            limits.append('Uma FAQ sobre conta Pix não confirma aceitação Pix nesse modelo. Não tenho evidência específica suficiente para confirmar esse recurso.')
    if 'eligibility' in attrs and re.search(r'crediario',normalize(question)) and re.search(r'cartao|card',normalize(question)):
        if not re.search(r'cartao.{0,60}credito|credit card|cartao de credito',corpus):
            limits.append('O trecho sobre limite de parcelas não esclarece o requisito de cartão solicitado; confirme a elegibilidade no canal oficial antes de oferecer a venda.')
    return tuple(limits)


def without_declined_requests(text):
    """Retira só cláusulas explícitas de assunto recusado da busca, nunca da segurança."""
    parts=split_questions(text)
    keep=[p.text for p in parts if not re.match(r'^(?:nao|not|do not|don.t)\s+(?:(?:quero|desejo|want|want to)\s+)',normalize(p.text))]
    return '. '.join(keep) if keep else text


TOPIC_ANCHORS = {
    'commercial': ATTRIBUTES['commercial'],
    'advance': r'antecip|advance', 'settlement': r'vend|sales|saldo|balance|receb|deposit',
    'installments': r'crediario|parcela|installment', 'link': r'link', 'link_fee': r'link',
    'comparison': r'classica|smart',
}

def project_topic(quote, topic):
    """A citação prova o pedido; a consulta leva só suas cláusulas pertinentes.

    Compartilha as fronteiras de perguntas com a orquestração. Uma interpretação
    pode citar o turno inteiro sem que isso autorize repetir consultas privadas.
    """
    from app.intents import receivable_query
    pattern=TOPIC_ANCHORS.get(topic)
    if pattern is None:return None
    selected=[]
    for part in split_questions(quote):
        personal=receivable_query(part.text).individual
        if re.search(pattern,normalize(part.text)) and (personal if topic=='settlement' else not personal):
            selected.append(part.text)
    return '. '.join(selected) or None

def independent_public_request(message):
    """Divide apenas consultas individuais + perguntas públicas autocontidas.

    Não autoriza segurança/mercado. O chamador aplica a política no original
    antes deste plano. Fluxos de diagnóstico dependente continuam indivisíveis.
    """
    from app.intents import receivable_query
    from app.router import RouterDemo
    from app.brazil_scope import market_of, BUSINESS
    from app.contracts import Entrada
    private=[];public=[]
    parts=split_questions(message)
    if not 2<=len(parts)<=8:return None
    for part in parts:
        if re.fullmatch(r'(?:oi|ola|hello|hi|bom dia|boa tarde|boa noite)',normalize(part.text)):continue
        # Country framing has already passed the whole-message scope policy;
        # it is not an unanswered lookup or a new public obligation.
        if market_of(part.text).value=='BR' and not BUSINESS.search(normalize(part.text)) and not financial_request(part.text):continue
        if receivable_query(part.text).individual:private.append(part.text)
        elif informational_part(part.text) and RouterDemo().planejar(Entrada(message=part.text,user_id='public_plan')).rota=='knowledge':public.append(part.text)
        else:return None
    if private and public:return '. '.join(private), '. '.join(public)
    return None


def dependent_help(text):
    """Ato de ajuda dependente, sem produto ou assunto novo no próprio trecho."""
    plain=normalize(text)
    return bool(re.fullmatch(r'(?:what should i do(?: next)?|how (?:can|should) i (?:proceed|continue)|(?:o )?que (?:eu )?(?:devo fazer|faco)(?: agora)?|como (?:devo |posso )?proceder|qual (?:e )?(?:a )?orientacao)[?.! ]*',plain))
