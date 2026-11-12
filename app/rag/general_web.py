"""Busca web geral via RSS Bing; snippets sao evidencias de descoberta, nao fatos verificados."""
from datetime import datetime, timezone
import ipaddress
import multiprocessing
import re
from urllib.parse import urlencode, urlsplit
from xml.etree import ElementTree
from .fetch import PinnedHTTPS, resolve_public
from .web_search import validate_query, clean
from app.intents import PUBLIC_QUESTION_PREFIX

HOST = 'www.bing.com'
MAX_BYTES = 200_000
MAX_CANDIDATES = 10
MAX_RESULTS = 3

# Remover a formulação no início, preservando nomes como "The Who" no assunto.
QUESTION_PREFIX = PUBLIC_QUESTION_PREFIX
CONNECTORS = set('o a os as um uma de do da dos das e em no na nos nas por para sobre '
                 'the a an of about and in'.split())
CATEGORIES = set('conceito definicao sistema linguagem programacao documentacao oficial'.split())
ALIASES = {'concept':'conceito','definition':'definicao','system':'sistema','systems':'sistema',
           'sistemas':'sistema','language':'linguagem','languages':'linguagem','linguagens':'linguagem',
           'programming':'programacao','documentation':'documentacao','official':'oficial',
           'algorithm':'algoritmo','algorithms':'algoritmo','algoritmos':'algoritmo',
           'sorting':'ordenacao','sort':'ordenacao'}

# Uma entidade pode ter homônimos: descritores não precisam coincidir literalmente,
# mas o resultado deve fornecer evidência do contexto solicitado, em PT ou EN.
PROGRAMMING_CONTEXT = set('programacao linguagem software code codigo coding codigos '
                          'programador programmer interpreter interpretador compiler compilador '
                          'scripting script scripts computacao computation'.split())
CONTEXT_GROUPS = {
    'programacao': PROGRAMMING_CONTEXT,
    'linguagem': PROGRAMMING_CONTEXT,
    'sistema': set('sistema network rede redes protocolo protocol infrastructure infraestrutura'.split()),
    'documentacao': set('documentacao docs manual manuals guia guide guides reference referencia tutorial tutorials tutoriais'.split()),
}

def subject_words(query):
    from app.intents import normalize
    text = normalize(query).strip()
    while QUESTION_PREFIX.match(text):
        text = QUESTION_PREFIX.sub('', text, count=1)
    return [ALIASES.get(w,w) for w in re.findall(r'[a-z0-9]+',text) if w not in CONNECTORS]

def subject_terms(query):
    words = set(subject_words(query))
    anchors = words - CATEGORIES
    # "programação" e "linguagem de programação" são assuntos, não lixo.
    return anchors or words

def search_query(query):
    """Desambiguar o termo técnico; não embutir resposta nem fonte fictícia."""
    terms = subject_terms(query)
    if 'dns' in terms:
        rest = ' '.join(sorted(terms - {'dns'}))
        return validate_query(('"DNS" "Domain Name System" ' + rest).strip())
    words=set(subject_words(query))
    if 'programacao' in query.casefold() or 'programação' in query.casefold():
        if terms-CATEGORIES:
            return validate_query(' '.join(sorted(terms-CATEGORIES))+' programming language')
    if 'ordenacao' in words and 'algoritmo' in words:
        return validate_query('sorting algorithms')
    from app.intents import normalize
    normalized = normalize(query).strip()
    if QUESTION_PREFIX.match(normalized):
        # Preservar descritores para desambiguar a consulta (Python vs. cobra),
        # mas não mandar "quem foi/what is" como se fosse parte do nome.
        body = normalized
        while QUESTION_PREFIX.match(body):
            body = QUESTION_PREFIX.sub('',body,count=1)
        return validate_query(body.strip(' ?.!'))
    return query

