"""Entrada canônica BCF: Getnet Brasil e informação pública, sem LLM implícito."""
import os,re,time
from pathlib import Path
from tempfile import gettempdir
from uuid import uuid4
from app.observability import current_request_id,request_context
from app.contracts import Entrada,RespostaEspecialista,Saida,bind_input
from fastapi import Request
from app.context_factory import create_app as context_app
from app.context_service import ContextService
from app.context_store import Store
from app.orchestration import Orquestrador
from app.knowledge import KnowledgeRag,KnowledgeDispatch,KnowledgeWeb
from app.rag.runtime import configured_knowledge,configuration_status
from app.rag.grounding import aggregate_coverage
from app.support import SupportCatalogoDemo
from app.service_policy import DISCLOSURE,ServicePlan,service_plan
from app.privacy import clean_message
from app.intents import normalize,request_facts
from app.response_notices import compose_notices,response_parts

BUSINESS=re.compile(r'\b(?:getnet|smart|classica|a920|dx8000|pax|crediario|pix|maquinin\w*|terminal|card machine|payment link|link de pagamento|recebiveis|antecip\w*|receivables|vendas?|sales|saldo|conta|cadastro|senha|password)\b')
def parts(message):
    # Uma declaração anterior pertence à pergunta seguinte. Só separa o ponto
    # depois de um pedido completo; não perde a cidade em "Estou em X. Vai chover?".
    chunks=re.split(r'(?<=[?;!])\s+|\s+(?:e|and)\s+(?=(?:qual|como|o que|what|how|when)\b)',message,flags=re.I)
    result=[]
    for chunk in chunks:
        sentences=re.split(r'\.\s+(?=[A-ZÀ-Ü])',chunk,flags=re.I);pending=''
        for sentence in sentences:
            pending=(pending+'. '+sentence if pending else sentence).strip(' .;')
            if re.match(r'^(?:compare|explique|pesquise|compare as|explain|search|qual|como|what|how|quando|when)\b',normalize(pending)):
                if pending:result.append(pending)
                pending=''
        if pending:result.append(pending)
    return result
def is_public(message):
    text=normalize(message)
    from app.request_plan import financial_request
    from app.public_information import CURRENCY
    # Taxa de câmbio pública é distinta de taxa/recebível de uma venda Getnet.
    if CURRENCY.search(text) and not BUSINESS.search(text) and not request_facts(message).unsupported_action:return True
    if financial_request(message) or re.search(r'\b(?:recebo|receberei|receberemos)\b',text):return False
    if re.fullmatch(r'(?:e )?(?:agora|ela|ele|isso|e agora o que faco|what now|and now)[ ?!.]*',text):return False
    if re.fullmatch(r'oi|ola|hello|hi|bom dia|boa tarde|boa noite',text.strip(' !?.')):return False
    # Ação privada continua nas proteções de suporte; moeda numa venda é Getnet.
    return not BUSINESS.search(text) and not request_facts(message).unsupported_action
class PublicRouter:
    def planejar(self,entrada):
        from app.contracts import Plano
        return Plano(rota='knowledge')
class PublicKnowledge:
    def __init__(self,provider):self.provider=provider
    def responder(self,entrada,contexto):return self.provider.answer(entrada.message)
