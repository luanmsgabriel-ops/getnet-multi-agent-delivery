"""Intenções compartilhadas entre roteamento e suporte demonstrativo."""
import re
import unicodedata
from dataclasses import dataclass

# Compartilhado com a reformulação da busca para evitar divergência de rotas.
PUBLIC_QUESTION_PREFIX = re.compile(
    r'^(?:(?:por favor|please)\s+)?(?:o que e|o que sao|quem e|quem sao|quem foi|quem foram|'
    r'what is|what are|who is|who are|who was|who were|explique|explain)\s+')

def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold())
                   if not unicodedata.combining(c)).replace('’', "'")

# Data e ação ligadas à venda, sem capturar qualquer frase que contenha "ontem".
YESTERDAY_SALES = re.compile(
    r"\byesterday'?s\s+sales\b|"
    r'\bvendas?\s+(?:de\s+|(?:realizadas?|feitas?|efetuadas?)\s+|'
    r'que\s+(?:(?:eu|nos)\s+)?(?:fiz|fizemos|realizei|realizamos|efetuei|efetuamos)\s+)ontem\b')

@dataclass(frozen=True)
class Intents:
    receivables: bool
    terminal: bool
    technical: bool
    knowledge: bool

@dataclass(frozen=True)
class RequestFacts:
    """Fatos lexicais compartilhados; não são diagnóstico nem compreensão universal."""
    decline: bool
    modality: str | None
    entities: frozenset[str]
    comparison: bool
    connectivity: bool
    fee: bool
    account_migration: bool
    unsupported_action: bool
    error_code: str | None


def request_facts(message):
    from app.propositions import canonical, propositions
    text = canonical(message)
    clauses = propositions(message)
    words = set(re.findall(r'[a-z0-9]+', text))
    declined = any(p.decline for p in clauses)
    modalities = {p.modality for p in clauses if p.decline}
    modality = next(iter(modalities)) if len(modalities)==1 else None
    if not declined:
        modality = 'pix' if 'pix' in words else 'card' if words & {'cartao','cartoes','card','cards'} else None
    entities = frozenset(words & {'classica','smart','link'})
    comparison = len(entities & {'classica','smart'}) == 2 and bool(words & {
        'difference','differences','compare','comparison','diferenca','diferencas','comparar','comparacao','versus','vs','melhor','best','better','escolher','como','like'})
    connectivity = any(p.connectivity for p in clauses)
    fee = bool(words & {'taxa','taxas','tarifa','tarifas','preco','precos','custo','custos','custa','custam','mensalidade','aluguel','rental','monthly','valor','valores','fee','fees','rate','rates','price','cost'})
    migration = bool(re.search(r'\bmigr\w*\b', text)) and bool(words & {'conta','account','pacote','package','meu','minha','my'})
    # Negação e pergunta são locais ao predicado da ação.
    action = any(p.action for p in clauses)
    code = re.search(r'\b(?:codigo(?:\s+de\s+erro)?|erro|error(?:\s+code)?|code)\s*(?:(?:e|is)\s*)?[:#-]?\s*([0-9]{1,4})\b',text)
    return RequestFacts(declined,modality,entities,comparison,connectivity,fee,migration,action,code[1] if code else None)

@dataclass(frozen=True)
class ReceivableQuery:
    individual: bool
    period: str | None = None
    needs_period: bool = False
    sale_period: "DatePeriod | None" = None
    settlement_period: "DatePeriod | None" = None
    period_issue: str | None = None
    explicit_total: bool = False


from app.receivable_periods import DatePeriod, temporal_periods


