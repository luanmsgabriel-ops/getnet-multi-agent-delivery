"""Local bearer authentication. No Getnet identity or model authority."""
import os,json,logging
_LOG=logging.getLogger("getnet.security")
_LOG.setLevel(logging.INFO)
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from app.access_store import AccessStore, AccessError

class Security:
    def __init__(self, store=None, *, mode="required"):
        if mode not in ("required", "demo") or (mode=="required" and store is None):
            raise ValueError("Explicit authentication configuration required")
        self.mode,self.store=mode,store
    @property
    def required(self):return self.mode=="required"
    def bind(self, request, user_id, scope=None):
        grant=getattr(request.state,"access_grant",None)
        if not self.required:return None
        if grant is None:raise HTTPException(401,headers={"WWW-Authenticate":"Bearer"})
        if user_id!=grant.principal.subject or (scope and scope not in grant.principal.scopes):
            raise HTTPException(403)
        return grant.principal
    def revalidate(self, request):
        if self.required:self.store.revalidate(request.state.access_grant)
    def session(self, request):
        if self.required:self.store.consume(request.state.access_grant,bucket="session")
    def describe(self):
        return {"mode":self.mode,"credential_authentication":self.required,
                "getnet_identity_verified":False,"synthetic_only":True}

def configured_security(env=None):
    env=os.environ if env is None else env
    mode=env.get("GETNET_AUTH_MODE","required")
    if mode=="demo":return Security(mode="demo")
    if mode!="required" or not env.get("GETNET_AUTH_DB"):
        raise ValueError("Set GETNET_AUTH_DB for required authentication or explicitly select local demo")
    return Security(AccessStore(env["GETNET_AUTH_DB"],
        per_minute=int(env.get("GETNET_RATE_PER_MINUTE","30")),
        global_per_minute=int(env.get("GETNET_RATE_GLOBAL_PER_MINUTE","180"))))

def access_response(error):
    status=getattr(error,"status_code",503)
    if status not in (401,403,429,503):status=503
    detail={401:"Credencial ausente ou invalida.",403:"Acesso indisponivel.",
            429:"Limite de requisicoes atingido.",503:"Controle de acesso indisponivel."}[status]
    headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}
    if status==401:headers["WWW-Authenticate"]="Bearer"
    if status==429:headers["Retry-After"]="60"
    return JSONResponse({"detail":detail},status_code=status,headers=headers)

class AccessBoundary:
    def __init__(self,app,security):
        from app.observability import ObservabilityMiddleware
        self.app,self.security=app,security
        self.observed=ObservabilityMiddleware(self._call)
    async def __call__(self,scope,receive,send):
        return await self.observed(scope,receive,send)
    async def _call(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        if scope.get('path')=='/health' and scope.get('method')=='GET':
            return await self.app(scope,receive,send)
        original_send=send
        async def audited_send(event):
            if event['type']=='http.response.start':
                route=scope.get('path')
                if route not in ('/chat','/context/chat','/context/reset','/demo/support/propose','/demo/support/confirm','/demo/support/status','/configuration','/demo/handoff/propose','/demo/handoff/confirm','/demo/handoff/status','/context/human/updates','/context/human/ack','/demo/operator/queue','/demo/operator/reply','/demo/operator/close','/demo/operator/status'):route='other'
                # A closed field set: no header, token, identity, message or user URL.
                try:
                    _LOG.info(json.dumps({'event':'access_result','route':route,'status':event['status'],'mode':self.security.mode},separators=(',',':')))
                except Exception:
                    pass # Logging failure must not alter the access decision.
            await original_send(event)
        send=audited_send
        try:
            headers=[v for k,v in scope.get('headers',[]) if k.lower()==b'authorization']
            if self.security.required:
                self.security.store.ingress()
                if len(headers)!=1 or len(headers[0])>256:raise AccessError('invalid')
                try:scheme,token=headers[0].decode('ascii').split(' ',1)
                except Exception:raise AccessError('invalid') from None
                if scheme.lower()!='bearer' or not token or token.strip()!=token:raise AccessError('invalid')
                grant=self.security.store.authenticate(token)
                self.security.store.consume(grant)
                scope.setdefault('state',{})['access_grant']=grant
            elif headers:
                # An invalid/misrouted credential must never downgrade to anonymous demo.
                raise AccessError('invalid')
        except AccessError as error:return await access_response(error)(scope,receive,send)
        except Exception:return await access_response(AccessError('unavailable'))(scope,receive,send)
        return await self.app(scope,receive,send)

class AuthenticatedSessions:
    """A disjoint namespace: old anonymous sessions cannot be adopted by a token."""
    def __init__(self,store,realm):
        import re
        if not isinstance(realm,str) or not re.fullmatch(r"[a-f0-9]{32}",realm):raise ValueError("Invalid access realm")
        self.store,self.realm=store,realm
        self.prefix="auth:v1:"+realm+":"
    def create(self,owner):return self.store.create(self.prefix+owner)
    def read(self,owner,sid):return self.store.read(self.prefix+owner,sid)
    def commit(self,owner,sid,version,state):return self.store.commit(self.prefix+owner,sid,version,state)
    def reset(self,owner,sid):return self.store.reset(self.prefix+owner,sid)

    def assert_version(self,owner,sid,expected):return self.store.assert_version(self.prefix+owner,sid,expected)
