"""Contrato de produto: atendimento Getnet Brasil, sem cotação de referência.

Regras determinísticas conservadoras, não compreensão universal de linguagem.
Decisão de produto de Luan; não requisito confirmado da banca.
"""
from dataclasses import dataclass
import re
from urllib.parse import urlsplit
from app.intents import normalize
from app.contracts import RespostaEspecialista
from app.response_notices import AnswerText, Notice, compose_notices

DISCLOSURE = 'Sou um assistente de IA criado para demonstração de atendimento Getnet Brasil; este não é um canal oficial da Getnet.'
DCC_SOURCE = 'https://site.getnet.com.br/conversor-de-moedas-getnet-disponivel-agora-no-tef/'
from app.brazil_scope import REDIRECT_BR, CLARIFY_BR
REDIRECT = REDIRECT_BR
QUOTE = 'Não forneço cotações nem cálculos de conversão monetária. Posso ajudar a entender como funciona a conversão em uma venda Getnet.'
CLARIFY = 'Você quer uma cotação de referência ou entender a conversão em uma venda Getnet? Não forneço cotações, mas posso explicar o funcionamento do serviço.'
CURRENCY = re.compile(r'\b(?:euro|euros|eur|dolar|dolares|dollar|dollars|usd|gbp|libra|iene|cambio|cambial|ptax|bce|cotacao|cotacoes|currency|exchange|dcc|moedas?|converter|converta|convert|conversao|conversor)\b')
TOPICS = re.compile(r'\b(?:getnet|pix|crediario|maquininhas?|maquinas?|maq|terminais|terminal|recebiveis|saldo|antecipacao|antecipar|classica|smart|adquirencia|pagamentos?|payment|payments|transacao|transacoes|transactions?|cartao|cartoes|card|cards|vendas?|sales|receivables|balance|wifi|wi-fi|link|tef|conta|account|cadastro|pacote|servico|dinheiro|senha|password|autenticacao|authentication)\b')
OFF_TOPIC = re.compile(r'\b(?:clima|tempo|previsao|weather|forecast|temperatura|temperature|chover|chuva|python|dns|futebol|receita|horoscopo|programacao|programming|algoritmos?)\b')

@dataclass(frozen=True)
class ServicePlan:
    message: str
    replies: tuple[RespostaEspecialista, ...] = ()

def reply(text, *, source=None, status='limitado', limitation_code=None):
    return RespostaEspecialista(texto=str(text), presentation=list(text.parts) if isinstance(text,AnswerText) else [], status=status, limitation_code=limitation_code, fontes=[source] if source else [], modo='extrativo')

# Snapshot literal reviewed independently from the historical editorial summary.
DCC_EVIDENCE_SHA256='1cac981f9243b1c7a2ec2f8ea00ab212181c22b8d94e6f66ab611dee18fa30f7'
DCC_SNAPSHOT='1e01cc91c615970f7402a475a8cca52dee9d1d080fc9e784c3c61c8e53dccfc7.json'

def dcc_available():
    from pathlib import Path
    import hashlib
    path=Path(__file__).resolve().parent.parent/'corpus_publico'/DCC_SNAPSHOT
    try:return hashlib.sha256(path.read_bytes()).hexdigest()==DCC_EVIDENCE_SHA256
    except OSError:return False


def dcc_retrieved(message, *, general_context=False, local=None):
    """Normal local retrieval, never a product answer embedded in policy code."""
    if getattr(local,'documentary',False):
        # Reuse the configured adapter and exact predicate; no hidden fallback.
        from app.contracts import Entrada
        return local._single(Entrada(message=message,user_id='public_query'),())
    from pathlib import Path
    from app.rag.core import Index,load_snapshot
    from app.rag.fetch import SOURCES
    from app.knowledge import KnowledgeRag
    from app.contracts import Entrada
    path=Path(__file__).resolve().parent.parent/'corpus_publico'/DCC_SNAPSHOT
    try:
        document=load_snapshot(path,SOURCES)
        # Acronym expansion changes query vocabulary, not the requested predicate.
        query=re.sub(r'\bdcc\b','Conversor de Moedas',message,flags=re.I)
        index=Index([document])
        local=KnowledgeRag(index,reviewed_presentations=False)
        result=local._single(Entrada(message=query,user_id='public_query'),())
        # A particular card is never verified by a public article. If its long
        # individual wording cannot retrieve, show separately labelled general
        # context, retaining limited status instead of claiming that card works.
        if general_context and not result.fontes:
            result=local._single(Entrada(message='Conversor de Moedas Getnet',user_id='public_query'),())
            if result.fontes:result=result.model_copy(update={'status':'limitado'})
        if not result.fontes:return result
        from app.rag.core import evidence_text
        from app.rag.grounding import literal_claims,retained_claims
        from app.rag.quality import relevant_candidates
        # One complete complementary block, chosen from ranked retrieval, not
        # a canned answer. General product context is labelled, never promoted
        # to confirmation of an unsupported predicate or individual condition.
        rows=relevant_candidates('Conversor de Moedas Getnet',index.search('Conversor de Moedas Getnet')['candidates'])
        extra=next((c for c in rows if c['text'] not in result.texto),None)
        if extra is not None:
            addition='\n\nContexto geral complementar da fonte; não confirma condição individual:\n'+evidence_text(extra)+'\nFonte: '+extra['source']+'\nCaptura: '+extra['captured_at']
            if len(result.texto+addition)<=3500:
                text=result.texto+addition
                result=result.model_copy(update={'texto':text,'presentation':[],
                    'grounding':retained_claims([*result.grounding,*literal_claims([extra])],text,result.fontes)})
        return result
    except (OSError,ValueError,KeyError):
        return reply('Não consegui recuperar a fonte literal de conversão nesta execução; não confirmei as condições.',status='sem_evidencia')


