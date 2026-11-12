"""Pesquisa publica limitada a Wikipedia; nao substitui fontes de tempo real."""
from datetime import datetime,timezone
from html import unescape
import json
import re
import multiprocessing
from urllib.parse import urlencode
from .fetch import PinnedHTTPS,resolve_public

HOST='pt.wikipedia.org'
MAX_RESPONSE=200_000

def validate_query(query):
    if not isinstance(query,str) or not query.strip() or len(query)>300:
        raise ValueError('Consulta publica exige 1-300 caracteres')
    if re.search(r'https?://|[\w.+-]+@[\w.-]+|\d{6,}|(?:\d[\s.()/+-]*){6,}|\b(senha|password|passcode|credential|cvv|token|cpf|cnpj|api.key)\b',query,re.I):
        raise ValueError('Consulta pode conter dado privado ou destino arbitrario')
    return query.strip()

def _request(query):
    query=validate_query(query)
    path='/w/api.php?'+urlencode({'action':'query','list':'search','srsearch':query,'srlimit':3,'format':'json','utf8':1})
    conn=PinnedHTTPS(HOST,resolve_public(HOST))
    try:
        conn.request('GET',path,headers={'Host':HOST,'User-Agent':'GetnetChallengeResearch/0.3 (educational prototype; no tracking)',
                                       'Accept':'application/json','Accept-Encoding':'identity','Connection':'close'})
        r=conn.getresponse()
        if r.status!=200:raise ValueError('HTTP '+str(r.status))
        if r.getheader('Content-Type','').split(';')[0].strip()!='application/json':raise ValueError('Tipo inesperado')
        if r.getheader('Content-Encoding','identity')!='identity':raise ValueError('Compressao inesperada')
        raw=r.read(MAX_RESPONSE+1)
        if len(raw)>MAX_RESPONSE:raise ValueError('Resposta excessiva')
        return json.loads(raw.decode('utf-8'))
    finally:conn.close()

def _worker(query,sender):
    try:sender.send(('ok',_request(query)))
    except Exception as exc:sender.send(('error',type(exc).__name__))
    finally:sender.close()

def bounded_request(query):
    validate_query(query)
    ctx=multiprocessing.get_context('spawn');receiver,sender=ctx.Pipe(duplex=False)
    process=ctx.Process(target=_worker,args=(query,sender),daemon=True);process.start();sender.close()
    try:
        if not receiver.poll(15):raise TimeoutError('Prazo da busca excedido')
        status,result=receiver.recv()
        if status!='ok':raise ValueError('Servico de pesquisa indisponivel')
        return result
    finally:
        receiver.close();process.join(timeout=1)
        if process.is_alive():process.terminate();process.join(timeout=2)

def clean(text):
    if not isinstance(text,str) or len(text)>4000:raise ValueError('Texto invalido')
    return ' '.join(unescape(re.sub(r'<[^>]*>',' ',text)).split())[:800]

class WikipediaSearch:
    def __init__(self,transport=bounded_request):self.transport=transport
    def search(self,query):
        query=validate_query(query)
        try:
            data=self.transport(query)
            rows=data['query']['search']
            if not isinstance(rows,list) or len(rows)>3:raise ValueError('Schema invalido')
            results=[]
            for row in rows:
                pageid=row['pageid']
                if type(pageid) is not int or pageid<=0:raise ValueError('ID invalido')
                title,snippet=clean(row['title']),clean(row['snippet'])
                if not title or not snippet:continue
                results.append({'title':title,'snippet':snippet,'url':f'https://pt.wikipedia.org/?curid={pageid}'})
            return {'status':'results' if results else 'insufficient_evidence','results':results,
                    'provider':'Wikipedia pt','retrieved_at':datetime.now(timezone.utc).isoformat(),
                    'limitation':'Busca enciclopedica; nao comprova clima, cotacao ou condicoes atuais.'}
        except Exception:
            return {'status':'unavailable','results':[],'provider':'Wikipedia pt'}
