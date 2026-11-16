"""Entrada HTTP experimental; mantém /chat e adiciona sessão opaca demonstrativa."""
import os,json
from pathlib import Path
from threading import BoundedSemaphore
from fastapi import HTTPException,Request
from app.access import configured_security,AuthenticatedSessions
from app.contracts import bind_input
from app.access_store import AccessError
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,field_validator
from app.http_factory import create_app as create_core_app
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
def create_app(service=None,security=None):
    security=security or configured_security()
    if service is None:
        interpreter=None
        if os.environ.get('GETNET_CONTEXT_MODEL')=='1':
            raise ValueError('Legacy real context model disabled; use app.challenge_api with budgeted supervisor')
        service=ContextService(Store(os.environ.get('GETNET_CONTEXT_DB','/tmp/getnet-context/state.db')),interpreter)
    class PublicAdapter:
        def executar(self,entrada):
            if security.required and entrada._principal is None:raise PermissionError("Missing server identity")
            return service.public(entrada)
    if isinstance(service.store,AuthenticatedSessions) and (not security.required or service.store.realm!=security.store.realm):raise ValueError("Session namespace mismatch")
    service.require_principal=security.required
    if security.required and not isinstance(service.store,AuthenticatedSessions):service.store=AuthenticatedSessions(service.store,security.store.realm)
    app=create_core_app(orchestrator=PublicAdapter(),mode='rag',context_interpreter_enabled=service.interpreter is not None,security=security);slots=BoundedSemaphore(4)
    @app.exception_handler(HTTPException)
    async def controlled(request,exc):return JSONResponse({'detail':DISCLOSURE+' Entrada ou sessão indisponível.'},status_code=exc.status_code,headers={'WWW-Authenticate':'Bearer'} if exc.status_code==401 else None)
    from starlette.exceptions import HTTPException as StarletteHTTPException
    app.add_exception_handler(StarletteHTTPException,controlled)
    @app.post('/context/reset')
    def context_reset(body:ContextInput,request:Request):
        security.bind(request,body.user_id,'context:reset')
        security.revalidate(request)
        if not body.session_id:raise HTTPException(422)
        try:service.reset(body.user_id,body.session_id)
        except PermissionError:raise HTTPException(403)
        except Conflict:raise HTTPException(409)
        except Exception:raise HTTPException(503)
        return {'reset':True,'session_id':body.session_id,'authenticated':security.required,'getnet_identity_verified':False,'synthetic_only':True}
    @app.post('/context/chat')
    def context_chat(body:ContextInput,request:Request):
        principal=security.bind(request,body.user_id,'chat:use')
        if not body.session_id:security.session(request)
        if not slots.acquire(blocking=False):return JSONResponse({'detail':DISCLOSURE+' Capacidade ocupada.'},status_code=429)
        try:
            if not body.message.strip():raise HTTPException(422)
            sid=body.session_id or service.create(body.user_id)
            result=service.step(body.user_id,sid,body.message,**({'access_principal':principal,'authorize_write':lambda:security.revalidate(request)} if security.required else {}))
            return {k:v for k,v in result.items() if k!='state'}|{'session_id':sid,'authenticated':security.required,'getnet_identity_verified':False,'synthetic_only':True}
        except (HTTPException,AccessError):raise
        except PermissionError:return JSONResponse({'detail':DISCLOSURE+' Sessão indisponível para este identificador sintético.'},status_code=403)
        except Conflict:return JSONResponse({'detail':DISCLOSURE+' Contexto mudou durante o atendimento; reenvie a mensagem.'},status_code=409)
        except Exception:return JSONResponse({'detail':DISCLOSURE+' Não foi possível validar o contexto. Nenhuma operação financeira foi realizada.'},status_code=503)
        finally:slots.release()
    return app
