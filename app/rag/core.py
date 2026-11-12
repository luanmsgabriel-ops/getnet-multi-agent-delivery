"""Snapshots publicos persistidos, extracao editorial e busca lexical limitada."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import json
import math
import os
import re
import tempfile
import unicodedata

MAX_QUERY = 2000
MAX_BYTES = 1_000_000
MAX_CHUNKS = 5000
MAX_CORPUS_CHARS = 5_000_000
STOP = set('a o as os um uma de do da dos das em no na nos nas e ou que qual quais como para por com eu meu minha se ao pelo pela'.split())


def evidence_text(candidate):
    """Apresenta título e corpo juntos: o título também pode restringir a oferta."""
    title = candidate.get('title', '').strip()
    text = candidate['text']
    if not title or text == title or text.startswith(title + '\n'):
        return text
    return title + '\n' + text


def tokens(text):
    text = ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))
    text = re.sub(r'\bwi[\s-]+fi\b', 'wifi', text)
    return set(re.findall(r'[a-z0-9]+', text)) - STOP


# Lexico de dominio aplicado a consultas, nao respostas prontas dos cenarios.
QUERY_EN_STOP = set("what whats how many can i do does the a an is are to into with through via my of for be will from in on it should and difference differences between compare comparison".split())
QUERY_PT_STOP = set('quantas quantos quanto posso pode fazer preciso ajuda quero gostaria sobre diferenca diferencas comparar comparacao entre'.split())
QUERY_TRANSLATIONS = {'installments':'parcelas','instalments':'parcelas','installment':'parcelas',
    'split':'dividir','sale':'venda','sales':'venda','vendas':'venda','pago':'pagamento','pagos':'pagamento','cuotas':'parcelas','card':'cartao','cards':'cartoes',
    'transaction':'transacao','transactions':'transacoes','decline':'negada','declined':'negada','showing':'mostrando','error':'erro','machine':'maquininha','connect':'conexao','connection':'conexao','bank':'bancaria','account':'conta','receive':'receber',
    'advance':'antecipacao','receivables':'recebiveis','payment':'pagamento','link':'link',
    'fees':'taxas','fee':'taxa','interest':'juros','limit':'limite','limits':'limite',
    'maximum':'limite','maximo':'limite','maxima':'limite','parcelamento':'parcelas',
    'prestacoes':'parcelas','prestacao':'parcelas',
    'recusada':'negada','recusado':'negada',
    'maquina':'maquininha','conectar':'conexao','conecta':'conexao','conectando':'conexao',
    'conectou':'conexao','conectada':'conexao','conectado':'conexao',
    'desconectada':'conexao','desconectado':'conexao','offline':'conexao',
    'allow':'permitido','available':'disponivel','getnet':'getnet'}

# Marca, datas e formulação não substituem o assunto pedido.
QUERY_CONTEXT = set('s getnet getnets get novidade novidades noticia noticias news latest new atual atualizada atualizado atualizacoes informacao informacoes information saber gostaria explicar explique funciona funcionam funciona works work ter tenho precisa necessario need about regarding favor favorzinho'.split())


def subject_tokens(text):
    return {t for t in query_tokens(text) - QUERY_CONTEXT if not t.isdigit()}


def query_tokens(text):
    terms=tokens(text)
    if {'quantas','vezes'} <= terms and terms & {'crediario','parcelamento','parcelas'}:
        terms = (terms - {'vezes'}) | {'parcelas'}
    return {QUERY_TRANSLATIONS.get(t,t) for t in terms if t not in QUERY_EN_STOP | QUERY_PT_STOP}


class Editorial(HTMLParser):
    SKIP = {'script', 'style', 'nav', 'footer', 'form', 'noscript', 'template', 'svg', 'head'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.depth, self.in_title, self.title = [], 0, False, []
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP: self.depth += 1
        if not self.depth:
            if tag == 'h1': self.in_title = True
            if tag in {'h1','h2','h3','p','li','br','div'}: self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth: self.depth -= 1
        if not self.depth:
            if tag == 'h1': self.in_title = False
            if tag in {'h1','h2','h3','p','li','div'}: self.parts.append('\n')
    def handle_data(self, text):
        if not self.depth:
            self.parts.append(text)
            if self.in_title: self.title.append(text)


def extract(raw, marker='Respondeu a sua duvida?', start_marker=None):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise ValueError('Snapshot vazio ou excessivo')
    parser = Editorial()
    parser.feed(raw.decode('utf-8', errors='strict'))
    title = ' '.join(''.join(parser.title).split())
    if not title or len(title) > 500: raise ValueError('Titulo editorial ausente ou ambiguo')
    lines = [' '.join(line.split()) for line in ''.join(parser.parts).splitlines() if line.strip()]
    try:
        start = lines.index(start_marker or title)
        end = next(i for i in range(start+1, len(lines)) if tokens(lines[i]) == tokens(marker))
    except (ValueError, StopIteration) as exc:
        raise ValueError('Limite editorial ausente: revisar fonte/extrator') from exc
    body = ' '.join(re.sub(r'^(\d+)\.\s+\1\.\s+', r'\1. ', line) for line in lines[start if start_marker else start+1:end])
    if not body: raise ValueError('Conteudo editorial vazio')
    chunks, current = [], ''
    # Preservar frases completas quando couberem; frases longas sao partidas por palavras.
    for sentence in re.split(r'(?<=[.!?])\s+', body):
        units = [sentence] if len(sentence) <= 1200 else sentence.split()
        for word in units:
            if len(word) > 1200: raise ValueError('Token excessivo')
            if current and len(current)+1+len(word) > 1200:
                chunks.append(current); current = ''
            current = (current+' '+word).strip()
    if current: chunks.append(current)
    return title, chunks


def document_market(url):
    from urllib.parse import urlsplit
    host=urlsplit(url).hostname
    return 'GLOBAL' if host=='www.getnet.net' else 'BR'


def snapshot(download):
    url = download['final_url']
    market = document_market(url)
    from .official_catalog import PRODUCT_PAGES, extract_product
    if url == 'https://site.getnet.com.br/duvidas/':
        from .pix_faq import extract_pix_faq
        title, chunks = extract_pix_faq(download['body'])
    elif url in PRODUCT_PAGES:
        title,chunks=extract_product(download['body'],url)
    elif market == 'GLOBAL':
        title, chunks = extract(download['body'], marker='BUILT FOR EVERY BUSINESS')
        # Presença institucional é um bloco separado da oferta comercial.
        # Fonte alterada sem esse marcador deve ser revista, nunca inferida.
        parser = Editorial(); parser.feed(download['body'].decode('utf-8', errors='strict'))
        lines = [' '.join(line.split()) for line in ''.join(parser.parts).splitlines() if line.strip()]
        presence = [line for line in lines if line.startswith('With presence in ')]
        if len(presence) != 1 or not 1 <= len(presence[0]) <= 1200:
            raise ValueError('Bloco de presença global ausente ou ambíguo')
        chunks.append(presence[0])
    elif url == 'https://site.getnet.com.br/crediario/':
        title, chunks = extract(download['body'], marker='ainda tem dúvidas?',
                                start_marker='Como eu contrato o Crediário e qual a taxa?')
        # Preservar oferta E ressalva juntas; iniciar apenas na FAQ omitia o teto.
        _, offer = extract(download['body'],
                           marker='mais vendas para você, mais vantagens para o seu cliente',
                           start_marker='Crediário')
        chunks = offer + chunks
        title = 'Crediário: perguntas frequentes'
    else:
        title, chunks = extract(download['body'])
    return dict(version=1, requested_url=download['requested_url'], final_url=download['final_url'],
                captured_at=download['captured_at'], raw_sha256=download['raw_sha256'],
                title=title, chunks=chunks, market=market, reviewed=False)


def save_snapshot(data, directory):
    """Grava atomica sem sobrescrever arquivo arbitrario; publica apenas metadados/texto."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).encode('utf-8')
    if len(payload) > MAX_BYTES: raise ValueError('Snapshot processado excessivo')
    envelope = json.dumps({'sha256':sha256(payload).hexdigest(), 'payload':data}, ensure_ascii=False, sort_keys=True)
    name = sha256(data['requested_url'].encode()).hexdigest()+'.json'
    target = directory / name
    fd, temp = tempfile.mkstemp(dir=directory, prefix='.snapshot-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(envelope); f.flush(); os.fsync(f.fileno())
        os.replace(temp, target)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    return target


def load_snapshot(path, allowed_urls):
    path = Path(path)
    if path.stat().st_size > 2*MAX_BYTES: raise ValueError('Arquivo excessivo')
    envelope = json.loads(path.read_text(encoding='utf-8-sig'))
    data = envelope['payload']
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).encode('utf-8')
    if sha256(payload).hexdigest() != envelope['sha256']: raise ValueError('Integridade divergente')
    required = {'version','requested_url','final_url','captured_at','raw_sha256','title','chunks','market','reviewed'}
    if set(data) != required or type(data['version']) is not int or data['version'] != 1: raise ValueError('Schema invalido')
    if data['requested_url'] not in allowed_urls or data['final_url'] not in allowed_urls:
        raise ValueError('Origem nao aprovada')
    if not isinstance(data['title'], str) or not 1 <= len(data['title']) <= 500: raise ValueError('Titulo invalido')
    if not isinstance(data['chunks'],list) or not data['chunks'] or len(data['chunks']) > MAX_CHUNKS:
        raise ValueError('Fragmentos invalidos')
    if any(not isinstance(c,str) or not 1 <= len(c) <= 1200 for c in data['chunks']): raise ValueError('Fragmento invalido')
    if not isinstance(data['raw_sha256'],str) or not re.fullmatch(r'[0-9a-f]{64}',data['raw_sha256']): raise ValueError('Hash invalido')
    date = datetime.fromisoformat(data['captured_at'])
    if date.tzinfo is None or date > datetime.now(timezone.utc): raise ValueError('Captura invalida')
    if data['market'] not in ('BR','GLOBAL') or type(data['reviewed']) is not bool: raise ValueError('Metadados invalidos')
    return data


