"""Busca básica Tavily: sem geração, retries ou autorização de gasto adicional."""
from contextlib import closing
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from tempfile import gettempdir
from urllib.error import HTTPError
import math,re,sqlite3,time
from app.public_search import SearchBatch,SearchUnavailable,TAVILY_ENDPOINT,TAVILY_USAGE

class TavilyBudget:
    """Teto persistente de dez requisições, incluindo /usage; sem texto ou segredo.

    Não reinicia automaticamente. Custo desconhecido bloqueia novas chamadas.
    Compartilhe o arquivo entre processos; não apague para contornar autorização.
    """
    def __init__(self,path=None):
        self.path=Path(path or Path(gettempdir())/'getnet-challenge/tavily-budget.db')
    def connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        return sqlite3.connect(self.path,timeout=2)
    def reserve(self,operation):
        if operation not in ('usage','search'):raise ValueError('Operação inválida')
        with closing(self.connect()) as db,db:
            db.execute('CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY, operation TEXT, at TEXT, status TEXT, credits REAL)')
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT COUNT(*) FROM calls WHERE status IN ('reserved','blocked')").fetchone()[0]:raise SearchUnavailable('Tavily pausado: uma chamada está em andamento ou seu custo/resultado não foi confirmado. Não fiz nova consulta.')
            if db.execute('SELECT COUNT(*) FROM calls').fetchone()[0]>=10:raise SearchUnavailable('O limite local de dez requisições Tavily foi atingido. Não fiz nova consulta.')
            return db.execute("INSERT INTO calls(operation,at,status,credits) VALUES(?,?,'reserved',NULL)",(operation,datetime.now(timezone.utc).isoformat())).lastrowid
    def finish(self,call_id,credits,blocked=False):
        with closing(self.connect()) as db,db:
            db.execute('UPDATE calls SET status=?,credits=? WHERE id=?',('blocked' if blocked else 'confirmed',credits,call_id))
    def pause(self):
        with closing(self.connect()) as db,db:
            db.execute("UPDATE calls SET status='blocked' WHERE id=(SELECT MAX(id) FROM calls)")

def free_allowance(data):
    """Confirma créditos do plano gratuito; nunca autoriza pay-as-you-go."""
    try:
        account=data['account'];key=data['key']
        if account['current_plan'] not in ('Researcher','Free','free'):raise ValueError()
        fields=(account['plan_usage'],account['plan_limit'],key['usage'],account['paygo_usage'])
        if any(type(x) not in (int,float) or not math.isfinite(x) or x<0 for x in fields):raise ValueError()
        remaining=account['plan_limit']-account['plan_usage']
        limit=key.get('limit')
        if limit is not None:
            if type(limit) not in (int,float) or not math.isfinite(limit):raise ValueError()
            remaining=min(remaining,limit-key['usage'])
        if account['paygo_usage']!=0 or remaining<10:raise ValueError()
        return remaining
    except (KeyError,TypeError,ValueError):
        raise SearchUnavailable('Não confirmei plano gratuito e margem de créditos Tavily suficientes. Nenhuma busca foi realizada; confira plano e consumo antes de continuar.') from None

class TavilySearch:
    def __init__(self,transport,key,budget=None,*,clock=time.monotonic):
        self.transport,self._key,self.budget=transport,key,budget or TavilyBudget()
        self.clock=clock;self._free_until=0;self._remaining=0
    def _request(self,operation,body=None):
        call_id=self.budget.reserve(operation)
        endpoint=TAVILY_USAGE if operation=='usage' else TAVILY_ENDPOINT
        credits=None
        try:
            options={'method':'POST','body':body} if operation=='search' else {}
            data=self.transport(endpoint,{}, {'Authorization':'Bearer '+self._key},**options)
            credits=0 if operation=='usage' else data.get('usage',{}).get('credits')
            if type(credits) not in (int,float) or credits!=(0 if operation=='usage' else 1):
                raise ValueError('Consumo não confirmado')
            self.budget.finish(call_id,credits)
            return data
        except Exception as exc:
            known=credits if type(credits) in (int,float) and math.isfinite(credits) and credits>=0 else None
            self.budget.finish(call_id,known,blocked=True)
            if isinstance(exc,HTTPError) and exc.code in (401,403):message='Chave Tavily ausente, inválida ou sem permissão.'
            elif isinstance(exc,HTTPError) and exc.code in (429,432,433):message='Tavily recusou a consulta por limite de uso.'
            else:message='Tavily indisponível ou com resposta/consumo não confirmado.'
            raise SearchUnavailable(message+' Novas chamadas foram pausadas; sem retries ou troca de provedor.') from None
    def search(self,query):
        if not self._key:raise SearchUnavailable('Busca Tavily não configurada: falta TAVILY_API_KEY. Não fiz consulta.')
        if self.clock()>=self._free_until or self._remaining<1:
            usage=self._request('usage')
            try:self._remaining=free_allowance(usage)
            except SearchUnavailable:
                self.budget.pause()
                raise
            self._free_until=self.clock()+60
        # Texto já passou pela privacidade da entrada; nunca envia sessão/documentos.
        language='pt' if re.search(r'[áàâãéêíóôõúç]|\b(?:como|qual|que|explique)\b',query,re.I) else 'en'
        payload={'query':query,'search_depth':'basic','topic':'general','chunks_per_source':1,'max_results':5,
                 'auto_parameters':False,'include_answer':False,'include_raw_content':False,'include_images':False,
                 'include_usage':True,'include_published_date':True,'safe_search':True,'language':language}
        data=self._request('search',payload);self._remaining-=1
        rows=data.get('results') if isinstance(data,dict) else None
        if not isinstance(rows,list) or len(rows)>5:
            self.budget.pause()
            raise SearchUnavailable('Tavily retornou resultados em estrutura inválida. Novas chamadas pausadas; não confirmei uma resposta.')
        normalized=[]
        for row in rows:
            if not isinstance(row,dict):continue
            stamp=row.get('published_date');date_label=None
            if isinstance(stamp,str) and len(stamp)<=80:
                try:date_label=parsedate_to_datetime(stamp).isoformat()
                except (TypeError,ValueError,OverflowError):
                    try:date_label=datetime.fromisoformat(stamp).isoformat()
                    except ValueError:pass
            normalized.append({'url':row.get('url'),'title':row.get('title'),'description':row.get('content'),'published_date':date_label})
        return SearchBatch('Tavily',normalized,'Busca básica, 1 crédito informado pelo provedor. Trechos retornados pelo Tavily, sem resposta gerada e sem leitura integral pela aplicação. Datas, quando presentes, são estimativas do provedor, não garantia de atualidade.')
