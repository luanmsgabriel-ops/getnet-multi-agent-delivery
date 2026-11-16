"""Bounded public-page evidence from explicit Mwmbl discovery, never a new corpus."""
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlsplit, unquote
import re
import time
from app.public_information import plain, public_url, suspicious, _WORDS, _STOP, WEATHER, CURRENCY
from app.privacy import clean_message


def search_terms(text):
    return set(_WORDS.findall(plain(text))) - _STOP


def bound_search_query(question, query):
    if not isinstance(query,str) or not query.strip() or len(query)>300:
        return False
    if WEATHER.search(plain(question)) or CURRENCY.search(plain(question)):
        return query == question
    terms=search_terms(query)
    return bool(terms) and terms <= search_terms(question) and not clean_message(query)[1] and not suspicious(query) and not re.search(r'https?://|\d{6,}',query)


def untried_queries(question, tried):
    """Bounded literal word spans, never new facts, synonyms or destinations."""
    words=[word for word in re.findall(r"\w+(?:[-'’]\w+)*",question) if plain(word) not in _STOP][:60]
    attempted={frozenset(search_terms(query)) for query in tried}
    choices=[];seen=set()
    # A failed narrow lookup needs a substantially broader topic query,
    # not deletion of one modifier. Preserve original Unicode spelling.
    max_size=min(3,max(1,min((len(search_terms(q)) for q in tried),default=4)//2))
    for size in range(1,max_size+1):
        for start in range(len(words)-size+1):
            query=' '.join(words[start:start+size]);key=frozenset(search_terms(query))
            if key in seen or key in attempted or not bound_search_query(question,query):continue
            seen.add(key);choices.append(query)
    return choices


def read_public_page(url, *, resolver=None, connection_factory=None):
    # Reuse DNS validation and IP-pinned verified TLS. No redirect, proxy,
    # credentials, retry, subresources, scripts or arbitrary user URL.
    from app.rag.fetch import resolve_public, PinnedHTTPS
    if not public_url(url):raise ValueError('Nonpublic URL')
    resolver=resolver or resolve_public
    connection_factory=connection_factory or PinnedHTTPS
    parsed=urlsplit(url);conn=connection_factory(parsed.hostname,resolver(parsed.hostname))
    try:
        path=(parsed.path or '/')+('?' + parsed.query if parsed.query else '')
        conn.request('GET',path,headers={'Host':parsed.hostname,'Accept-Encoding':'identity',
                     'Connection':'close','User-Agent':'GetnetChallengeResearch/0.3'})
        response=conn.getresponse()
        if response.status!=200:raise ValueError('Page unavailable; no redirect or retry')
        if response.getheader('Content-Type','').split(';')[0].strip().lower() not in ('text/html','application/xhtml+xml'):
            raise ValueError('Unsupported page type')
        if response.getheader('Content-Encoding','identity').lower()!='identity':raise ValueError('Unexpected compression')
        limit=1_000_000;length=response.getheader('Content-Length')
        if length and (not length.isdecimal() or int(length)>limit):raise ValueError('Invalid page size')
        raw=response.read(limit+1)
        if not raw or len(raw)>limit or (length and len(raw)!=int(length)):raise ValueError('Truncated or excessive page')
        return {'body':raw,'source':url,'raw_sha256':sha256(raw).hexdigest(),
                'captured_at':datetime.now(timezone.utc).isoformat()}
    finally:
        conn.close()


from html.parser import HTMLParser

class PublicParagraphs(HTMLParser):
    """Only complete prose paragraphs; navigation/link titles are not evidence."""
    from app.rag.core import Editorial as _Editorial
    SKIP=_Editorial.SKIP
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip=0;self.current=None;self.paragraphs=[]
    def handle_starttag(self,tag,attrs):
        if tag in self.SKIP:self.skip+=1
        if not self.skip and tag=='p':self.current=[]
    def handle_endtag(self,tag):
        if tag in self.SKIP and self.skip:self.skip-=1
        if tag=='p' and self.current is not None:
            self.paragraphs.append(''.join(self.current));self.current=None
    def handle_data(self,text):
        if not self.skip and self.current is not None:self.current.append(text)


def page_candidates(page, title, query):
    parser=PublicParagraphs();parser.feed(page['body'].decode('utf-8',errors='strict'))
    terms=search_terms(query);blocks=[];seen=set()
    for raw in parser.paragraphs:
        text=' '.join(raw.split())
        if not 80<=len(text)<=1200 or text in seen:continue
        # A bare hyperlink is discovery metadata, not a supporting paragraph.
        if re.fullmatch(r'https?://\S+',text):continue
        seen.add(text)
        overlap=terms & search_terms(text)
        if not overlap or suspicious(text) or clean_message(text)[1]:continue
        blocks.append((len(overlap),len(text),text))
    return [{'source':page['source'],'title':title,'text':text,
             'captured_at':page['captured_at'],'raw_sha256':page['raw_sha256'],
             'kind':'web_page_excerpt'}
            for _,_,text in sorted(blocks,key=lambda x:-x[0])[:3]]


def ranked_search_rows(rows, query):
    """Prefer a topic article over archive/image/list pages; no factual inference."""
    terms=search_terms(query)
    def rank(row):
        url=row.get('url');title=row.get('title')
        if not public_url(url) or not isinstance(title,str):return (-1,0,0)
        path=unquote(urlsplit(url).path).strip('/').lower()
        leaf=path.rsplit('/',1)[-1].removesuffix('.html')
        index_page=bool(re.search(r'(?:^|/)(?:tag|tags|category|categoria|topics|busca-de-imagens)(?:/|$)',path))
        exact_topic=search_terms(leaf)==terms
        return (int(not index_page),int(exact_topic),len(terms & search_terms(title)))
    return sorted(rows,key=rank,reverse=True)


def grounded_search(question, query, provider, synthesizer, *, reader=read_public_page, deadline=None):
    from app.contracts import RespostaEspecialista
    from app.agentic_client import BudgetExhausted
    from app.rag.grounding import RejectedSynthesis
    from app.public_search import SearchUnavailable
    def result(text,status='sem_evidencia',sources=(),claims=(),coverage='partial',limitation=None):
        return RespostaEspecialista(texto=text,status=status,fontes=list(sources),grounding=list(claims),
            evidence_coverage=coverage,limitation_code=limitation,modo='pesquisa')
    if not bound_search_query(question,query):
        return result('A consulta pública não está vinculada ao pedido; não fiz busca externa.',status='recusado')
    try:batch=provider.search(query)
    except SearchUnavailable as exc:return result(str(exc),status='indisponivel')
    terms=search_terms(query);groups=[];attempts=0;seen=set()
    for row in ranked_search_rows(batch.rows, query):
        if attempts>=2:break
        url=row.get('url');title=row.get('title')
        if not public_url(url) or url in seen or not isinstance(title,str) or not 1<=len(title)<=500:continue
        if not terms & search_terms(title) or suspicious(title) or clean_message(title)[1]:continue
        if deadline is not None and deadline-time.monotonic()<12:break
        seen.add(url);attempts+=1
        try:groups.append(page_candidates(reader(url),title,query))
        except Exception:continue
    candidates=[group[i] for i in range(3) for group in groups if i<len(group)][:3]
    if not candidates:
        return result('A busca não forneceu trechos de páginas pertinentes suficientes. Não confirmei a resposta nem fiz outra busca automática.')
    sources=list(dict.fromkeys(c['source'] for c in candidates))
    try:
        diagnostics={}
        text,sources,claims,complete=synthesizer.synthesize(question,candidates,deadline=deadline,diagnostics=diagnostics)
        return result(text+'\n\nPáginas públicas descobertas via '+batch.provider+' e consultadas nesta execução; a data de captura não comprova atualidade do conteúdo.',
                      status='evidencias' if complete else 'limitado',sources=sources,claims=claims,
                      coverage='supported' if complete else 'partial',
                      limitation='source_insufficient' if not complete and diagnostics.get('evidence_answerability')=='insufficient' else None)
    except RejectedSynthesis as exc:
        if exc.evidence_answerability=='insufficient':
            return result('A checagem do modelo indicou que falta evidência nos trechos recuperados para responder ao pedido integral. A resposta gerada não foi validada; não confirmei a informação.',status='limitado',sources=sources,limitation='source_insufficient')
        if exc.evidence_answerability=='sufficient':
            return result('A checagem indicou que os trechos contêm informação pertinente, mas a resposta gerada não foi validada. Outra busca não corrige por si só essa falha de redação; não confirmei a resposta.',status='limitado',sources=sources,limitation='answer_rejected_with_sufficient_source')
        return result('Recuperei fontes públicas, mas a síntese não foi validada e a suficiência da fonte permanece incerta. Não confirmei a resposta nem repeti a geração.',status='limitado',sources=sources)
    except BudgetExhausted:
        return result('O orçamento do modelo foi esgotado. Há fontes recuperadas, mas nenhuma síntese validada; encerrei sem afirmar cobertura completa.',status='limitado',sources=sources,limitation='budget_exhausted')
    except Exception:
        return result('Recuperei fontes públicas, mas a síntese não foi validada. Não confirmei a resposta nem repeti a geração.',status='limitado',sources=sources)