class ChallengeOrchestrator:
    def __init__(self,business,provider,documentary=None):
        self.business=business
        self.documentary=Orquestrador(router=PublicRouter(),knowledge=documentary,policy=lambda m:ServicePlan(m),preserve_failure_details=True) if documentary is not None else None
        self.public=Orquestrador(router=PublicRouter(),knowledge=PublicKnowledge(provider),policy=lambda m:ServicePlan(m),preserve_failure_details=True)
    @request_context()
    def executar(self,dados):
        e=Entrada.model_validate(dados);safe,redacted=clean_message(e.message)
        from app.documentary_plan import intact_documentary,needs_documentary_reference,independent_public_question
        if self.documentary is not None and needs_documentary_reference(safe):
            return Saida(request_id=current_request_id() or str(uuid4()),route='clarify',status='limitado',answer='A qual produto ou assunto da Getnet Brasil você se refere? Não tenho uma referência explícita para essa pergunta.',sources=[],simulated_data=False,eventos=[],modo='extrativo')
        # A documentary request is one semantic obligation, not one obligation per
        # punctuation mark. Keep conditions and dependent instructions intact.
        if self.documentary is not None and intact_documentary(safe):
            return self.documentary.executar(e.model_copy(update={'message':e.message}))
        queries=parts(safe)
        # Preserve dependent Getnet follow-ups as one documentary block when a
        # separate standalone public question occurs in the same message.
        if self.documentary is not None and any(independent_public_question(q) for q in queries):
            grouped=[]
            for query in queries:
                if grouped and not BUSINESS.search(normalize(query)) and not independent_public_question(query) and not is_public(grouped[-1]):
                    grouped[-1] += '. ' + query
                else:grouped.append(query)
            queries=grouped
        if not queries or not any(re.search(r'\w',q) for q in queries) or len(queries)>3:
            return Saida(request_id=current_request_id() or str(uuid4()),route='clarify',status='limitado',answer='Descreva sua dúvida em até três pedidos por mensagem para que nenhuma parte seja omitida.',sources=[],simulated_data=False,eventos=[],modo='extrativo')
        results=[(self.public if is_public(q) else self.documentary if self.documentary is not None and intact_documentary(q) else self.business).executar(e.model_copy(update={'message':q})) for q in queries]
        status=next((s for s in ('recusado','indisponivel','limitado','sem_evidencia','simulado','evidencias') if any(r.status==s for r in results)),'sem_evidencia')
        answer=compose_notices(*(p for r in results for p in response_parts(r)),credentials=redacted)
        return Saida(request_id=current_request_id() or str(uuid4()),route='support_knowledge' if any('support' in r.route for r in results) and any(r.route=='knowledge' for r in results) else results[0].route,
            status=status,answer=str(answer),presentation=list(answer.parts),evidence_coverage=aggregate_coverage(results),grounding=[c for r in results for c in r.grounding if c.claim in str(answer)],sources=list(dict.fromkeys(s for r in results for s in r.sources)),simulated_data=any(r.simulated_data for r in results),
            eventos=[ev for r in results for ev in r.eventos],modo='misto' if len({r.modo for r in results})>1 else results[0].modo)
