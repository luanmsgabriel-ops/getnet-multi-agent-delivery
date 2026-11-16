"""Provedores substituíveis de descoberta; nenhum resultado autoriza ações."""
from dataclasses import dataclass
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import gettempdir
from typing import Protocol
import os
import sqlite3
import time
from urllib.error import HTTPError

MWMBL_ENDPOINT = 'https://api.mwmbl.org/api/v2/search/'
BRAVE_ENDPOINT = 'https://api.search.brave.com/res/v1/web/search'
TAVILY_ENDPOINT = 'https://api.tavily.com/search'
TAVILY_USAGE = 'https://api.tavily.com/usage'

class SearchUnavailable(Exception):
    """Somente mensagem pública fixa; nunca inclui exceção ou chave do transporte."""

@dataclass(frozen=True)
class SearchBatch:
    provider: str
    rows: list
    notice: str

class SearchProvider(Protocol):
    def search(self, query: str) -> SearchBatch: ...

def configuration(env):
    provider=env.get('GETNET_PUBLIC_SEARCH','disabled').strip().lower()
    if provider not in ('mwmbl','brave','tavily','disabled'):
        raise ValueError('GETNET_PUBLIC_SEARCH deve ser mwmbl, brave, tavily ou disabled.')
    return {'provider':provider,'available_without_key':provider=='mwmbl',
            'configured':provider=='mwmbl' or (provider=='brave' and bool(env.get('BRAVE_SEARCH_API_KEY','').strip())) or (provider=='tavily' and bool(env.get('TAVILY_API_KEY','').strip())),
            'automatic_fallback':False}

def supervisor_configuration(env):
    """Política efetiva compartilhada por execução e diagnóstico, sem rede.

    A seleção explícita de Mwmbl permite a demonstração gratuita. Provedores
    com chave continuam pausados; disponibilidade de uma chave não autoriza uso.
    """
    selected = configuration(env)
    if selected['provider'] in ('disabled', 'mwmbl'):
        return selected
    return {**configuration({'GETNET_PUBLIC_SEARCH': 'disabled'}),
            'requested_provider': selected['provider'], 'reason': 'paid_search_paused'}

class AnonymousBudget:
    """Contador mensal local e espaçamento entre processos que compartilhem o arquivo.

    Não conhece o uso de outros dispositivos no mesmo IP. O limite remoto
    continua soberano. Reserva tentativas antes da rede, inclusive falhas.
    Não persiste consulta, resposta, usuário ou IP.
    """
    def __init__(self,path=None,*,clock=time.time,cap=50,interval=1.1):
        self.path=Path(path or Path(gettempdir())/'getnet-challenge/mwmbl-usage.db')
        self.clock,self.cap,self.interval=clock,cap,interval
    def reserve(self):
        now=self.clock();month=datetime.fromtimestamp(now,timezone.utc).strftime('%Y-%m')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path,timeout=2)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS usage(month TEXT PRIMARY KEY, attempts INTEGER NOT NULL, last REAL NOT NULL)')
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT attempts,last FROM usage WHERE month=?',(month,)).fetchone()
            attempts,_=row or (0,0)
            last=db.execute('SELECT COALESCE(MAX(last),0) FROM usage').fetchone()[0]
            if attempts>=self.cap:raise SearchUnavailable('O limite local de 50 tentativas mensais da busca pública foi atingido. Não fiz nova consulta; o limite remoto por IP também se aplica.')
            if now-last<self.interval:raise SearchUnavailable('A busca pública exige intervalo entre consultas. Aguarde ao menos dois segundos e tente novamente; não fiz nova consulta.')
            db.execute('INSERT INTO usage VALUES(?,?,?) ON CONFLICT(month) DO UPDATE SET attempts=excluded.attempts,last=excluded.last',(month,attempts+1,now))

class MwmblSearch:
    def __init__(self,transport,budget=None):self.transport,self.budget=transport,budget or AnonymousBudget()
    def search(self,query):
        self.budget.reserve()
        try:data=self.transport(MWMBL_ENDPOINT,{'q':query})
        except HTTPError as exc:
            if exc.code==429:raise SearchUnavailable('Mwmbl recusou a consulta por limite de uso (429). Não houve retry ou troca automática de provedor.') from None
            raise SearchUnavailable('Mwmbl está indisponível nesta consulta. Não confirmei a resposta e não troquei automaticamente de provedor.') from None
        except Exception:
            raise SearchUnavailable('Mwmbl está indisponível ou retornou dados inválidos. Não confirmei a resposta; não houve retry.') from None
        rows=data.get('results') if isinstance(data,dict) else None
        if not isinstance(rows,list) or len(rows)>100:raise SearchUnavailable('Mwmbl retornou uma estrutura inválida. Não confirmei a resposta.')
        normalized=[]
        for row in rows:
            if not isinstance(row,dict):continue
            origin=row.get('engine')
            origin=origin if origin in ('mwmbl','wikipedia','user','google','eusp') else 'não informada'
            normalized.append({'url':row.get('url'),'title':row.get('title'),'description':row.get('content'),'engine':origin})
        return SearchBatch('Mwmbl',normalized,
            'Resultados via Mwmbl, licença informada CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/); direitos das fontes originais preservados. Uso desta integração limitado à demonstração não comercial. O índice não informa data de publicação/captura de cada resultado.')

class BraveSearch:
    def __init__(self,transport,key,*,mock_response=None):
        self.transport,self.key,self.mock_response=transport,key,mock_response
    def search(self,query):
        if not self.key:raise SearchUnavailable('A busca web geral Brave não está configurada: falta BRAVE_SEARCH_API_KEY. Não fiz pesquisa nem confirmei a resposta.')
        if self.mock_response is None:raise SearchUnavailable('Brave real desativado: orcamento equivalente ainda nao implementado. Nenhuma consulta realizada.')
        data=self.mock_response
        rows=data.get('web',{}).get('results',[])
        if not isinstance(rows,list) or len(rows)>20:raise SearchUnavailable('Brave retornou uma estrutura inválida. Não confirmei a resposta.')
        return SearchBatch('Brave',rows,'Resumos fornecidos pelo Brave Search.')

class DisabledSearch:
    def search(self,query):raise SearchUnavailable('Busca geral desativada nesta configuração. Não fiz consulta externa. Tavily ou Brave exigem seleção e chave próprias; Mwmbl é uma opção experimental.')

def build_provider(transport,env=None):
    env=os.environ if env is None else env
    chosen=configuration(env)['provider']
    if chosen=='brave':return BraveSearch(transport,env.get('BRAVE_SEARCH_API_KEY','').strip())
    if chosen=='tavily':
        from app.tavily_search import TavilySearch,TavilyBudget
        return TavilySearch(transport,env.get('TAVILY_API_KEY','').strip(),TavilyBudget(env.get('GETNET_TAVILY_LEDGER') or None))
    if chosen=='disabled':return DisabledSearch()
    return MwmblSearch(transport,AnonymousBudget(env.get('GETNET_PUBLIC_SEARCH_LEDGER') or None))
