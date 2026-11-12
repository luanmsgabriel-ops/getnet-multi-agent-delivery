"""HTTP de entrega sem LLM: servidor próprio ou instância loopback configurada sem modelo/rede."""
import argparse,hashlib,json,os,re,socket,subprocess,sys,tempfile,time,unicodedata
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
def norm(value):return ''.join(c for c in unicodedata.normalize('NFKD',value.casefold()) if not unicodedata.combining(c))
def password_on_device(answer):
    """Contrato mínimo: instrução local + proibição de envio, não palavra solta.

    Detector conservador de apresentações PT conhecidas; revisão semântica continua
    necessária. "Aparelho", "maquininha" e "dispositivo" não mudam a proteção.
    """
    text=norm(answer)
    local=bool(re.search(
        r'(?:^|[.!?;\n]\s*)(?:digite|insira)\b[^.!?;\n]{0,90}\bsenha\b'
        r'[^.!?;\n]{0,90}\b(?:somente|apenas)\b[^.!?;\n]{0,60}'
        r'\b(?:aparelho|maquininha|dispositivo)\b',text))
    chat=bool(re.search(
        r'\b(?:nao|nunca)\s+(?:envie|compartilhe)\b[^.!?;\n]{0,65}'
        r'\b(?:senha|senhas|credenciais)\b[^.!?;\n]{0,65}\b(?:chat|conversa)\b',text))
    unsafe=bool(re.search(
        r'(?:^|[.!?;\n]\s*)(?:envie|compartilhe)\b[^.!?;\n]{0,65}'
        r'\b(?:senha|senhas|credenciais)\b',text))
    return local and chat and not unsafe

def request(base,path,payload=None,*,timeout=20):
    raw=None if payload is None else json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    if raw is not None:assert json.loads(raw)==payload and '\ufffd' not in raw.decode('utf-8')
    req=Request(base+path,data=raw,headers={'Content-Type':'application/json; charset=utf-8'})
    try:
        with urlopen(req,timeout=timeout) as response:return response.status,json.load(response)
    except HTTPError as error:return error.code,json.load(error)
class StartupError(RuntimeError):
    def __init__(self, diagnostics):
        self.diagnostics=diagnostics
        super().__init__('Local service not ready: '+diagnostics['reason'])

def wait_ready(base, *, timeout=90, process=None):
    """Wait against a monotonic deadline; do not confuse slow startup with a crash."""
    start=time.monotonic();attempts=0;last_error=None
    def details(reason):
        return {'reason':reason,'elapsed_seconds':round(time.monotonic()-start,3),
                'timeout_seconds':timeout,'attempts':attempts,'last_error_type':last_error}
    while True:
        remaining=timeout-(time.monotonic()-start)
        if remaining<=0:raise StartupError(details('startup_deadline_exceeded'))
        if process is not None and process.poll() is not None:
            raise StartupError(details('server_process_exited'))
        attempts+=1
        try:
            status,health=request(base,'/health',timeout=min(1,remaining))
        except OSError as exc:
            # Keep only the type, never response bodies or possibly sensitive errors.
            last_error=type(exc).__name__
        else:
            return status,health,details('health_received')
        time.sleep(min(.25,max(0,timeout-(time.monotonic()-start))))