def relevant_result(query, row):
    """Filtro lexical conservador; pertinência não equivale a verdade factual."""
    from app.intents import normalize
    required = subject_terms(query)
    from app.service_policy import official_result, source_market
    from .official_catalog import product_query
    plan=product_query(query) if official_result(row) else None
    if plan:
        expected='Brasil'
        if source_market(row['url'])!=expected:return False
        required=set(plan[1].replace(' de ',' ').split())
        required={normalize(x) for x in required}
        required={'pagamento' if x=='pago' else 'antecipacao' if x=='antecipação' else x for x in required}
        if 'antecipacao' in required:required.discard('vendas')
    text = normalize(row['title'] + ' ' + row['snippet'])
    if plan:text=re.sub(r'\bpago\b','pagamento',text)
    terms = {ALIASES.get(w,w) for w in re.findall(r'[a-z0-9]+', text)}
    if not required or not required <= terms:
        return False
    descriptors = set(subject_words(query)) & CONTEXT_GROUPS.keys()
    if required - CATEGORIES and descriptors:
        # Preservar contexto além do nome; Python/Java por si só não comprovam
        # que o resultado trate de uma linguagem em vez de um animal/lugar.
        for descriptor in descriptors:
            if not terms & CONTEXT_GROUPS[descriptor]:
                return False
    if required <= CATEGORIES and QUESTION_PREFIX.match(normalize(query).strip()):
        # Assunto genérico em uma pergunta conceitual: uma grade de horários
        # pode conter "programação" sem explicar o conceito. Manter acentos
        # aqui distingue "é" de "e" e "são" de um nome como "São Paulo".
        explanation = row['title']+' '+row['snippet']
        if not re.search(r'\b(?:é|significa|consiste|designa|is|are|means|refers|consists|expresses|denotes)\b',explanation,re.I):
            return False
    if 'dns' in required:
        if required == {'dns'}:
            # Pergunta conceitual: não basta uma lista de servidores/recomendação.
            return bool(terms & {'domain','domains','dominio','dominios','names','nomes'}) and bool(
                terms & {'ip','addresses','enderecos'}) and bool(
                terms & {'maps','mapping','translates','translation','converting','converts',
                         'traduz','traducao','converte','conversao','mapeia','resolucao','resolution'})
        # Evitar homônimos comerciais e resultados que só repetem a sigla.
        return bool(terms & {'domain','domains','dominio','dominios','resolver','resolucao','ip','internet'})
    return True

def public_url(url):
    parts = urlsplit(url)
    if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password:
        raise ValueError('URL de resultado invalida')
    if parts.port not in (None, 80, 443) or '.' not in parts.hostname or parts.hostname.endswith(('.local', '.internal', '.localhost')):
        raise ValueError('Destino privado')
    try:
        address = ipaddress.ip_address(parts.hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError('Destino privado')
    return url

def parse_results(raw):
    if len(raw) > MAX_BYTES or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('XML excessivo ou inseguro')
    root = ElementTree.fromstring(raw)
    if root.tag != 'rss':
        raise ValueError('RSS esperado')
    results = []
    for item in root.findall('./channel/item')[:MAX_CANDIDATES]:
        title, snippet = clean(item.findtext('title', '')), clean(item.findtext('description', ''))
        url = public_url(item.findtext('link', ''))
        if title and snippet:
            results.append(dict(title=title, snippet=snippet, url=url))
    return results

def request(query):
    query = validate_query(query)
    conn = PinnedHTTPS(HOST, resolve_public(HOST))
    try:
        parameters = {'q': query, 'format': 'rss'}
        if 'dns' in subject_terms(query):
            # A sigla técnica tem homônimos; mercado explícito estabiliza a busca.
            parameters['mkt'] = 'en-US'
        conn.request('GET', '/search?' + urlencode(parameters),
                     headers={'Host': HOST, 'User-Agent': 'GetnetChallengeResearch/1.0',
                              'Accept-Encoding': 'identity', 'Connection': 'close'})
        response = conn.getresponse()
        if response.status != 200 or response.getheader('Content-Encoding', 'identity') != 'identity':
            raise ValueError('Resposta inesperada; redirects nao seguidos')
        return parse_results(response.read(MAX_BYTES + 1))
    finally:
        conn.close()

def _worker(query, sender):
    try:
        sender.send(('ok', request(query)))
    except Exception:
        sender.send(('error', None))
    finally:
        sender.close()

def bounded_request(query):
    validate_query(query)
    ctx = multiprocessing.get_context('spawn')
    receiver, sender = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_worker, args=(query, sender), daemon=True)
    process.start(); sender.close()
    try:
        if not receiver.poll(15):
            raise TimeoutError('Prazo da busca excedido')
        status, results = receiver.recv()
        if status != 'ok':
            raise ValueError('Busca indisponivel')
        return results
    finally:
        receiver.close(); process.join(timeout=1)
        if process.is_alive():
            process.terminate(); process.join(timeout=2)