class Index:
    def __init__(self, documents):
        if len(documents) > 100: raise ValueError('Corpus excessivo')
        self.entries, total = [], 0
        seen = set()
        fingerprints = set()
        for doc in documents:
            if doc['requested_url'] in seen: raise ValueError('Fonte duplicada')
            seen.add(doc['requested_url'])
            if not doc['reviewed']: raise ValueError('Fonte precisa de revisao explicita')
            expected_market = document_market(doc['final_url'])
            if doc['market'] != expected_market: raise ValueError('Mercado incoerente com origem')
            fingerprint = (doc['final_url'], tuple(doc['chunks']))
            if fingerprint in fingerprints: continue
            fingerprints.add(fingerprint)
            for i, text in enumerate(doc['chunks']):
                total += len(text)+len(doc['title'])
                if total > MAX_CORPUS_CHARS or len(self.entries) >= MAX_CHUNKS: raise ValueError('Orcamento corpus excedido')
                self.entries.append(dict(text=text, source=doc['final_url'], title=doc['title'],
                                         captured_at=doc['captured_at'], market=doc['market'], ordinal=i))
        self.terms = []
        for entry in self.entries:
            terms_ = tokens(entry['title']+' '+entry['text'])
            if entry['market'] == 'GLOBAL':
                # A entidade também está na origem oficial, mesmo se faltar no h1.
                from urllib.parse import urlsplit
                terms_ |= tokens(urlsplit(entry['source']).hostname or '')
            # Mesma normalização de domínio em pergunta e documento, mantendo originais.
            terms_ |= {QUERY_TRANSLATIONS.get(t,t) for t in terms_}
            self.terms.append(terms_)
        counts = Counter(t for terms_ in self.terms for t in terms_)
        self.idf = {t:math.log(1+len(self.terms)/(1+n)) for t,n in counts.items()}

    def search(self, query, *, market='BR'):
        if not isinstance(query,str) or not 1 <= len(query) <= MAX_QUERY or not query.strip(): raise ValueError('Consulta 1-2000 caracteres nao vazios')
        if market not in ('BR','GLOBAL'): raise ValueError('Mercado invalido')
        if not self.entries: return dict(status='unavailable', candidates=[])
        if not any(e['market']==market for e in self.entries): return dict(status='insufficient_evidence', candidates=[])
        q, ranked = query_tokens(query), []
        anchors = subject_tokens(query)
        from .quality import predicate_supported
        for entry, terms_ in zip(self.entries,self.terms):
            if entry['market'] != market: continue
            code = re.search(r'ADQ\s+(\d+)[- ](\d+)', entry['title'], re.I)
            if code and not {'adq',code[1],code[2]}.issubset(q): continue
            overlap = q & terms_
            # Datas e entidade não contam como cobertura do assunto central.
            coverage = len(anchors & terms_)/len(anchors) if anchors else len(overlap)/len(q) if q else 0
            years = {t for t in q if re.fullmatch(r'20\d{2}', t)}
            # Notícias pedem conteúdo sobre o assunto, não só um título ou data.
            news = tokens(query) & {'novidade','novidades','noticia','noticias','news'}
            body_terms = query_tokens(entry['text'])
            topic_in_body = not news or not anchors or len(anchors & body_terms)/len(anchors) >= 0.5
            if q and coverage >= 0.5 and topic_in_body and years <= terms_ and predicate_supported(query, entry):
                ranked.append((sum(self.idf[t] for t in sorted(overlap)),entry))
        ranked.sort(key=lambda item:(-item[0],item[1]['source'],item[1]['ordinal']))
        return dict(status='candidates' if ranked else 'insufficient_evidence', candidates=[e for _,e in ranked[:3]])

    def answer_extractive(self, query, *, market='BR'):
        """Baseline sem LLM: evidencia citada, nao simula compreensao/verificacao factual."""
        result = self.search(query, market=market)
        if result['status'] != 'candidates': return dict(**result, answer=None, mode='extractive')
        first = result['candidates'][0]
        return dict(**result, answer='Trecho da fonte (relevancia a confirmar). Siga instrucoes de autenticacao somente no portal oficial; nunca informe senhas nesta conversa. '+evidence_text(first), mode='extractive')
