"""Catálogo de páginas oficiais, complementar à descoberta RSS.

URLs/seletores versionados; corpo consultado por HTTPS limitado. Resultados são
informações públicas, nunca instruções do agente ou autorização para agir.
"""
from html.parser import HTMLParser
from html import unescape
from datetime import datetime,timezone
import re
from app.intents import normalize

BR_LINK='https://site.getnet.com.br/link-de-pagamento/'
BR_ADVANCE='https://site.getnet.com.br/get-ajuda-antecipacao-de-venda/como-antecipar-sua-vendas-pelo-app/'
PRODUCT_PAGES=(BR_LINK,)
HTML_LIMIT=2_000_000

class ProductText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.parts=[];self.skip=0;self.heading=False;self.titles=[];self.title=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','nav','footer','form','noscript','template','svg','head'}:self.skip+=1
        if self.skip:return
        if tag=='h1':self.heading=True;self.title=[]
        if tag in {'h1','h2','h3','h4','p','li','br','div'}:self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in {'script','style','nav','footer','form','noscript','template','svg','head'} and self.skip:self.skip-=1
        if self.skip:return
        if tag=='h1':self.heading=False;self.titles.append(' '.join(''.join(self.title).split()))
        if tag in {'h1','h2','h3','h4','p','li','div'}:self.parts.append('\n')
    def handle_data(self,text):
        if not self.skip:
            self.parts.append(text)
            if self.heading:self.title.append(text)


def extract_product(raw,url):
    if url not in PRODUCT_PAGES or not isinstance(raw,bytes) or not 0<len(raw)<=HTML_LIMIT:raise ValueError('Product document limit/origin')
    html=raw.decode('utf-8','strict');parser=ProductText();parser.feed(html)
    lines=[' '.join(x.split()) for x in ''.join(parser.parts).splitlines() if x.strip()]
    titles=[x for x in parser.titles if 'link de pag' in normalize(x)]
    if len(titles)!=1:raise ValueError('Product title missing/ambiguous')
    def section(start,end):
        a=lines.index(start);b=lines.index(end,a+1);return lines[a:b]
    pairs=[('Benefícios para você vender mais com Link de Pagamento na Black Friday','Venda online de forma prática e segura com Link de Pagamento'),
           ('Termos e condições','Veja como é fácil vender com o Link de Pagamento'),
           ('Veja como é fácil vender com o Link de Pagamento','Dúvidas sobre Link de Pagamento?')]
    chunks=[' '.join(x for x in section(a,b) if x!='Quero contratar') for a,b in pairs]
    if not chunks or any(not 0<len(c)<=1200 for c in chunks):raise ValueError('Editorial block changed or excessive')
    return titles[0],chunks


def product_query(query):
    """Plano de descoberta: país separado do assunto, sem dados privados."""
    from app.rag.scope import retrieval_plan
    from app.rag.web_search import validate_query
    validate_query(query);text=normalize(query);market,_=retrieval_plan(query)
    if market!='BR':return None
    if re.search(r'\blink\b',text):return market,'link de pagamento'
    if re.search(r'\b(?:antecipacao|antecipar|advance)\b',text) and market=='BR':return market,'antecipação de vendas'
    return None


class OfficialCatalogSearch:
    def __init__(self,fetcher=None):
        from app.rag.fetch import fetch_bounded
        self.fetcher=fetcher or fetch_bounded
    def search(self,query):
        from app.rag.web_search import validate_query
        from app.rag.core import snapshot
        validate_query(query);plan=product_query(query);rows=[];attempts=[]
        urls=[] if plan is None else [BR_LINK if plan[1]=='link de pagamento' else BR_ADVANCE]
        for url in urls[:2]:
            try:
                download=self.fetcher(url)
            except Exception:
                attempts.append({'url':url,'status':'unavailable','reason':'transport_failure'});continue
            try:
                doc=snapshot(download)
                # Discovery never promotes external commands to executable procedures.
                text=doc['title']+' '+' '.join(doc['chunks'])
                from app.knowledge import KnowledgeRag
                if KnowledgeRag._suspicious(text) or re.search(r'\b(?:envie|compartilhe|send|share)\b.{0,45}\b(?:senha|password|otp|token)\b',text,re.I):raise ValueError('Untrusted source instructions')
                terms=set(re.findall(r'\w+',normalize(query)))
                ranked=sorted(enumerate(doc['chunks']),key=lambda pair:(-len(terms & set(re.findall(r'\w+',normalize(pair[1])))),pair[0]))
                from app.rag.quality import commercial_attribute, attribute_candidates
                attribute=commercial_attribute(query)
                if attribute:
                    eligible=attribute_candidates(query,[{'title':doc['title'],'text':c} for c in doc['chunks']])
                    if not eligible:
                        attempts.append({'url':url,'status':'insufficient_evidence','reason':'requested_attribute_not_supported'});continue
                    selected=eligible[0]['text']
                else:selected=ranked[0][1]
                conditions=doc['chunks'][1] if url==BR_LINK else ''
                snippet=' '.join(dict.fromkeys(x for x in (selected,conditions) if x))
                # Keep complete paragraph; no deletion of trailing conditions to meet a quota.
                rows.append({'title':doc['title'],'snippet':snippet,'url':doc['final_url'],'market':doc['market'],'body_sha256':doc['raw_sha256']})
                attempts.append({'url':url,'status':'results','raw_sha256':doc['raw_sha256']})
            except ValueError:attempts.append({'url':url,'status':'insufficient_evidence','reason':'editorial_changed_or_untrusted'})
            except Exception:attempts.append({'url':url,'status':'unavailable','reason':'transport_failure'})
        status='results' if rows else 'unavailable' if attempts and all(x['status']=='unavailable' for x in attempts) else 'insufficient_evidence'
        return {'status':status,'results':rows,'provider':'catálogo oficial consultado por HTTPS','retrieved_at':datetime.now(timezone.utc).isoformat(),'attempts':attempts}


def official_search():
    from app.rag.general_web import GeneralWebSearch
    return GeneralWebSearch(official_only=True,catalog=OfficialCatalogSearch())