class ChallengeService(ContextService):
    def __init__(self,store,provider=None,supervisor=None,tickets=None):
        super().__init__(store)
        from app.public_information import PublicInformation
        local=configured_knowledge(Path(__file__).resolve().parent.parent/'corpus_publico')
        web=None
        if os.environ.get('GETNET_WEB_SEARCH')=='1':
            from app.rag.official_catalog import official_search
            web=KnowledgeWeb(official_search())
        self.local=local
        self.supervisor=supervisor
        self.tickets=tickets
        self.core=ChallengeOrchestrator(Orquestrador(knowledge=KnowledgeDispatch(local,web),support=SupportCatalogoDemo(),policy=lambda message:service_plan(message,local=local)),provider or PublicInformation(),documentary=local if getattr(local,'documentary',False) else None)
    def public(self,dados):
        e=Entrada.model_validate(dados)
        if getattr(self,'require_principal',False) and e._principal is None:raise PermissionError('Missing server identity')
        if self.supervisor is not None:return self.supervisor.executar(e)
        return self.core.executar(e)
    def step(self,principal,session,message,documents=(),access_principal=None,authorize_write=None,**kwargs):
        if getattr(self,"require_principal",False) and access_principal is None:raise PermissionError("Missing server identity")
        safe,redacted=clean_message(message)
        from app.dialogue_memory import history_for,record_turn
        from app.context_reference import reference_clarification,dependent_reference,recall_request
        start_version,initial_state=self.store.read(principal,session)
        expected=start_version
        def checked(result):
            if authorize_write:authorize_write()
            if hasattr(self.store,'assert_version'):self.store.assert_version(principal,session,expected)
            from app.handoff_policy import handoff_offer
            offer=handoff_offer(safe,result,enabled=getattr(self,'handoff',None) is not None)
            return {**result,**({'human_handoff_offer':offer} if offer else {})}
        clarification=reference_clarification(safe,initial_state)
        if clarification and (self.supervisor is None or recall_request(safe)):
            return checked({'answer':DISCLOSURE+'\n\n'+clarification,'sources':[],'status':'limitado',
                'route':'clarify','mode':'context_reference_missing','traces':[],
                'documents_received':len(documents),'documents_ignored':bool(documents),'external_documents_actionable':False})
        if self.supervisor is not None:
            version,state=self.store.read(principal,session)
            # Histórico de pedidos sanitizados é dado relatado, não fato validado.
            # Não promove entidades, autorizações ou resultados ao estado legado.
            history=history_for(state)
            result=self.supervisor.executar(bind_input({'message':safe,'user_id':principal},access_principal),history=history,session=session)
            if authorize_write:authorize_write()
            self.store.commit(principal,session,version,record_turn(state,safe,result))
            expected=version+1
            demo_action=None
            if result.demo_ticket_topic:
                from app.demo_ticket_api import demo_principal
                try:
                    if authorize_write:authorize_write()
                    demo_action=self.tickets.offer(demo_principal(principal,access_principal),session,result.demo_ticket_topic)
                    demo_action={**demo_action,'authenticated':access_principal is not None,'getnet_identity_verified':False}
                except Exception:
                    demo_action={'state':'not_confirmed','message':'Não foi possível preparar a proposta local; nenhum protocolo foi registrado.','synthetic_only':True,'authenticated':False,'destination':'local_demo'}
            return checked({**({'demo_action':demo_action} if demo_action else {}),'answer':DISCLOSURE+'\n\n'+str(compose_notices(*response_parts(result),credentials=redacted)),
                'sources':result.sources,'evidence_coverage':result.evidence_coverage,'grounding':[c.model_dump() for c in result.grounding],'mode':result.agentic.mode,'status':result.status,'route':result.route,
                'simulated_data':result.simulated_data,'traces':[], 'agentic':result.agentic.model_dump(),
                'documents_received':len(documents),'documents_ignored':bool(documents),'external_documents_actionable':False})
        if dependent_reference(safe):
            return super().step(principal,session,message,documents,access_principal=access_principal,authorize_write=authorize_write,**kwargs)
        # An explicit documentary question needs no inferred private facts.
        # Validate session ownership, but never promote a product mention to state.
        from app.documentary_plan import intact_documentary,needs_documentary_reference,independent_public_question
        from app.brazil_scope import scoped_parts
        _,documentary_state=self.store.read(principal,session)
        documentary_scope=all(market=='BR' for _,market in scoped_parts(safe,state=documentary_state))
        if getattr(self.local,'documentary',False) and (needs_documentary_reference(safe) or (intact_documentary(safe) and documentary_scope)):
            r=self.public(bind_input({'message':message,'user_id':principal},access_principal))
            return checked({'answer':DISCLOSURE+'\n\n'+str(compose_notices(*response_parts(r),credentials=redacted)),
                'sources':r.sources,'evidence_coverage':r.evidence_coverage,'grounding':[c.model_dump() for c in r.grounding],
                'mode':'documentary_explicit','status':r.status,'route':r.route,'simulated_data':r.simulated_data,'traces':[],
                'documents_received':len(documents),'documents_ignored':bool(documents),'external_documents_actionable':False})
        # Informação pública não recebe estado, identidade ou documentos da sessão.
        if any(is_public(p) for p in parts(safe)):
            self.store.read(principal,session) # valida titularidade sintética antes da rede
            start=time.perf_counter();r=self.public(bind_input({'message':safe,'user_id':principal},access_principal))
            return checked({'answer':DISCLOSURE+'\n\n'+str(compose_notices(*response_parts(r),credentials=redacted)), 'sources':r.sources,'evidence_coverage':r.evidence_coverage,'grounding':[c.model_dump() for c in r.grounding],'mode':'public_stateless','status':r.status,'route':r.route,'simulated_data':r.simulated_data,'traces':[v.model_dump() for v in r.eventos],'seconds':time.perf_counter()-start,'validation':{},'documents_received':len(documents),'documents_ignored':bool(documents),'external_documents_actionable':False})
        legacy_result=super().step(principal,session,message,documents,access_principal=access_principal,authorize_write=authorize_write,**kwargs)
        from app.handoff_policy import handoff_offer
        offer=handoff_offer(safe,legacy_result,enabled=getattr(self,'handoff',None) is not None)
        return {**legacy_result,**({'human_handoff_offer':offer} if offer else {})}
