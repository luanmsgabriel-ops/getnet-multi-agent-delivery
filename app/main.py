"""API de demonstracao local; user_id nao autentica clientes."""
import asyncio
import os
from pathlib import Path
from threading import BoundedSemaphore
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.contracts import Entrada, Saida
from app.orchestration import Orquestrador
from app.support import SupportCatalogoDemo
from app.service_policy import DISCLOSURE

MAX_BODY = 16384
class BodyLimit:
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http': return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        async def error(code, message):
            await JSONResponse({'detail': DISCLOSURE+' '+message}, status_code=code)(scope, receive, send)
        if headers.get(b'content-encoding', b'identity').lower() != b'identity':
            return await error(415, 'Codificacao nao suportada')
        if scope['method'] == 'POST' and headers.get(b'content-type', b'').split(b';')[0].strip().lower() != b'application/json':
            return await error(415, 'Use application/json')
        try:
            length = int(headers.get(b'content-length', b'0'))
            if length < 0: raise ValueError
        except ValueError: return await error(400, 'Tamanho invalido')
        if length > MAX_BODY: return await error(413, 'Corpo excede limite')
        async def collect():
            body = bytearray()
            while True:
                event = await receive()
                if event['type'] == 'http.disconnect': return None
                body.extend(event.get('body', b''))
                if len(body) > MAX_BODY: raise OverflowError
                if not event.get('more_body', False): return bytes(body)
        try: body = await asyncio.wait_for(collect(), timeout=5)
        except OverflowError: return await error(413, 'Corpo excede limite')
        except TimeoutError: return await error(408, 'Tempo de recebimento excedido')
        if body is None: return
        delivered = False
        async def replay():
            nonlocal delivered
            if delivered: return {'type': 'http.disconnect'}
            delivered = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        async def secure_send(event):
            if event['type'] == 'http.response.start':
                event['headers'] = list(event.get('headers', [])) + [(b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff')]
            await send(event)
        await self.app(scope, replay, secure_send)

def create_app(orchestrator=None, *, mode=None, corpus=None, web_search=None, enable_web=None, generator=None, context_interpreter_enabled=False):
    selected = mode if mode is not None else os.environ.get('GETNET_KNOWLEDGE', 'demo')
    if selected not in ('demo', 'rag', 'generated'): raise ValueError('GETNET_KNOWLEDGE deve ser demo, rag ou generated')
    web_enabled = enable_web if enable_web is not None else os.environ.get('GETNET_WEB_SEARCH', '0') == '1'
    if orchestrator is None:
        from app.knowledge import KnowledgeDemo, KnowledgeDispatch, KnowledgeWeb
        web = None
        if web_enabled:
            from app.rag.official_catalog import official_search
            web = KnowledgeWeb(web_search if web_search is not None else official_search())
        if selected in ('rag','generated'):
            from app.knowledge import KnowledgeRag
            directory = Path(corpus) if corpus else Path(__file__).resolve().parent.parent / 'corpus_publico'
            local = KnowledgeRag.from_directory(directory)
            if selected == 'generated':
                from app.knowledge import KnowledgeGenerated
                if generator is None:
                    if os.environ.get('GETNET_ALLOW_MODEL_NETWORK') != '1':
                        raise ValueError('Modelo real exige GETNET_ALLOW_MODEL_NETWORK=1 e orcamento autorizado')
                    model=os.environ.get('GETNET_MODEL','')
                    if not model.startswith('openrouter:') or len(model)>160 or not os.environ.get('OPENROUTER_API_KEY'):
                        raise ValueError('Configure modelo OpenRouter e credencial no ambiente; valores nao registrados')
                    from app.rag.generation import PydanticGenerator
                    generator=PydanticGenerator(model,allow_network=True)
                local=KnowledgeGenerated(local.index,generator)

        else: local = KnowledgeDemo()
        orchestrator = Orquestrador(knowledge=KnowledgeDispatch(local, web), support=SupportCatalogoDemo())
    app = FastAPI(title='Getnet - demonstracao local', version='0.1.0', redoc_url=None)
    app.add_middleware(BodyLimit)
    slots = BoundedSemaphore(4)
    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({'detail': DISCLOSURE+' Entrada invalida: use message (1-4000) e user_id sintetico (1-64).'}, status_code=422)
    @app.get('/health')
    def health():
        return {'status': 'ok', 'knowledge': selected, 'environment': 'demonstracao_local', 'authenticated': False, 'web_search_enabled': web_enabled, 'context_interpreter_enabled': bool(context_interpreter_enabled)}
    @app.post('/chat', response_model=Saida)
    def chat(entrada: Entrada):
        if not slots.acquire(blocking=False):
            return JSONResponse({'detail': DISCLOSURE+' Capacidade ocupada; tente novamente.'}, status_code=429)
        try:
            from app.privacy import clean_message
            safe,redacted=clean_message(entrada.message)
            result = Saida.model_validate(orchestrator.executar(entrada.model_copy(update={'message':safe})))
            from app.response_notices import compose_notices, response_parts
            answer=compose_notices(*response_parts(result),credentials=redacted)
            result=result.model_copy(update={'answer':str(answer),'presentation':list(answer.parts)})
            # API sem sessão: todo POST pode ser a primeira interação.
            return result if result.answer.startswith(DISCLOSURE) else result.model_copy(update={'answer':DISCLOSURE+'\n\n'+result.answer})
        except Exception:
            return JSONResponse({'detail': DISCLOSURE+' Atendimento temporariamente indisponivel.'}, status_code=503)
        finally: slots.release()
    return app

app = create_app()
