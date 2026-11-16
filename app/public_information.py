"""Informação pública: APIs tipadas e descoberta web, sem executar conteúdo externo.

Open-Meteo e Mwmbl são usados para demonstração não comercial. Brave requer
seleção explícita e pode cobrar. Este adaptador não compra créditos nem faz retries.
"""
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.parse import urlencode, quote, urlsplit, unquote, parse_qsl
from html import unescape
import ipaddress
import json
import math
import os
import re
import unicodedata
from app.contracts import RespostaEspecialista
from app.privacy import clean_message

ENDPOINTS = {
    'geo': 'https://geocoding-api.open-meteo.com/v1/search',
    'weather': 'https://api.open-meteo.com/v1/forecast',
    'fx': 'https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)',
    'search': 'https://api.search.brave.com/res/v1/web/search',
    'mwmbl': 'https://api.mwmbl.org/api/v2/search/',
    'tavily': 'https://api.tavily.com/search',
    'tavily_usage': 'https://api.tavily.com/usage',
}
MAX_BYTES = 250_000
WEATHER = re.compile(r'\b(?:clima|weather|forecast|meteorolog\w*|temperatura|temperature|chuva|chover|previsao do tempo)\b|\bprevisao\s+(?:em|para)\b|\b(?:como (?:esta|estara|ficara|vai estar)|qual (?:e|sera))\s+o tempo\b')
STATES = dict(zip('ac al ap am ba ce df es go ma mt ms mg pa pb pr pe pi rj rn rs ro rr sc sp se to'.split(),
    ['acre','alagoas','amapa','amazonas','bahia','ceara','distrito federal','espirito santo','goias','maranhao','mato grosso','mato grosso do sul','minas gerais','para','paraiba','parana','pernambuco','piaui','rio de janeiro','rio grande do norte','rio grande do sul','rondonia','roraima','santa catarina','sao paulo','sergipe','tocantins']))
CURRENCY = re.compile(r'\b(?:cotacao|cambio|exchange|eur|euro|euros|usd|dolar|dollar|gbp|libra)\b')
_WORDS = re.compile(r'\b[a-z0-9]{3,}\b')
_STOP = set('como que qual quais quando onde para uma um dos das de do da os as the what how is are does about explique explain funciona pesquisar pesquise busca search web hoje today atual current'.split())
_STOP.update('why which who when where from with without during than then into between different difference show shows other also through this that these those have has had can could would should will shall month months significa significado por porque pelo pela sobre entre seja ser sao foi tem ter tambem apenas latest recent recentest new novidades atuais'.split())

def plain(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))

def suspicious(text):
    from app.knowledge import KnowledgeRag
    p = plain(text)
    return KnowledgeRag._suspicious(text) or bool(re.search(
        r'(ignore|disregard|forget).{0,60}(previous|instructions|rules)|'
        r'(envie|send|compartilhe|share).{0,50}(senha|password|token|credential)|'
        r'\b(system|assistant|developer)\s*:', p))

def ambiguous_options(text):
    """Alternativas de questionário não são afirmações confirmadas.

    Descarta o fragmento inteiro, sem escolher gabarito ou reescrever seu sentido.
    Listas alfabéticas legítimas também podem exigir outra fonte; passos numéricos
    não são rejeitados por este controle de formato.
    """
    options=re.findall(r'(?:^|[\s:;])\(?([a-f])[).]\s',text,re.I)
    return len({x.lower() for x in options})>=2

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirecionamento não permitido')