def currency_reply(message, *, local=None, defer_retrieval=False):
    text = normalize(message)
    foreign_card_brl=bool(re.search(r'\b(?:cartao|card)\b',text) and re.search(r'\b(?:emitido|issued|estrangeiro|international|internacional)\b',text) and re.search(r'\b(?:reais|brl)\b',text) and re.search(r'\b(?:cobrar|pagar|charge|pay)\b',text))
    if not CURRENCY.search(text) and not foreign_card_brl:
        return None
    if re.search(r'\b(?:calcule|calcular|converta|quanto vale|quanto da|quanto recebo|cotacao|cotacoes|referencia|reference|ptax|bce)\b', text):
        return reply(QUOTE)
    transaction = re.search(r'\b(?:getnet|dcc|tef|venda|vendas|sale|sales|transacao|transaction|cartao|card|conversor)\b', text)
    if transaction:
        if not dcc_available():return reply('A fonte revisada de conversão não está íntegra ou disponível nesta execução; não consigo confirmar essas condições.',status='sem_evidencia')
        from app.brazil_scope import market_of
        market=market_of(message)
        if market.value=='OUT':return reply(REDIRECT)
        if market.value=='UNKNOWN':return reply(CLARIFY_BR)
        if defer_retrieval and getattr(local,'documentary',False):return None
        qualification=('Não consigo confirmar a aceitação nem a moeda de cobrança desse cartão específico com a evidência disponível. A informação revisada abaixo é sobre DCC; não garante aprovação da venda. ' if foreign_card_brl else '')
        result=dcc_retrieved(message,general_context=foreign_card_brl,local=local)
        if result.status=='sem_evidencia' and re.search(r'\b(?:margem|spread|percentual|percentage|markup)\b',text):
            qualification+='Não confirmei a taxa, margem ou percentual de conversão solicitado nas fontes recuperadas; nenhum valor foi inferido. '
        notice='No Brasil, a fonte pública não confirma condições, elegibilidade ou aprovação de uma venda individual. Nenhuma cotação ou operação foi executada. '
        updates={'texto':qualification+notice+result.texto,'presentation':[]}
        if foreign_card_brl and getattr(local,'documentary',False) and result.fontes:
            updates.update(status='limitado',evidence_coverage='partial')
        return result.model_copy(update=updates)
    return reply(CLARIFY)

