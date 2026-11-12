"""Run free HTTP checks in Docker; retain diagnostics and clean up only our CID."""
import argparse,json,os,re,subprocess,sys,tempfile,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default='getnet-brasil')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--startup-timeout',type=float,default=90)
    parser.add_argument('--docker',default='docker')
    args=parser.parse_args()
    if not 1<=args.startup_timeout<=300:parser.error('startup-timeout must be between 1 and 300 seconds')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    name='getnet-verify-'+uuid.uuid4().hex[:12]
    receipt={'image':args.image,'name':name,'mode':'free deterministic HTTP; no LLM or web search'}
    status=1;cid=None;diagnostic_errors=[]
    def docker(*parts):
        return subprocess.run([args.docker,*parts],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
    with tempfile.TemporaryDirectory(prefix='getnet-docker-cid-') as directory:
        cidfile=Path(directory)/'owned.cid'
        def owned_id():
            value=cidfile.read_text('utf-8').strip() if cidfile.exists() else ''
            return value if re.fullmatch('[a-f0-9]{64}',value) else None
        try:
            created=docker('create','--cidfile',str(cidfile),'--name',name,'--read-only','--tmpfs','/tmp:size=64m,noexec,nosuid',
                           '-p','127.0.0.1::8000','-e','GETNET_CONTEXT_MODEL=0','-e','GETNET_WEB_SEARCH=0',
                           '-e','GETNET_KNOWLEDGE=rag',args.image)
            cid=owned_id()
            if created.returncode or not cid:raise RuntimeError('Docker container creation failed')
            receipt['container_id']=cid
            if docker('start',cid).returncode:raise RuntimeError('Docker container start failed')
            port=docker('port',cid,'8000/tcp')
            if port.returncode:raise RuntimeError('Docker port lookup failed')
            address=port.stdout.strip()
            if not address.startswith('127.0.0.1:') or not address.rsplit(':',1)[1].isdigit():
                raise RuntimeError('Expected one loopback-only Docker port')
            receipt['base_url']='http://'+address
            command=[sys.executable,'-B','-m','scripts.verify_delivery','--url',receipt['base_url'],
                     '--startup-timeout',str(args.startup_timeout),'--output',str(args.output.resolve())]
            env=os.environ.copy()
            for key in list(env):
                if any(word in key.upper() for word in ('API_KEY','TOKEN','SECRET')):env.pop(key,None)
            env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
            with args.output.with_suffix('.execution.log').open('w',encoding='utf-8') as log:
                result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                                      timeout=args.startup_timeout+900)
            status=result.returncode;receipt['verifier_exit_code']=status
        except Exception as exc:
            receipt['error_type']=type(exc).__name__;status=1
        finally:
            # A failed start can still leave a created container. Recover only our CID.
            cid=cid or owned_id()
            if cid:
                receipt['container_id']=cid
                try:
                    for kind,parts in [('logs',('logs','--timestamps',cid)),('state',('inspect','--format','{{json .State}}',cid))]:
                        try:
                            result=docker(*parts)
                            if result.returncode:raise RuntimeError('Diagnostic command failed')
                            if kind=='logs':args.output.with_suffix('.container.log').write_text(result.stdout+result.stderr,'utf-8')
                            else:receipt['state']=json.loads(result.stdout)
                        except Exception as exc:diagnostic_errors.append({'step':kind,'error_type':type(exc).__name__})
                finally:
                    try:receipt['cleanup_exit_code']=docker('rm','-f',cid).returncode
                    except Exception as exc:
                        receipt['cleanup_error_type']=type(exc).__name__;receipt['cleanup_exit_code']=1
                if receipt['cleanup_exit_code']:status=1
            if diagnostic_errors:receipt['diagnostic_errors']=diagnostic_errors;status=1
            receipt['exit_code']=status
            args.output.with_suffix('.container.json').write_text(json.dumps(receipt,indent=2),'utf-8')
    return status

if __name__=='__main__':raise SystemExit(main())