def create_app(provider=None,store=None,supervisor=None,tickets=None,security=None):
    from app.configuration import validate_declared
    validate_declared(injected_supervisor=supervisor is not None)
    from app.demo_ticket_api import configured_tickets,install_ticket_routes
    tickets=configured_tickets() if tickets is None else tickets
    if os.environ.get('GETNET_RAG_GENERATION','disabled')!='disabled' and supervisor is None and os.environ.get('GETNET_ORCHESTRATION','deterministic')!='supervisor':
        raise ValueError('RAG generation requires explicitly configured budgeted supervisor')
    if supervisor is None and os.environ.get('GETNET_ORCHESTRATION','deterministic')=='supervisor':
        from app.agentic_client import configured_client
        from app.agentic_capabilities import Capabilities
        from app.agentic import Supervisor
        local=configured_knowledge(Path(__file__).resolve().parent.parent/'corpus_publico')
        client=configured_client()
        generation=os.environ.get('GETNET_RAG_GENERATION','disabled')
        if generation not in ('disabled','validated'):raise ValueError('Invalid RAG generation mode')
        if generation=='validated':
            from app.rag.grounding import GroundedSynthesizer
            local.synthesizer=GroundedSynthesizer(client,max_seconds=60,evidence_filter=getattr(getattr(local,'scopes',None),'compatible',None))
            from app.public_information import PublicInformation
            if provider is None:provider=PublicInformation()
            if isinstance(provider,PublicInformation):
                provider.synthesizer=GroundedSynthesizer(client,max_seconds=60,
                    evidence_filter=lambda question,candidate:candidate.get('kind')=='web_page_excerpt')
        # Three real RAG stages need a shared bounded window, not the old 18s.
        limits=({'max_steps':3,'max_tools':2,'max_seconds':120,'step_seconds':60}
                if generation=='validated' else {})
        supervisor=Supervisor(client,Capabilities(local,public=provider,tickets=tickets),**limits)
    if supervisor is not None and hasattr(supervisor.capabilities,'tickets'):supervisor.capabilities.tickets=tickets
    service=ChallengeService(store or Store(os.environ.get('GETNET_CONTEXT_DB',str(Path(gettempdir())/'getnet-challenge/state.db'))),provider,supervisor,tickets)
    app=context_app(service,security=security)
    from app.agentic_capabilities import Capabilities
    if supervisor is not None and isinstance(supervisor.capabilities,Capabilities):supervisor.capabilities.require_principal=app.state.security.required
    service.core.business.support.allow_demo=not app.state.security.required
    install_ticket_routes(app,service,tickets)
    from app.human_handoff import HandoffStore
    from app.human_handoff_api import install_handoff_routes
    service.handoff=HandoffStore(tickets,app.state.security.store.realm) if tickets.enabled and app.state.security.required else None
    install_handoff_routes(app,service,service.handoff)
    if supervisor is not None and isinstance(supervisor.capabilities,Capabilities):supervisor.capabilities.handoff=service.handoff
    @app.get('/configuration')
    def configuration(request:Request):
        app.state.security.bind(request,getattr(getattr(request.state,'access_grant',None),'principal',None).subject if app.state.security.required else '', 'configuration:read')
        from app.public_search import configuration as search_configuration, supervisor_configuration
        return {'experience':'challenge_fit','getnet_response':'grounded_generated_opt_in' if supervisor and getattr(supervisor.capabilities.local,'synthesizer',None) else 'retrieved_extractive','llm_enabled':supervisor is not None,
            'orchestration':supervisor.client.mode if supervisor else 'deterministic',
            'rag':configuration_status(supervisor.capabilities.local if supervisor else service.local),
            'general_search':supervisor_configuration(os.environ) if supervisor else search_configuration(os.environ),
            'weather':'open_meteo','exchange':'bcb_ptax','support':'synthetic_only',
            'security':app.state.security.describe(),
            'demo_tickets':{'enabled':tickets.enabled,'confirmation':'explicit_http_only','authenticated':app.state.security.required,'destination':'local_demo'},
            'human_handoff':{'enabled':service.handoff is not None,'destination':'local_operator_demo','external_delivery':False,'response_delivery':'authenticated_session_poll'},
            'public_context':'sanitized_dialogue' if supervisor else 'stateless','env_loading':'local launcher: explicit --env-file; Compose: declared environment, no automatic .env injection'}
    return app