def verify(base):
    cases=json.loads((ROOT/'tests/data/delivery_cases.json').read_text('utf-8'))['cases'];rows=[]
    for case in cases:
        status,response=request(base,'/chat',{'message':case['message'],'user_id':case['user_id']});exp=case['expected'];answer=norm(response.get('answer',''));errors=[]
        if status!=200:errors.append('HTTP != 200')
        for text in exp.get('contains',[]):
            if norm(text) not in answer:errors.append('Missing expected concept: '+text)
        for text in exp.get('not_contains',[]):
            if norm(text) in answer:errors.append('Unexpected content')
        if exp.get('password_only_on_device') and not password_on_device(response.get('answer','')):errors.append('Missing safe device-only password guidance')
        sources=response.get('sources',[])
        if 'sources' in exp and bool(sources)!=exp['sources']:errors.append('Source presence differs')
        if len(sources)<exp.get('min_sources',0):errors.append('Insufficient source coverage')
        if any(not source.startswith('https://site.getnet.com.br/') for source in sources):errors.append('Source outside Brazil boundary')
        tools=[e['ferramenta'] for e in response.get('eventos',[]) if e.get('ferramenta')]
        if 'tools' in exp and sorted(tools)!=sorted(exp['tools']):errors.append('Unexpected tool dispatch')
        if 'simulated' in exp and response.get('simulated_data')!=exp['simulated']:errors.append('Simulation disclosure mismatch')
        rows.append({'id':case['id'],'group':case['group'],'input':case['message'],'status':status,'response':response,'contract_pass':not errors,'errors':errors})
    checks=[]
    for path,payload,expected in [('/context/chat',{'message':'   ','user_id':'demo_A'},422),('/chat',{'message':'','user_id':'demo_A'},422),('/context/reset',{'message':'reset','user_id':'demo_A'},422),('/chat',{'message':'oi','user_id':'demo_A','extra':True},422)]:
        status,_=request(base,path,payload);checks.append({'check':path,'expected':expected,'actual':status,'pass':status==expected})
    status,data=request(base,'/context/chat',{'message':'Minha A920 está no Chile. Como configurar Wi-Fi?','user_id':'delivery_A'});sid=data.get('session_id');checks.append({'check':'context outside before provider','pass':status==200 and data.get('mode')=='scope_policy' and not data.get('sources')})
    if sid:
        status,data=request(base,'/context/chat',{'message':'Qual o próximo passo?','user_id':'delivery_A','session_id':sid});checks.append({'check':'context outside followup','pass':status==200 and data.get('mode')=='scope_policy' and not data.get('sources')})
        for owner,expected in [('delivery_B',403),('delivery_A',200)]:
            status,data=request(base,'/context/reset',{'message':'reset','user_id':owner,'session_id':sid});checks.append({'check':'reset isolation '+owner,'expected':expected,'actual':status,'pass':status==expected})
    return {'mode':'HTTP TCP with deterministic/extractive replies; no new model generation or public search','dataset_sha256':hashlib.sha256((ROOT/'tests/data/delivery_cases.json').read_bytes()).hexdigest(),'case_count':len(rows),'contracts_passed':sum(r['contract_pass'] for r in rows),'controls_passed':sum(r['pass'] for r in checks),'controls':checks,'cases':rows,'semantic_limit':'These are minimum regression contracts, not a complete automatic semantic grade. Review answer, sources, dates and limitations.'}
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--url',help='Only a loopback deployment with model/web disabled');parser.add_argument('--output',type=Path,required=True);parser.add_argument('--startup-timeout',type=float,default=90,help='Readiness deadline in seconds (1–300)');args=parser.parse_args();process=None;server_log=None;readiness=None
    if not 1<=args.startup_timeout<=300:parser.error('startup-timeout must be between 1 and 300 seconds')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='getnet-delivery-') as tmp:
        if args.url:
            parsed=urlsplit(args.url)
            if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password:parser.error('Use a local loopback HTTP URL')
            base=args.url.rstrip('/')
        else:
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            base='http://127.0.0.1:'+str(port);env=os.environ.copy()
            for name in list(env):
                if any(x in name.upper() for x in ('API_KEY','TOKEN','SECRET')):env.pop(name,None)
            env.update(GETNET_CONTEXT_MODEL='0',GETNET_WEB_SEARCH='0',GETNET_KNOWLEDGE='rag',GETNET_CONTEXT_DB=str(Path(tmp)/'state.db'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
            server_log=args.output.with_suffix('.server.log').open('w',encoding='utf-8')
            process=subprocess.Popen([sys.executable,'-B','-m','uvicorn','app.context_api:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],cwd=ROOT,env=env,stdout=server_log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            status,health,readiness=wait_ready(base,timeout=args.startup_timeout,process=process)
            if status!=200 or health.get('knowledge')!='rag' or health.get('web_search_enabled') is not False or health.get('context_interpreter_enabled') is not False:
                raise RuntimeError('Expected a free local RAG deployment with web search disabled; no POST performed')
            result=verify(base);result['health']=health;result['readiness']=readiness;args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
            print(json.dumps({k:v for k,v in result.items() if k not in ('cases','controls')},ensure_ascii=False));return 0 if result['contracts_passed']==result['case_count'] and all(c['pass'] for c in result['controls']) else 1
        except Exception as exc:
            failure={'passed':False,'error_type':type(exc).__name__,
                     'readiness':exc.diagnostics if isinstance(exc,StartupError) else readiness}
            args.output.write_text(json.dumps(failure,indent=2),'utf-8')
            raise
        finally:
            if process:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            if server_log:server_log.close()
if __name__=='__main__':raise SystemExit(main())
