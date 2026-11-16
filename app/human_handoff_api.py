"""Authenticated local human-workflow endpoints; never a model tool or Getnet channel."""
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from app.access import access_response
from app.access_store import AccessError

class ClosedInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
class ClientBinding(ClosedInput):
    user_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    session_id:str=Field(pattern=r'^[A-Za-z0-9_-]{20,80}$')
class HandoffProposal(ClientBinding):
    topic:Literal['conectividade','recebiveis','terminal']
    reason:Literal['customer_request','billing_review','unresolved','evidence_gap','tool_unavailable']
    summary:str=Field(min_length=1,max_length=600)
class ClientProposal(ClientBinding):
    proposal_id:str=Field(pattern=r'^[A-Za-z0-9_-]{32}$')
class HandoffConfirmation(ClientProposal):
    confirmed:bool
class ClientAcknowledgment(ClientBinding):
    event_id:str=Field(pattern=r'^[A-Za-z0-9_-]{32}$')
class OperatorLookup(ClosedInput):
    proposal_id:str=Field(pattern=r'^[A-Za-z0-9_-]{32}$')
class OperatorAction(OperatorLookup):
    expected_version:int=Field(ge=0)
    request_id:str=Field(pattern=r'^[A-Za-z0-9_-]{8,80}$')
class OperatorReply(OperatorAction):
    text:str=Field(min_length=1,max_length=600)

_ERRORS={
 'disabled':(404,'Atendimento humano local desativado.'),
 'permission':(403,'Atendimento indisponivel para este contexto.'),
 'expired':(409,'A proposta expirou. Revise uma nova proposta.'),
 'conflict':(409,'Estado ou requisicao divergente. Consulte o estado antes de agir.'),
 'unavailable':(503,'Atendimento local indisponivel. Nenhum resultado confirmado.'),
 'unconfirmed':(503,'Resultado nao confirmado. Consulte o estado antes de repetir a escrita.')}

def _result(data):
    return {**data,'authenticated':True,'getnet_identity_verified':False,
        'local_prototype':True,'sent_to_getnet':False,
        'operator_attribution':'credencial local autorizada, nao identidade pessoal verificada'}

def install_handoff_routes(app,service,store):
    """Client session validation precedes store access; operator identity is token-only."""
    security=app.state.security
    if store is not None and security.required and store.realm!=security.store.realm:raise ValueError("Handoff realm mismatch")
    def principal(request,scope,body=None):
        if not security.required:raise HTTPException(403)
        grant=getattr(request.state,'access_grant',None)
        if grant is None:raise HTTPException(401)
        owner=body.user_id if body is not None else grant.principal.subject
        value=security.bind(request,owner,scope)
        if body is not None:service.store.read(owner,body.session_id)
        # Recheck after session lookup, immediately before store action.
        security.revalidate(request)
        return value
    def execute(request,scope,action,body=None):
        try:
            bound=principal(request,scope,body)
            if store is None:
                from app.demo_tickets import TicketError
                raise TicketError("disabled")
            return _result(action(bound))
        except (HTTPException,AccessError) as error:return access_response(error)
        except PermissionError:return access_response(HTTPException(403))
        except Exception as error:
            code=getattr(error,'code','unconfirmed')
            if code not in _ERRORS:code='unconfirmed'
            status,message=_ERRORS[code]
            return JSONResponse({'state':'not_confirmed','code':code,'message':message,
                'local_prototype':True,'sent_to_getnet':False},status_code=status,
                headers={'Cache-Control':'no-store'})
    @app.post('/demo/handoff/propose')
    def propose(body:HandoffProposal,request:Request):
        return execute(request,'demo_ticket:write',lambda p:store.prepare(p,body.session_id,body.topic,body.reason,body.summary),body)
    @app.post('/demo/handoff/confirm')
    def confirm(body:HandoffConfirmation,request:Request):
        return execute(request,'demo_ticket:write',lambda p:store.confirm(p,body.session_id,body.proposal_id,confirmed=body.confirmed),body)
    @app.post('/demo/handoff/status')
    def status(body:ClientProposal,request:Request):
        return execute(request,'demo_ticket:read',lambda p:store.status(p,body.session_id,body.proposal_id),body)
    @app.post('/context/human/updates')
    def updates(body:ClientBinding,request:Request):
        return execute(request,'demo_ticket:read',lambda p:{'events':store.updates(p,body.session_id),'session_id':body.session_id,'delivery':'available_on_explicit_poll','user_read_proven':False},body)
    @app.post('/context/human/ack')
    def acknowledge(body:ClientAcknowledgment,request:Request):
        return execute(request,'demo_ticket:write',lambda p:{'acknowledgment':store.acknowledge(p,body.session_id,body.event_id),'user_read_proven':False},body)
    @app.get('/demo/operator/queue')
    def queue(request:Request):
        return execute(request,'handoff:read',lambda p:{'items':store.queue(p)})
    @app.post('/demo/operator/reply')
    def reply(body:OperatorReply,request:Request):
        return execute(request,'handoff:respond',lambda p:store.respond(p,body.proposal_id,body.expected_version,body.request_id,body.text))
    @app.post('/demo/operator/close')
    def close(body:OperatorAction,request:Request):
        return execute(request,'handoff:respond',lambda p:store.close(p,body.proposal_id,body.expected_version,body.request_id))

    @app.post('/demo/operator/status')
    def inspect(body:OperatorLookup,request:Request):
        return execute(request,'handoff:read',lambda p:store.inspect(p,body.proposal_id))