def service_plan(message, *, state=None, local=None):
    """Particiona obrigações de atendimento antes de consultar fontes ou ferramentas."""
    from app.knowledge import KnowledgeRag
    from app.brazil_scope import scoped_parts, market_of, BUSINESS, CONTINUATION, OUTSIDE
    from app.request_plan import financial_request
    if len(message)>2000:
        return ServicePlan('',(reply('Para consultar as fontes, envie uma pergunta com ate 2000 caracteres. Sua entrada nao foi truncada.'),))
    if KnowledgeRag._suspicious(message):
        return ServicePlan('',(reply('Não sigo instruções para alterar regras ou revelar credenciais. Posso ajudar com produtos, serviços e suporte da Getnet Brasil.',status='recusado'),))
    if state is not None:
        from app.context_reference import reference_clarification
        missing=reference_clarification(message,state)
        if missing:return ServicePlan('',(reply(missing),))
    # Never strip a sensitive clause to make an explicit search eligible.
    if re.search(r'\bpesquise na web\s*:',message,re.I):
        from app.rag.web_search import validate_query
        try:validate_query(message)
        except ValueError:return ServicePlan('',(reply('Use somente uma pergunta pública sobre Getnet Brasil, sem dados pessoais ou credenciais.'),))
    # A dependent help act inherits only an already in-scope business subject.
    dependent_help=re.compile(r'\b(?:ajud\w*|help|orient\w*|proced\w*)\b|\b(?:como|how)\b.{0,30}\b(?:verific\w*|check|continu\w*|prossegu\w*)\b')
    has_context=bool(BUSINESS.search(normalize(message)) or financial_request(message) or (state and state.get('devices')))
    accepted=[]; replies=[]
    for part,market in scoped_parts(message,state=state):
        plain=normalize(part)
        if re.fullmatch(r'(?:(?:minha?|my|a|the)\s+)?(?:senha|password|passphrase|codigo de autenticacao|otp)\b.{0,65}\[credencial removida\][\s,.:]*',plain):
            replies.append(reply(compose_notices(Notice('credentials'))));continue
        if re.search(r'\b(?:onde|where)\b.*\b(?:getnet|opera|atua|operate)\b',plain):
            replies.append(reply(CLARIFY_BR));continue
        if re.fullmatch(r'(?:o que e (?:a )?getnet|what is getnet)',plain):
            replies.append(reply('Posso ajudar com produtos, serviços, vendas, recebimentos e suporte da Getnet Brasil. Qual desses assuntos você quer conhecer?'));continue
        if market=='OUT':
            replies.append(reply(REDIRECT));continue
        if market=='UNKNOWN':
            replies.append(reply(CLARIFY_BR));continue
        if re.search(r'\b(?:voce|you)\b',plain) and re.search(r'\b(?:ia|ai|robo|robot|humano|human|oficial|official|quem|who)\b',plain):
            replies.append(reply(DISCLOSURE));continue
        if re.search(r'\b(?:dela|dele|deles|delas|disso|anterior)\b',plain) and not TOPICS.search(plain) and not (state or TOPICS.search(normalize(re.sub(re.escape(part),'',message,flags=re.I)))):
            replies.append(reply('Não tenho a referência anterior neste endpoint sem sessão. A qual produto ou assunto da Getnet Brasil você se refere?'));continue
        if re.fullmatch(r'(?:qual (?:e )?(?:o |a )?|quanto (?:custa|e) ?)(?:valor|preco|taxa)?',plain.strip()):
            replies.append(reply('A qual produto, serviço ou valor da Getnet Brasil você se refere?'));continue
        if state and state.get('service_boundary',{}).get('mentions') and not state.get('devices') and not state.get('goals') and CONTINUATION.search(plain) and not BUSINESS.search(plain):
            replies.append(reply('Posso continuar com o atendimento Getnet Brasil, mas os detalhes do problema não foram recuperados. Qual problema esse aparelho apresenta?'));continue
        if not (state and state.get('devices')) and re.search(r'\b(?:qual|what|which|record\w*|lembr\w*)\b',plain) and re.search(r'\b(?:informei|relatei|disse|told|reported|registrad\w*|recorded)\b',plain) and CONTINUATION.search(plain):
            replies.append(reply('Não tenho esses relatos recuperados neste atendimento. Qual aparelho e problema da Getnet Brasil você quer retomar?'));continue
        currency=currency_reply(part,local=local,defer_retrieval=bool(getattr(local,'documentary',False)))
        if currency:
            replies.append(currency);continue
        financial=financial_request(part)
        substantive=BUSINESS.search(re.sub(r'\bgetnet\b','',plain))
        if OUTSIDE.search(plain) and not substantive and not financial:
            replies.append(reply(REDIRECT));continue
        if (state is not None and re.fullmatch(r'(?:hoje|ontem|today|yesterday|\d{4}-\d{2}-\d{2})',plain)) or BUSINESS.search(plain) or financial or (has_context and market_of(part).value=='BR') or (state and (state.get('devices') or state.get('goals') or state.get('context')) and not OUTSIDE.search(plain)) or (has_context and (
                (not OUTSIDE.search(plain) and dependent_help.search(plain)) or CONTINUATION.search(plain) or re.search(r'\b(?:codigo|erro|error|code|nao quero|what should i|o que devo|o que faco|como (?:devo |posso )?proceder|qual (?:e )?(?:a )?orientacao)\b',plain)
                or (state and re.fullmatch(r'(?:hoje|ontem|today|yesterday|\d{4}-\d{2}-\d{2})',plain)))):
            accepted.append(part)
        elif re.fullmatch(r'(?:oi|ola|hello|hi|bom dia|boa tarde|boa noite)',plain):
            accepted.append(part)
        else:replies.append(reply(REDIRECT))
    if replies and accepted and all(market_of(part).value=='BR' and not BUSINESS.search(normalize(part)) and not financial_request(part) for part in accepted):
        # Country qualifiers inform the replies above; they are not a second service request.
        accepted=[]
    if not replies:return ServicePlan(message)
    return ServicePlan('. '.join(accepted),tuple({r.texto:r for r in replies}.values()))

def official_result(row):
    """Hosts explícitos; nenhum sufixo arbitrário ou site apenas parecido."""
    url=urlsplit(row['url'])
    return url.scheme=='https' and url.hostname in {
        # Host operacional brasileiro; fontes globais ficam na ingestão offline.
        'site.getnet.com.br',
    } and not url.username and not url.password

def source_market(url):
    parsed=urlsplit(url)
    if parsed.hostname=='site.getnet.com.br':
        return 'Brasil'
    return {'ar':'Argentina','mx':'México','es':'Espanha','pt':'Portugal','uy':'Uruguai'}.get(parsed.path.strip('/').split('/')[0], 'institucional/global; confirme o país aplicável')
