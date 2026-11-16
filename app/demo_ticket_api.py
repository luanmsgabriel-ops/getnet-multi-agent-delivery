"""Explicit demo-only HTTP confirmation; no model can call these routes."""
import os,re
from pydantic import BaseModel,ConfigDict,Field
from fastapi.responses import JSONResponse
from fastapi import Request,HTTPException
from app.access_store import AccessError
from app.access import access_response
from app.demo_tickets import TicketStore,TicketTopic,TicketError
from app.support import SupportCatalogoDemo,Principal

def configured_tickets(env=None):
 env=os.environ if env is None else env
 enabled=env.get('GETNET_DEMO_TICKETS','0')
 if enabled not in ('0','1'):raise ValueError('GETNET_DEMO_TICKETS must be 0 or 1')
 path=env.get('GETNET_DEMO_TICKET_DB')
 if enabled=='1' and not path:raise ValueError('An explicit local demo ticket database path is required')
 return TicketStore(path or 'unused-disabled-demo-tickets.db',enabled=enabled=='1')

def demo_principal(owner, bound=None):
 from app.support import resolve_principal
 principal=resolve_principal(owner,bound)
 if principal is None:raise PermissionError('Unknown synthetic identity')
 return principal if bound is not None else Principal(principal.subject,principal.tenant,principal.scopes|frozenset({'demo_ticket:write','demo_ticket:read'}))

def requested_local_demo_ticket(text):
 from app.intents import normalize
 t=normalize(text)
 verb=re.search(r'\b(?:registre|registrar|crie|criar|abra|abrir|create|open|register|prepare|preparar)\b',t)
 if not verb:return False
 # A negated/explanatory creation predicate is not a request to prepare.
 # An unrelated restriction such as "nao envie a Getnet" remains intact.
 prefix=re.split(r'[.!?;]',t[:verb.start()])[-1]
 return (bool(re.search(r'\b(?:solicitacao|chamado|protocolo|ticket|request)\b',t))
  and bool(re.search(r'\b(?:demonstrativ\w*|demonstracao|demo|local)\b',t))
  and not re.search(r"\b(?:nao|nunca|not|never|don.t|explique|explain|como|how)\b",prefix))


class TicketBinding(BaseModel):
 model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
 user_id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
 session_id:str=Field(min_length=20,max_length=80)
class TicketOfferInput(TicketBinding):
 topic:TicketTopic
class TicketLookupInput(TicketBinding):
 proposal_id:str=Field(min_length=20,max_length=100)
class TicketConfirmInput(TicketLookupInput):
 topic:TicketTopic
 confirmed:bool

ERROR_MESSAGES={'disabled':'Registro demonstrativo desativado.',
 'permission':'Proposta indisponível para este contexto demonstrativo.',
 'expired':'A proposta venceu. Revise uma nova proposta antes de confirmar.',
 'conflict':'A confirmação não corresponde à proposta apresentada.',
 'unavailable':'Registro local indisponível. Não há confirmação de operação.',
 'unconfirmed':'Resultado não confirmado. Consulte o estado pela mesma proposta, sem repetir a escrita.'}

def ticket_error(error):
 code=getattr(error,'code','permission' if isinstance(error,PermissionError) else 'unconfirmed')
 if code not in ERROR_MESSAGES:code='unconfirmed'
 status={'disabled':404,'permission':403,'expired':409,'conflict':409,'unavailable':503,'unconfirmed':503}[code]
 return JSONResponse({'state':'not_confirmed','code':code,'message':ERROR_MESSAGES[code],
   'synthetic_only':True,'authenticated':False,'destination':'local_demo','sent_to_getnet':False},status_code=status)

def install_ticket_routes(app,service,tickets):
    security=app.state.security
    def bind(body,request,scope):
        principal=security.bind(request,body.user_id,scope)
        security.revalidate(request)
        if not tickets.enabled:raise TicketError('disabled')
        service.store.read(body.user_id,body.session_id)
        return demo_principal(body.user_id,principal)
    def execute(request,body,scope,action):
        try:
            result=action(bind(body,request,scope))
            return {**result,'authenticated':security.required,'getnet_identity_verified':False}
        except HTTPException:raise
        except AccessError as error:return access_response(error)
        except Exception as error:return ticket_error(error)
    @app.post('/demo/support/propose')
    def offer(body:TicketOfferInput,request:Request):
        return execute(request,body,'demo_ticket:write',lambda p:tickets.offer(p,body.session_id,body.topic))
    @app.post('/demo/support/confirm')
    def confirm(body:TicketConfirmInput,request:Request):
        # Explicit client HTTP action, never a model decision or chat yes.
        return execute(request,body,'demo_ticket:write',lambda p:tickets.confirm(p,body.session_id,body.proposal_id,body.topic,confirmed=body.confirmed))
    @app.post('/demo/support/status')
    def lookup(body:TicketLookupInput,request:Request):
        return execute(request,body,'demo_ticket:read',lambda p:tickets.lookup(p,body.session_id,body.proposal_id))