def receivable_query(message):
    """Consulta individual com datas de venda e recebimento independentes.

    ``period`` mantém o alias legado para uma data única de venda. Os campos
    estruturados preservam todos os limites; ausência de suporte nunca autoriza
    substituir um período solicitado pelo total da fixture.
    """
    from app.propositions import propositions
    personal=[]
    for clause in propositions(message):
        text=clause.text
        text=re.sub(r'\b(?:sem|without|nao|do not|don.t)\s+(?:(?:quero|desejo|want to)\s+)?(?:consultar|consulte|ver|consult|check|access)\s+[^;.!?]*','',text)
        words=set(re.findall(r'[a-z0-9]+',text))
        balance=bool(words & {'saldo','balance'})
        implied=bool(re.search(r'\b(?:quanto (?:eu )?(?:tenho|vou|posso) (?:para |a )?receber|how much (?:will i|do i) (?:receive|get))\b',text))
        sales=bool(words & {'venda','vendas','sale','sales'})
        receivable=bool(words & {'recebivel','recebiveis','receivable','receivables','recebimento','recebimentos'}) or bool(re.search(r'\b(?:creditos?|depositos?|settlements?|deposits?)\s+(?:previst[oa]s?|scheduled|expected)\b',text))
        if not (balance or sales or receivable or implied):
            # Uma frase que apenas continua o período herda o objeto da consulta.
            # Datas em problemas de terminal ou outros assuntos não são herdadas.
            if personal and re.match(r'^(?:e\s+)?(?:de\s+|entre\s+|desde\s+|ate\s+|no dia\s+|no periodo\s+|o periodo\s+|a data\s+|hoje\b|ontem\b|anteontem\b|\d)',text):
                previous,required=personal[-1]
                personal[-1]=(previous+' '+text,required)
            continue
        if sales and future_sales(text):continue
        # An explicit listing/lookup is distinct from a general commercial question.
        explicit_lookup=bool(re.search(r'\b(?:liste|listar|list|consulte|consultar|consult|check|some|somar|ver|view)\b',text)) and not re.search(r'\b(?:como|how|por que|why)\b',text)
        owned=bool(words & {'meu','minha','meus','minhas','my','our'})
        actual_sales=bool(YESTERDAY_SALES.search(text)) or bool(re.search(r'\b(?:vendas?|sales)\s+(?:de\s+)?(?:hoje|today)\b',text))
        general=bool(re.search(r'\b(?:como (?:funciona|funcionam|posso|consultar|acessar)|how (?:does|do|to)|o que (?:e|sao)|what (?:is|are)|explique|explain)\b',text))
        general=general or bool(words & {'preciso','necessario','need','required'})
        general=general or bool(re.search(r'\b(?:por que|porque|why|pode aparecer|can appear|prazo de recebimento|prazos de recebimento)\b',text))
        general=general or (not owned and bool(words & {'prazo','prazos','tempo','normalmente','geral','usually'}))
        if general and not explicit_lookup and not (balance and owned) and not actual_sales:continue
        if words & {'antecipacao','antecipar','advance','advancement'} and not balance and not actual_sales:continue
        lookup=bool(re.search(r'\b(?:receb(?:o|er)|receberemos|receive|consultar|consulte|consult|check|liste|listar|list|some|somar|ver|view|deposit(?:ed|o)|creditad[oa]|cai|caem|cair|quando|when)\b',text))
        dated=actual_sales or bool(re.search(r'\b(?:vendas?|sales)\s+(?:de\s+)?(?:anteontem|ha\s+\d+\s+dias|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2})',text))
        if balance or receivable or implied or (sales and (lookup or owned or dated or explicit_lookup)):
            personal.append((text,sales or implied or bool(re.search(r'\b(?:quando|when)\b',text))))
    if not personal:return ReceivableQuery(False)
    sale_period=settlement_period=None
    issue=None
    for text,_ in personal:
        sale,settlement,error=temporal_periods(text,'sale' if re.search(r'\b(?:vendas?|sales)\b',text) else 'settlement')
        if error:
            issue=error
            break
        if (sale_period and sale and sale_period!=sale) or (settlement_period and settlement and settlement_period!=settlement):
            issue='Há períodos diferentes no pedido; consulte um intervalo de venda e um de recebimento por vez.'
            break
        sale_period=sale or sale_period
        settlement_period=settlement or settlement_period
    total=any(re.search(r'\b(?:total|saldo|balance)\b',text) for text,_ in personal)
    needs=bool(issue) or (any(required for _,required in personal) and sale_period is None and settlement_period is None and not total)
    period=sale_period.start if sale_period and sale_period.start==sale_period.end else None
    return ReceivableQuery(True,period,needs,sale_period,settlement_period,issue,total)


def future_sales(message):
    text=normalize(message)
    if not re.search(r'\b(?:vendas?|sales)\b',text):return False
    return bool(re.search(r'\b(?:farei|faremos|futuras?|future)\b',text) or
                re.search(r'\b(?:vendas?|sales)\s+(?:de\s+)?(?:amanha|tomorrow)\b',text) or
                re.search(r"\btomorrow'?s\s+sales\b",text))


