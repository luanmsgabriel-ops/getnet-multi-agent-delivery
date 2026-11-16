"""Launcher explícito: carrega somente o .env solicitado, sem sobrescrever ambiente."""
import argparse,json,os
from pathlib import Path
def configure(env_file=None):
    if env_file:
        if not Path(env_file).is_file():raise ValueError('Arquivo de configuração não encontrado; copie .env.example para .env.')
        from dotenv import load_dotenv
        load_dotenv(env_file,override=False)
    from app.configuration import validate_declared
    from app.public_search import supervisor_configuration
    declared = validate_declared()
    from app.access import configured_security
    security = configured_security()
    from app.rag.runtime import configured_knowledge, configuration_status
    local = configured_knowledge(Path(__file__).resolve().parent.parent/'corpus_publico')
    mode = declared['orchestration']
    if mode == 'supervisor':
        from app.agentic_client import configured_client
        configured_client() # existing ledger and public prices only; no reservation or call
    return {'experience':'challenge_fit', 'interface':'app.challenge_api:app',
        'llm':'supervisor' if mode=='supervisor' else 'disabled',
        'security':security.describe(), 'support':'synthetic_only',
        'getnet':'grounded_generated_opt_in' if declared['generation']=='validated' else 'retrieved_extractive',
        'rag':configuration_status(local),
        'checks':{'declarations':'valid', 'local_auth':'checked' if security.required else 'explicit_demo',
            'local_corpus':'checked', 'model_ledger':'checked' if mode=='supervisor' else 'not_enabled',
            'context_ticket_storage':'not_opened', 'remote_providers':'not_tested'},
        'weather':'Open-Meteo, requires HTTPS', 'exchange':'BCB PTAX, dated reference',
        'general_search':supervisor_configuration(os.environ) if mode=='supervisor' else declared['search'],
        'env_file_loaded':bool(env_file), 'network_performed':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--env-file');p.add_argument('--preflight',action='store_true');p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8000);a=p.parse_args()
    try:info=configure(a.env_file)
    except Exception:p.exit(2,'Preflight failed: check declared modes, local authentication, public corpus and optional model ledger. No provider call was made.\n')
    if a.preflight:print(json.dumps(info,ensure_ascii=False,indent=2));return
    import uvicorn
    uvicorn.run('app.challenge_api:app',host=a.host,port=a.port,access_log=False,limit_concurrency=16,timeout_keep_alive=5)
if __name__=='__main__':main()