def request_json(endpoint, params, headers=None, *, method='GET', body=None):
    """Host/path são internos. Sem proxy ambiente, redirects, retries ou TLS relaxado."""
    if endpoint not in ENDPOINTS.values():
        raise ValueError('Endpoint não permitido')
    if method not in ('GET','POST') or (method=='POST' and endpoint!=ENDPOINTS['tavily']):raise ValueError('Método não permitido')
    if method=='GET' and body is not None:raise ValueError('Corpo inesperado')
    raw_body=json.dumps(body,ensure_ascii=False).encode('utf-8') if body is not None else None
    if raw_body and len(raw_body)>20_000:raise ValueError('Pedido excessivo')
    url = endpoint + ('?' + urlencode(params, quote_via=quote) if params else '')
    request = Request(url, data=raw_body,method=method, headers={'User-Agent':'GetnetChallengeFit/1.0',
        **({'Content-Type':'application/json'} if body is not None else {}),
        'Accept':'application/json','Accept-Encoding':'identity', **(headers or {})})
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=10) as response:
        if response.status != 200 or response.headers.get_content_type() != 'application/json':
            raise ValueError('Resposta inválida')
        if response.headers.get('Content-Encoding','identity') != 'identity':
            raise ValueError('Compressão inesperada')
        raw = response.read(MAX_BYTES + 1)
        if not raw or len(raw) > MAX_BYTES:
            raise ValueError('Resposta vazia ou excessiva')
        data = json.loads(raw.decode('utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Schema inválido')
        return data

def number(value, minimum, maximum):
    if type(value) not in (int,float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError('Valor inválido')
    return value

def public_url(value):
    if not isinstance(value,str) or len(value)>1800:
        return False
    decoded=value
    for _ in range(3):decoded=unquote(decoded)
    if re.search(r'[\s\x00-\x1f\x7f]',decoded) or suspicious(decoded):return False
    try:
        p=urlsplit(value)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):return False
        for key,_ in parse_qsl(urlsplit(decoded).query,keep_blank_values=True):
            if re.search(r'(?:api.?key|token|secret|password|senha|credential|authorization|access.?key)',key,re.I):return False
    except ValueError:return False
    host=p.hostname.lower()
    if '.' not in host or host.endswith(('.local','.internal','.localhost','.test','.invalid')):
        return False
    try: return ipaddress.ip_address(host).is_global
    except ValueError: return True

def reply(text, status='evidencias', sources=()):
    return RespostaEspecialista(texto=text,status=status,fontes=list(sources),modo='pesquisa')

class PublicInformation:
    def __init__(self, transport=request_json, *, clock=None, env=None, search_provider=None, synthesizer=None, page_reader=None):
        self.synthesizer=synthesizer
        self.page_reader=page_reader
        self.transport=transport
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.env=os.environ if env is None else env
        from app.public_search import build_provider
        self.search_provider=search_provider or build_provider(transport,self.env)

    def answer(self,message,*,search_query=None,deadline=None):
        if not isinstance(message,str) or not message.strip() or len(message)>2000:
            return reply('Envie uma pergunta pública de até 2000 caracteres.','limitado')
        safe, removed=clean_message(message)
        without_dates=re.sub(r'\b\d{4}-\d{2}-\d{2}\b','[data]',safe)
        if removed or '[credencial removida]' in safe or re.search(r'[\w.+-]+@[\w.-]+|(?:\d[\s.()/+-]*){8,}|https?://',without_dates):
            return reply('Não envie senhas, dados pessoais ou credenciais para pesquisa pública. Reformule apenas a dúvida pública; não fiz consulta externa.','limitado')
        if re.search(r'\b(?:me chamo|my name is|meu cliente|minha cliente|my customer|cpf|cnpj)\b',plain(safe)):
            return reply('Reformule somente a pergunta pública, sem identificação pessoal ou informações privadas de atendimento. Não fiz consulta externa.','limitado')
        if suspicious(safe):
            return reply('Não sigo instruções para revelar segredos ou alterar regras. Envie apenas a dúvida pública.','recusado')
        p=plain(safe)
        try:
            if WEATHER.search(p):return self.weather(safe)
            if CURRENCY.search(p):return self.exchange(safe)
            if self.synthesizer is not None:
                from app.public_documents import grounded_search, read_public_page
                return grounded_search(safe,search_query or safe,self.search_provider,self.synthesizer,
                    reader=self.page_reader or read_public_page,deadline=deadline)
            return self.search(safe)
        except Exception:
            # Não inclui exception, URL autenticada, payload ou credenciais na resposta.
            return reply('O provedor público está indisponível ou devolveu dados inválidos nesta consulta. Não confirmei a informação solicitada.','indisponivel')

    def weather(self,message):
        p=plain(message)
        location_text=re.sub(r'\b(?:para|for)\s+(?:hoje|amanha|today|tomorrow)\b',' ',p)
        m=re.search(r'\b(?:em|in|para)\s+(.+?)(?=\s+(?:amanha|hoje|tomorrow|today|on|daqui a|in\s+\d|em\s+\d|para\s+\d)|[.?!;]|$)',location_text)
        if not m:return reply('Para qual cidade e estado você quer a previsão, e para qual dia?','limitado')
        city=m.group(1).strip(' .,')
        explicit=re.search(r'\b(\d{4}-\d{2}-\d{2})\b',p)
        offset=2 if 'depois de amanha' in p or 'day after tomorrow' in p else 1 if re.search(r'\b(amanha|tomorrow)\b',p) else 0 if re.search(r'\b(hoje|today)\b',p) else None
        relative=re.search(r'\b(?:daqui a|in)\s+(\d{1,4})\s+(?:dias?|days?)\b',p)
        if relative:offset=int(relative.group(1))
        if offset is not None and offset>15:
            return reply('Esta consulta cobre previsão de hoje até 15 dias à frente. Não confirmei previsão para a data solicitada.','limitado')
        if explicit is None and offset is None:
            return reply('Para qual dia você quer a previsão? Informe hoje, amanhã ou uma data no formato AAAA-MM-DD.','limitado')
        city_parts=[part.strip() for part in city.split(',')]
        city=city_parts[0]
        region=city_parts[1] if len(city_parts)>1 else None
        region=STATES.get(region,region)
        params={'name':city,'count':10,'language':'pt','format':'json','countryCode':'BR'}
        data=self.transport(ENDPOINTS['geo'],params)
        rows=data.get('results',[])
        if not isinstance(rows,list) or len(rows)>10:raise ValueError('Geocoding inválido')
        # GeoNames distingue localidade PPL de sede administrativa PPLA.
        # Excluir PPL fazia cidades reais, como Campinas, desaparecerem.
        places=[x for x in rows if isinstance(x,dict) and x.get('country_code')=='BR' and x.get('feature_code') in ('PPL','PPLC','PPLA','PPLA2','PPLA3','PPLA4')]
        exact=[x for x in places if plain(x.get('name',''))==city]
        places=exact or places
        if region:places=[x for x in places if region==plain(x.get('admin1',''))]
        # Para nome de cidade, uma sede administrativa única precede localidades
        # menores homônimas; duas sedes ou localidades indistintas pedem UF.
        seats=[x for x in places if x.get('feature_code') in ('PPLC','PPLA','PPLA2','PPLA3','PPLA4')]
        if len(seats)==1:places=seats
        if len(places)!=1:
            return reply('Não identifiquei uma cidade brasileira única. Informe cidade e estado; não consultei uma previsão para um local presumido.','limitado')
        place=places[0];tz=ZoneInfo(place['timezone']);today=self.clock().astimezone(tz).date()
        try:target=date.fromisoformat(explicit.group(1)) if explicit else today+timedelta(days=offset)
        except ValueError:return reply('A data informada não é válida. Use AAAA-MM-DD.','limitado')
        if not today<=target<=today+timedelta(days=15):
            return reply('Esta consulta cobre previsão de hoje até 15 dias à frente. Não confirmei previsão para a data solicitada.','limitado')
        lat=number(place['latitude'],-90,90);lon=number(place['longitude'],-180,180)
        args={'latitude':lat,'longitude':lon,'daily':'temperature_2m_max,temperature_2m_min,precipitation_probability_max','timezone':place['timezone'],'start_date':target.isoformat(),'end_date':target.isoformat()}
        forecast=self.transport(ENDPOINTS['weather'],args)
        daily=forecast['daily'];units=forecast['daily_units']
        if daily['time']!=[target.isoformat()] or forecast['timezone']!=place['timezone']:raise ValueError('Data ou fuso inválido')
        if units['temperature_2m_max']!='°C' or units['temperature_2m_min']!='°C' or units['precipitation_probability_max']!='%':raise ValueError('Unidades inválidas')
        low=number(daily['temperature_2m_min'][0],-100,70);high=number(daily['temperature_2m_max'][0],-100,70);rain=number(daily['precipitation_probability_max'][0],0,100)
        if low>high:raise ValueError('Intervalo inválido')
        label=', '.join(str(place[k]) for k in ('name','admin1','country') if place.get(k))
        if suspicious(label) or len(label)>200:raise ValueError('Local inválido')
        source=ENDPOINTS['weather']+'?'+urlencode(args,quote_via=quote)
        return reply(f'Previsão para {label}, em {target.isoformat()} ({place["timezone"]}): mínima de {low:g} °C, máxima de {high:g} °C e probabilidade máxima diária de precipitação de {rain:g}%. Dados por Open-Meteo, consultados em {self.clock().isoformat()}. É uma previsão, não uma garantia. A consulta de localização desta demonstração abrange cidades do Brasil.',sources=[source])

    def exchange(self,message):
        p=plain(message)
        if re.search(r'\b(?:turismo|cartao|card|contrat|venda|sale)\w*\b',p):
            return reply('A PTAX é uma referência pública e não confirma taxa de cartão, turismo ou condição contratual. A cobrança depende do emissor e do contrato aplicável; não confirmei o valor da sua transação. Para consultar apenas a referência pública, informe o par de moedas e a data.','limitado')
        currencies=[code for code,words in [('EUR',r'eur|euro|euros'),('USD',r'usd|dolar|dolares|dollar|dollars'),('GBP',r'gbp|libra|libras')]
                    if re.search(r'\b(?:'+words+r')\b',p)]
        brl=bool(re.search(r'\b(?:brl|reais|real brasileiro|brazilian real)\b',p))
        if len(currencies)!=1 or not brl:
            return reply('Qual par de moedas você quer consultar? Posso buscar a referência PTAX de EUR, USD ou GBP em reais (BRL), que não é taxa de cartão, turismo ou da sua venda.','limitado')
        today=self.clock().astimezone(ZoneInfo('America/Sao_Paulo')).date()
        d=re.search(r'\b(\d{4}-\d{2}-\d{2})\b',p)
        if re.search(r'\b(?:amanha|tomorrow|proxim|next)\w*\b',p):
            return reply('Não há cotação futura confirmada. Informe uma data passada ou consulte o último fechamento publicado.','limitado')
        try:target=date.fromisoformat(d.group(1)) if d else today-timedelta(days=1 if re.search(r'\b(?:ontem|yesterday)\b',p) else 0)
        except ValueError:return reply('A data informada não é válida. Use AAAA-MM-DD.','limitado')
        if target>today:return reply('Não há cotação futura confirmada.','limitado')
        args={'@moeda':"'"+currencies[0]+"'",'@dataInicial':(target-timedelta(days=7)).strftime("'%m-%d-%Y'"),'@dataFinalCotacao':target.strftime("'%m-%d-%Y'"),'$format':'json','$top':200}
        data=self.transport(ENDPOINTS['fx'],args);rows=data['value']
        if not isinstance(rows,list) or len(rows)>200:raise ValueError('Boletins inválidos')
        valid=[]
        for row in rows:
            if row.get('tipoBoletim')!='Fechamento':continue
            stamp=datetime.fromisoformat(row['dataHoraCotacao'])
            if not target-timedelta(days=7)<=stamp.date()<=target:raise ValueError('Data incompatível')
            buy=number(row['cotacaoCompra'],.000001,1_000_000);sell=number(row['cotacaoVenda'],.000001,1_000_000)
            valid.append((stamp,buy,sell))
        if not valid:return reply('O BCB não retornou fechamento PTAX no período consultado. Não confirmei uma cotação.','sem_evidencia')
        stamp,buy,sell=max(valid)
        if (d or re.search(r'\b(?:ontem|yesterday)\b',p)) and stamp.date()!=target:
            return reply(f'Não há fechamento PTAX retornado para {target.isoformat()}. Não substituí a data solicitada por outra cotação.','sem_evidencia')
        caveat='Não foi retornado fechamento para hoje; este é o último fechamento disponível no período consultado. ' if not d and not re.search(r'\b(?:ontem|yesterday)\b',p) and stamp.date()!=today else ''
        source=ENDPOINTS['fx']+'?'+urlencode(args,quote_via=quote)
        return reply(caveat+f'Referência PTAX BCB {currencies[0]}/BRL: compra R$ {buy:.4f} e venda R$ {sell:.4f} por 1 {currencies[0]}. Boletim de fechamento de {stamp.isoformat(sep=" ")} (Brasília); consulta em {self.clock().isoformat()}. Não é cotação em tempo real, taxa de cartão, turismo, preço contratual ou taxa de uma venda Getnet.',sources=[source])

    def search(self,message):
        if len(message)>300:return reply('Para busca geral, reformule a pergunta em até 300 caracteres.','limitado')
        from app.public_search import SearchUnavailable
        try:batch=self.search_provider.search(message)
        except SearchUnavailable as exc:return reply(str(exc),'indisponivel')
        rows=batch.rows
        terms=set(_WORDS.findall(plain(message)))-_STOP
        accepted=[]
        for row in rows:
            if not isinstance(row,dict) or not public_url(row.get('url')):continue
            title=row.get('title','');snippet=row.get('description','')
            if not isinstance(title,str) or not isinstance(snippet,str) or len(title)+len(snippet)>5000:continue
            title=' '.join(unescape(re.sub(r'<[^>]*>',' ',title)).split())
            snippet=' '.join(unescape(re.sub(r'<[^>]*>',' ',snippet)).split())
            text=title+' '+snippet
            if suspicious(text) or clean_message(text)[1] or not terms:continue
            if ambiguous_options(snippet):continue
            overlap=terms & set(_WORDS.findall(plain(text)))
            if len(overlap)<min(2,len(terms)):continue
            if not terms & set(_WORDS.findall(plain(title))):continue
            if len(snippet)>700:continue  # Não corta condições para caber.
            details='Origem indicada pelo índice: '+row['engine']+'.' if row.get('engine') in ('mwmbl','wikipedia','user','google','eusp','não informada') else ''
            stamp=row.get('published_date')
            if isinstance(stamp,str):
                try:details+=' Data estimada pelo provedor: '+datetime.fromisoformat(stamp).isoformat()+'.'
                except ValueError:pass
            if title and snippet:accepted.append((title,snippet,row['url'],details))
            if len(accepted)==3:break
        if not accepted:return reply('A busca não retornou resumos suficientemente pertinentes e seguros para esta pergunta. Não confirmei uma resposta.','sem_evidencia')
        while accepted and len('\n\n'.join(f'{title}: {snippet}\nFonte descoberta: {url}' for title,snippet,url,_ in accepted))>2800:accepted.pop()
        if not accepted:return reply('Os resultados pertinentes excedem o limite de apresentação; reformule a pergunta.','limitado')
        body='\n\n'.join(f'{title}: {snippet}\nFonte descoberta: {url}'+(f'\n{details}' if details else '') for title,snippet,url,details in accepted)
        current=bool(re.search(r'\b(?:hoje|atual|atuais|atualmente|latest|current|today|recent|recentes|novidades)\b',plain(message)))
        caveat='Não confirmei a atualidade nem uma resposta conclusiva para esta pergunta. Consulte a data na fonte original.\n\n' if current else ''
        return reply(caveat+'Busca '+batch.provider+' realizada em '+self.clock().isoformat()+'. Resumos fornecidos pelo buscador; as páginas completas não foram consultadas nem suas afirmações verificadas independentemente.\n'+batch.notice+'\n\n'+body,status='sem_evidencia' if current else 'evidencias',sources=[x[2] for x in accepted])