def terminal_status_query(message):
    """Recognize only a standalone private status lookup, never troubleshooting.

    Full matching prevents a status phrase from swallowing a product question,
    negation, technical symptom or action in the same clause.
    """
    text = normalize(message).strip().strip('?.! ')
    device = r'(?:terminal|maquininha|maquina|machine|card machine)'
    return bool(re.fullmatch(
        rf'(?:(?:por favor|please)\s+)?(?:'
        rf'qual (?:e )?o (?:estado|status) d[oa] (?:meu|minha) {device}|'
        rf'(?:consulte|consultar|ver|quero saber|informe) (?:o )?(?:estado|status) d[oa] (?:meu|minha) {device}|'
        rf'(?:meu|minha) {device} esta online|'
        rf'what is (?:the )?status of my {device}|is my {device} online'
        rf')', text))


def classify(message):
    from app.propositions import canonical
    from app.request_plan import without_declined_requests
    text=canonical(without_declined_requests(message))
    facts=request_facts(message)
    words=set(re.findall(r'[a-z0-9]+',text))
    receivables=receivable_query(message).individual
    terminal=bool(words & {'minha','meu','minhas','meus','my'}) and bool(words & {'maquininha','maquininhas','maquina','terminal','terminais','machine'})
    technical=bool(words & {'maquininha','maquina','terminal','machine','transacao','transaction'}) and bool(
        words & {'internet','wifi','conexao','conectar','conecta','conectando','conectou',
                 'conectada','conectado','desconectada','desconectado','offline',
                 'connect','erro','error','decline','declined','negada','recusada'})
    technical = technical or facts.decline
    knowledge=facts.connectivity or future_sales(message) or technical or facts.account_migration or facts.unsupported_action or bool(words & {
        'como','qual','quais','taxa','taxas','pix','wifi','clima','cambio','getnet',
        'what','who','quem','how','weather','exchange','difference','differences','compare','comparison',
        'diferenca','diferencas','comparar','comparacao','smart','classica','crediario',
        'antecipar','antecipacao','advance','recebiveis','recebivel','recebimentos','recebimento','receivables','link','bank','account','cobrar','pagamento','pagamentos','deposito','depositos','cobranca','cobrancas'})
    # Interrogativos não transformam uma consulta de saldo em dúvida de produto.
    if receivables:
        knowledge = technical or bool(words & {
            'pix','classica','smart','taxa','taxas','crediario','antecipacao',
            'antecipar','advance','link','wifi'}) or bool(re.search(
                r'\b(?:como\s+(?:consultar|ver|acessar)|how\s+(?:do\s+i\s+|can\s+i\s+|to\s+)?(?:check|view|access))\b',text))
    # Interrogatives alone do not create a public RAG obligation for status.
    if terminal and terminal_status_query(text):
        knowledge = False
    return Intents(receivables,terminal,technical,knowledge)

def natural_public_question(message):
    """Intenção informativa explícita; nunca fallback geral de uma consulta privada."""
    text=normalize(message).strip()
    if not PUBLIC_QUESTION_PREFIX.match(text):
        return False
    # Um prefixo informativo não torna uma consulta de recebíveis pública.
    intent = classify(message)
    if intent.receivables or intent.terminal:
        return False
    words=set(re.findall(r'[a-z0-9]+',text))
    blocked={'getnet','smart','classica','pix','crediario','antecipacao','receivables',
             'payment','maquininha','terminal','conta','account','cliente','customer',
             'meu','minha','meus','minhas','my','our','tenant','saldo','balance',
             'clima','previsao','weather','forecast','temperature','temperatura',
             'cambio','cotacao','exchange','euro','eur','dollar','dolar','usd'}
    return not bool(words & blocked)

def public_technical_only(message):
    """Permite apenas orientação documental; não concede acesso às fixtures."""
    text=normalize(message)
    intent=classify(message)
    private=re.search(r'\b(?:conta|saldo|recebiveis|tenant|cpf|cnpj|senha|password|account|balance)\b|\d{6,}|@',text)
    return intent.technical and not intent.receivables and not private