class GeneralWebSearch:
    def __init__(self, transport=bounded_request, fallback=None, *, official_only=False, catalog=None):
        self.transport = transport
        self.fallback = fallback
        self.official_only = official_only
        self.catalog = catalog

    def search(self, query):
        # Validar o original ANTES de remover palavras/desambiguar a consulta.
        query = validate_query(query)
        if self.official_only:
            from app.service_policy import service_plan
            policy=service_plan(query)
            if not policy.message:
                return {'status':'insufficient_evidence','results':[],'provider':'scope_policy',
                        'diagnostics':{'scope':'Getnet Brasil'},'retrieved_at':datetime.now(timezone.utc).isoformat()}
            query=policy.message
        failed=False;request_query=query
        try:
            request_query=search_query(query)
            if self.official_only:
                from .official_catalog import product_query
                plan=product_query(query)
                if plan:
                    host='site.getnet.com.br'
                    request_query=validate_query('"'+plan[1]+'" site:'+host)
                else:request_query=validate_query(request_query+' site:site.getnet.com.br')
            results = self.transport(request_query)
            if self.official_only:
                from app.service_policy import official_result
                results=[r for r in results[:MAX_CANDIDATES] if official_result(r)]
            results = [r for r in results[:MAX_CANDIDATES] if relevant_result(query, r)][:MAX_RESULTS]
        except Exception:
            failed=True;results=[]
        provider='Bing RSS'
        diagnostics={'rss_status':'unavailable' if failed else 'results' if results else 'insufficient_evidence','request_query':request_query}
        if not results and self.official_only and self.catalog is not None:
            alternate=self.catalog.search(query)
            from app.service_policy import official_result
            results=[r for r in alternate['results'] if official_result(r) and relevant_result(query,r)][:MAX_RESULTS]
            provider='Bing RSS -> '+alternate['provider']
            diagnostics['catalog']=alternate.get('attempts',[])
            # All available sources must fail transport to call the service unavailable.
            failed=failed and alternate['status']=='unavailable'
        if not results and self.fallback is not None and not self.official_only:
            # Segunda fonte independente, uma tentativa; não afrouxa o filtro
            # nem transforma um snippet irrelevante em resposta. Sem links
            # arbitrários ou contexto privado. Cada transporte mantém seu prazo.
            from app.intents import normalize
            subject=normalize(query).strip()
            while QUESTION_PREFIX.match(subject):
                subject=QUESTION_PREFIX.sub('',subject,count=1)
            try:
                alternate=self.fallback.search(validate_query(subject.strip(' ?.!')))
                results=[r for r in alternate['results'][:MAX_CANDIDATES] if relevant_result(query,r)][:MAX_RESULTS]
                provider='Bing RSS -> Wikipedia pt'
                failed=alternate['status']=='unavailable'
            except Exception:failed=True
        return {'status':'results' if results else 'unavailable' if failed else 'insufficient_evidence',
                'results':results,'provider':provider,'diagnostics':diagnostics,'retrieved_at':datetime.now(timezone.utc).isoformat()}
