"""Content-free local operational events. No remote exporter or request bodies."""
import asyncio
import contextvars
from contextlib import contextmanager
import json
import logging
import math
import sys
import time
from uuid import uuid4

_REQUEST_ID = contextvars.ContextVar('operational_request_id', default=None)
_LOG = logging.getLogger('getnet.operations')
_LOG.setLevel(logging.INFO)
_LOG.propagate = False
class QuietHandler(logging.StreamHandler):
    def handleError(self, record):
        pass # No stderr traceback, record echo or operational failure.

if not _LOG.handlers:
    handler = QuietHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(message)s'))
    _LOG.addHandler(handler)

ROUTES = frozenset(('/health','/configuration','/chat','/context/chat','/context/reset',
 '/demo/support/propose','/demo/support/confirm','/demo/support/status',
 '/demo/handoff/propose','/demo/handoff/confirm','/demo/handoff/status',
 '/context/human/updates','/context/human/ack','/demo/operator/queue',
 '/demo/operator/reply','/demo/operator/close','/demo/operator/status'))
STAGES = frozenset(('tool','rag','model','supervisor','context','handoff','budget','router','knowledge','support','rag_plan',
 'rag_draft','rag_verify','retrieval','knowledge_getnet','knowledge_public',
 'support_receivables','support_terminal','support_ticket_prepare','support_ticket_status'))
OUTCOMES = frozenset(('ok','partial','blocked','unavailable','timeout','error','invalid',
 'limited','no_progress','cancelled','late_completed','late_failed','uncertain',
 'absent','complete','evidencias','simulado','recusado','limitado','sem_evidencia',
 'indisponivel','deadline','step_limit','tool_limit','model_timeout',
 'model_or_decision_unavailable','lookup_plan_unavailable','finish','limit','clarify','input_policy','no_new_evidence'))

@contextmanager
def request_context():
    existing = _REQUEST_ID.get()
    token = None if existing else _REQUEST_ID.set(uuid4().hex)
    try:
        yield _REQUEST_ID.get()
    finally:
        if token is not None:_REQUEST_ID.reset(token)

def current_request_id():
    return _REQUEST_ID.get()

def _write(record):
    try:
        _LOG.info(json.dumps(record,separators=(',',':'),allow_nan=False))
        return True
    except Exception:
        return False

EVENTS = frozenset(('stage_result','work_late','model_call','budget_reservation',
 'budget_reconciliation','tool_call','retrieval','execution_completed','provider_http_error'))

def capture_context():
    """Capture before thread creation; use the returned context.run(function)."""
    return contextvars.copy_context()

def emit_event(event, *, stage=None, outcome=None, duration_ms=0, count=None,
               cost_usd=None, cost_state=None, mode=None, http_status=None):
    """Closed metadata only; explicit correlation copying for worker threads.

    Unknown costs carry no amount. Reservations are NOT confirmed spend.
    No event allocates a new request ID; outside HTTP correlation remains null.
    """
    if (not isinstance(event,str) or event not in EVENTS or not isinstance(stage,str)
        or stage not in STAGES or not isinstance(outcome,str) or outcome not in OUTCOMES):
        return False
    if type(duration_ms) not in (float,int) or not math.isfinite(duration_ms) or not 0 <= duration_ms <= 86400000:
        return False
    if count is not None and (type(count) is not int or not 0 <= count <= 1000000):return False
    if mode not in (None,'controlled','remote'):return False
    if event in ('model_call','budget_reservation','budget_reconciliation') and mode is None:return False
    if event=='provider_http_error':
        if (stage!='model' or mode is None or type(http_status) is not int
            or not 100 <= http_status <= 599 or http_status==200):return False
    elif http_status is not None:return False
    if cost_state not in (None,'confirmed','reserved','unknown'):return False
    if cost_state in (None,'unknown') and cost_usd is not None:return False
    if cost_state in ('confirmed','reserved') and (type(cost_usd) not in (float,int)
        or not math.isfinite(cost_usd) or not 0 <= cost_usd <= 1000000):return False
    return _write(dict(schema_version=1,event=event,request_id=current_request_id(),
                       stage=stage,outcome=outcome,duration_ms=round(duration_ms,3),
                       count=count,cost_usd=cost_usd,cost_state=cost_state,mode=mode,
                       **({'http_status':http_status} if http_status is not None else {})))

class ObservabilityMiddleware:
    def __init__(self, app):self.app=app
    async def __call__(self, scope, receive, send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        rid=uuid4().hex
        token=_REQUEST_ID.set(rid)
        # State contains only a server-generated correlation value, never identity.
        scope.setdefault('state',{})['operational_request_id']=rid
        started=time.perf_counter();status=None;complete=False;disconnected=False;termination='incomplete'
        async def observed_receive():
            nonlocal disconnected
            message=await receive()
            if message['type']=='http.disconnect':disconnected=True
            return message
        async def observed_send(message):
            nonlocal status,complete
            if message['type']=='http.response.start':
                status=message['status']
                # Do not preserve an application/user-controlled correlation header.
                message=dict(message)
                message['headers']=[(k,v) for k,v in message.get('headers',[]) if k.lower()!=b'x-request-id']+[(b'x-request-id',rid.encode('ascii'))]
            await send(message)
            if message['type']=='http.response.body' and not message.get('more_body',False):complete=True
        try:
            await self.app(scope,observed_receive,observed_send)
            termination='completed' if complete else 'disconnected' if disconnected else 'incomplete'
        except asyncio.CancelledError:
            termination='cancelled';raise
        except BaseException:
            termination='error';raise
        finally:
            try:
                method=scope.get('method')
                route=scope.get('path')
                _write(dict(schema_version=1,event='http_request',request_id=rid,
                    route=route if route in ROUTES else 'other',
                    method=method if method in ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS') else 'other',
                    http_status=status if type(status) is int and 100<=status<=599 else None,
                    duration_ms=round(max(0,time.perf_counter()-started)*1000,3),termination=termination))
            finally:
                _REQUEST_ID.reset(token)
