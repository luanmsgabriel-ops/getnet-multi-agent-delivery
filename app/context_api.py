"""Entrada HTTP experimental; mantém /chat e adiciona sessão opaca demonstrativa."""
import os,json
from pathlib import Path
from threading import BoundedSemaphore
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,field_validator
from app.main import create_app as create_core_app
from app.context_service import ContextService
from app.context_store import Store,Conflict
from app.service_policy import DISCLOSURE
class ContextInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    message:str=Field(min_length=1,max_length=4000)
    user_id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    session_id:str|None=Field(default=None,min_length=20,max_length=80)
    @field_validator('message')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('Mensagem vazia')
        return value
def create_app(service=None):
    if service is None:
        interpreter=None
        if os.environ.get('GETNET_CONTEXT_MODEL')=='1':
            from app.context_client import ModelClient
            from app.context_solo import SoloInterpreter
            # Prices must match the selected model before any paid request.
            pricefile=os.environ['GETNET_PRICE_FILE'];model=os.environ.get('GETNET_MODEL','openai/gpt-6-sol').removeprefix('openrouter:')
            meta=json.loads(Path(pricefile).read_text('utf-8'));prices=meta['model']['pricing']
            if meta['model']['id']!=model:raise ValueError('Pricing/model mismatch')
            interpreter=SoloInterpreter(ModelClient(os.environ['GETNET_COST_LEDGER'],os.environ['OPENROUTER_API_KEY'],prices,model=model,max_calls=int(os.environ.get('GETNET_MAX_CALLS','40')),max_cost=os.environ.get('GETNET_COST_CAP','1.00')))
        service=ContextService(Store(os.environ.get('GETNET_CONTEXT_DB','/tmp/getnet-context/state.db')),interpreter)
    class PublicAdapter:
        def executar(self,entrada):return service.public(entrada)
    app=create_core_app(orchestrator=PublicAdapter(),mode='rag',context_interpreter_enabled=service.interpreter is not None);slots=BoundedSemaphore(4)
    @app.exception_handler(HTTPException)
    async def controlled(request,exc):return JSONResponse({'detail':DISCLOSURE+' Entrada ou sessão indisponível.'},status_code=exc.status_code)
    from starlette.exceptions import HTTPException as StarletteHTTPException
    app.add_exception_handler(StarletteHTTPException,controlled)
    @app.post('/context/reset')
    def context_reset(body:ContextInput):
        if not body.session_id:raise HTTPException(422)
        try:service.reset(body.user_id,body.session_id)
        except PermissionError:raise HTTPException(403)
        except Conflict:raise HTTPException(409)
        except Exception:raise HTTPException(503)
        return {'reset':True,'session_id':body.session_id,'authenticated':False,'synthetic_only':True}
    @app.post('/context/chat')
    def context_chat(body:ContextInput):
        if not slots.acquire(blocking=False):return JSONResponse({'detail':DISCLOSURE+' Capacidade ocupada.'},status_code=429)
        try:
            if not body.message.strip():raise HTTPException(422)
            sid=body.session_id or service.create(body.user_id)
            result=service.step(body.user_id,sid,body.message)
            return {k:v for k,v in result.items() if k!='state'}|{'session_id':sid,'authenticated':False,'synthetic_only':True}
        except HTTPException:raise
        except PermissionError:return JSONResponse({'detail':DISCLOSURE+' Sessão indisponível para este identificador sintético.'},status_code=403)
        except Conflict:return JSONResponse({'detail':DISCLOSURE+' Contexto mudou durante o atendimento; reenvie a mensagem.'},status_code=409)
        except Exception:return JSONResponse({'detail':DISCLOSURE+' Não foi possível validar o contexto. Nenhuma operação financeira foi realizada.'},status_code=503)
        finally:slots.release()
    return app
app=create_app()
