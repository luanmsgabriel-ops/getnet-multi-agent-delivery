"""Capacidades de leitura: identidade e política sempre pertencem ao servidor."""
from datetime import datetime, timezone
import os
import re
from app.agentic_contracts import Observation
from app.contracts import Entrada
from app.privacy import clean_message
from app.public_information import PublicInformation, public_url, suspicious, plain, WEATHER, CURRENCY
from app.knowledge import KnowledgeRag
from app.support import (SupportCatalogoDemo, SyntheticTools, RecebiveisResult,
    TerminalResult, _receivable_period_lines, _TERMINAIS, read_support_tool)
from app.tool_errors import ToolFailure, tool_failure

def safe_text(text):
    # Frases de procedimento/aviso sem valor de credencial são dados públicos.
    # Protege somente a frase completa; qualquer valor adicional volta ao redator.
    phrases=[]
    pattern=(r'(?<!\w)(?:'
        r'(?:digite|insira) (?:a|sua) senha (?:somente |apenas )?(?:na própria maquininha|no próprio aparelho)|'
        r'(?:digite|insira) (?:a|sua) senha (?:da|do) (?:sua |seu )?(?:rede|wi[-‐‑]fi|wifi)(?: com aten[cç][aã]o| corretamente)?(?: e confirme)?|'
        r'(?:digite|insira) (?:a|sua) senha(?: (?:da|do) (?:sua |seu )?(?:rede|wi[-‐‑]fi|wifi))?(?: com aten[cç][aã]o| corretamente)(?: e confirme(?: para (?:conectar|concluir a conex[aã]o|finalizar a configura[cç][aã]o))?)?|'
        r'(?:digite|insira) (?:a|sua) senha(?: (?:da|do) (?:sua |seu )?(?:rede|wi[-‐‑]fi|wifi))? e confirme(?: para (?:concluir|finalizar) a (?:conexão|conexao|configuração|configuracao))?|'
        r'(?:não|nao|nunca) (?:envie|compartilhe) (?:a |sua )?senha (?:nesta conversa|no chat)|'
        r'(?:enter|type) (?:the|your) password (?:only )?on (?:the|your) (?:device|terminal)|'
        r'(?:never|do not) (?:send|share) (?:your )?password (?:in this chat|here)'
        r')(?=[.!?;]|$)')
    def protect(m):phrases.append(m.group());return f'PROCEDIMENTOSEGURO{len(phrases)-1}X'
    clean, redacted = clean_message(re.sub(pattern,protect,text,flags=re.I))
    for i,phrase in enumerate(phrases):clean=clean.replace(f'PROCEDIMENTOSEGURO{i}X',phrase)
    # Avisos legítimos para NÃO compartilhar credenciais não são exfiltração.
    inspected=re.sub(r'\b(?:não|nao|nunca|never|do not)\s+(?:envie|compartilhe|send|share)\s+(?:a\s+|sua\s+|your\s+)?(?:senha\w*|password\w*|código\w*|codigo\w*|token\w*)',
        'orientação de privacidade',clean,flags=re.I)
    return clean, redacted or suspicious(inspected)

class Capabilities:
    def __init__(self, local, *, public=None, tools_factory=SyntheticTools, tickets=None, env=None):
        self.local = local
        self.tickets = tickets
        from app.public_search import supervisor_configuration
        env = os.environ if env is None else env
        self.public_policy = supervisor_configuration(env)
        self.public = public or PublicInformation(env={**env,
            'GETNET_PUBLIC_SEARCH': self.public_policy['provider']})
        self.tools_factory = tools_factory

    def lookup_plan(self, query, *, focus=None, goal_request=None, requested_services=(), non_geographic=()):
        """Pure, validated local query plan shared by execution and deduplication."""
        clean, unsafe = safe_text(query)
        from app.intents import request_facts
        if unsafe: return {'error':'unsafe_query'}
        if request_facts(clean).unsupported_action: return {'error':'unsupported_action'}
        from app.rag.applicability import validated_services
        try:validated_services(goal_request or clean,requested_services)
        except (TypeError,ValueError):return {'error':'unsafe_query'}
        fixed = False
        documentary = getattr(self.local,'documentary',False) is True
        bound = goal_request or ''
        if non_geographic and (not documentary or not bound):return {'error':'unsafe_query'}
        if focus or (documentary and bound):
            from app.brazil_scope import market_of
            _, bad_bound = safe_text(bound)
            if bad_bound or (focus and (focus not in bound or not re.fullmatch(r'\w+(?:-\w+)?',focus))):
                return {'error':'unsafe_query'}
            if request_facts(bound).unsupported_action:
                return {'error':'unsupported_action'}
            from app.rag.query_scope import documentary_market
            try:
                bound_market=documentary_market(bound,non_geographic) if documentary else market_of(bound)
                proposal_market=bound_market if query==bound else market_of(query)
            except ValueError:return {'error':'unsafe_query'}
            if bound_market.value in ('OUT','UNKNOWN') or proposal_market.value in ('OUT','UNKNOWN'):
                return {'error':'market_scope'}
            if documentary:
                # The immutable goal, not a model's shortened reformulation,
                # supplies retrieval, draft and judge with every condition.
                clean = bound
                # Fixed describes the execution contract, not whether this
                # particular proposal happened to need rewriting.
                fixed = True
            elif focus:
                # The previous focused lookup remains exclusive to the legacy adapter.
                products = re.findall(r'\b(?:Get\s+)?(?:Smart|Cl[aá]ssica|A920|DX8000)\b',bound,re.I)
                if products:
                    clean = ' '.join(dict.fromkeys(products))+' '+focus
                    fixed = True
        return {'query':clean, 'fixed':fixed}

    def run(self, action, query, *, owner, goal_id, observation_id, focus=None, goal_request=None, requested_services=(), non_geographic=(), deadline=None, session=None, ticket_topic=None, principal=None):
        stamp = datetime.now(timezone.utc).isoformat()
        def result(status, text, sources=(), simulated=False, limitation='', grounding=(), evidence_coverage=None):
            clean, unsafe = safe_text(text)
            if unsafe or any(not public_url(s) for s in sources):
                status,clean,sources,limitation='blocked','O retorno foi bloqueado por validação de conteúdo.',[],'untrusted_output'
            if status in ('blocked','unavailable','absent'):evidence_coverage=None
            from app.rag.grounding import retained_claims
            return Observation(evidence_coverage=evidence_coverage,grounding=retained_claims(grounding,clean[:4000],list(sources)[:3]),id=observation_id,goal_id=goal_id,capability=action,status=status,
                content=clean[:4000],sources=list(sources)[:3],simulated=simulated,observed_at=stamp,limitation=limitation)
        if action.startswith("support_") and getattr(self,"require_principal",False) and principal is None:
            return result("blocked","Identidade autenticada ausente.",limitation="tool_permission_denied")
        clean, unsafe = safe_text(query)
        if unsafe: return result('blocked','Consulta rejeitada pela política do servidor.',limitation='unsafe_query')
        from app.intents import request_facts
        if request_facts(clean).unsupported_action:
            return result('blocked','Não disponho de ferramenta para executar operações financeiras, alterar serviços ou transferir atendimento. Nenhuma ação foi realizada.',limitation='unsupported_action')
        if action in ('support_ticket_prepare','support_ticket_status'):
            from app.demo_ticket_api import demo_principal,requested_local_demo_ticket
            if self.tickets is None or not self.tickets.enabled:
                return result('blocked','Registro local demonstrativo desativado; nada foi registrado.',limitation='demo_disabled')
            if not session:
                return result('blocked','Use uma sessão demonstrativa para propor um registro local.',limitation='demo_session_required')
            try: principal=demo_principal(owner,principal)
            except PermissionError:return result('blocked','Identidade demonstrativa desconhecida.',limitation='unknown_demo_identity')
            if any(t in plain(clean) for t in ('outra conta','outro cliente','loja_ficticia_','demo-b','demo_b','outro usuario')):
                return result('blocked','Não posso apresentar o protocolo desta sessão como se pertencesse a outra identidade.',limitation='identity_boundary')
            from app.brazil_scope import market_of
            if market_of(clean).value in ('OUT','UNKNOWN'):
                return result('blocked','O registro demonstrativo desta sessão não atende outro mercado solicitado.',limitation='market_scope')
            if action=='support_ticket_prepare':
                if 'demo_ticket:write' not in principal.scopes:return result('blocked','Permissao de escrita ausente.',limitation='tool_permission_denied')
                if ticket_topic not in ('conectividade','recebiveis','terminal') or not requested_local_demo_ticket(goal_request or clean):
                    return result('blocked','Não há pedido explícito para uma proposta local demonstrativa; nada foi registrado.',limitation='demo_request_required')
                # This tool is PURE: only the interface may persist a proposal
                # after the graph returns; it never creates a support protocol.
                return result('partial','Posso propor um registro local demonstrativo de '+ticket_topic+'. Nenhum protocolo foi registrado. Revise a proposta na interface e confirme explicitamente; responder sim no chat não confirma. Nada será enviado à Getnet ou a um atendente.',simulated=True,limitation='demo_confirmation_required').model_copy(update={'demo_ticket_topic':ticket_topic})
            handoff=getattr(self,'handoff',None)
            if handoff is not None:
                try: human=handoff.latest(principal,session)
                except Exception:return result('unavailable','Não foi possível consultar o atendimento local. Não repeti escrita.',limitation='tool_provider_failure')
                if human is not None:
                    lines=['Último encaminhamento local '+human['protocol']+'; estado '+human['state']+'. Não enviado à Getnet. Respondido ou encerrado não confirma resolução.']
                    responses=[event for event in human.get('events',[]) if event['kind']=='response']
                    if responses:
                        event=responses[-1]
                        lines.append('Última resposta histórica do operador local '+event['operator_id']+' (identificador local, não identidade pessoal verificada): '+event['text'])
                    lines.append('O histórico completo e outros protocolos são consultáveis por identificador na interface local.')
                    return result('complete','\n'.join(lines),simulated=True)
            try: receipt=self.tickets.latest(principal,session)
            except Exception:return result('unavailable','Não foi possível confirmar o estado do registro local. Não repeti a escrita.',limitation='tool_provider_failure')
            if receipt is None:return result('absent','Não há protocolo local confirmado nesta sessão demonstrativa.',limitation='demo_ticket_absent')
            return result('complete','Protocolo demonstrativo '+receipt['protocol']+' registrado somente nesta sessão deste protótipo, categoria '+receipt['topic']+'. Não enviado à Getnet; nenhum atendente foi notificado.',simulated=True)
        if action.startswith('knowledge_'):
            if action=='knowledge_getnet':
                plan=self.lookup_plan(query,focus=focus,goal_request=goal_request,requested_services=requested_services,non_geographic=non_geographic)
                if 'error' in plan:
                    return result('blocked','Consulta local rejeitada pela política ou vínculo do servidor.',limitation=plan['error'])
                clean=plan['query']
            if action == 'knowledge_public':
                # Uma pergunta geral não pode ativar Tavily por troca de ambiente.
                if self.public_policy['provider'] != 'mwmbl' and not (WEATHER.search(plain(clean)) or CURRENCY.search(plain(clean))):
                    return result('unavailable','A pesquisa pública geral não está habilitada nesta configuração; não fiz consulta externa.',limitation='search_paused')
                response = (self.public.answer(goal_request or clean,search_query=clean,deadline=deadline)
                            if isinstance(self.public,PublicInformation) else self.public.answer(clean))
            else:
                options={'deadline':deadline}
                if getattr(self.local,'documentary',False) is True and focus:
                    options['focus']=focus
                if getattr(self.local,'documentary',False) is True and requested_services:
                    options['requested_services']=requested_services
                if getattr(self.local,'documentary',False) is True and non_geographic:
                    options['non_geographic']=non_geographic
                response = (self.local._single(Entrada(message=clean,user_id='public_query'),(),**options)
                    if isinstance(self.local,KnowledgeRag) else self.local.responder(Entrada(message=clean,user_id='public_query'),()))
            if action=='knowledge_getnet' and focus:
                from app.agentic_contracts import Goal
                from app.agentic_semantics import missing_attributes
                if missing_attributes(Goal(id=goal_id,request=goal_request,focus=focus),[response.texto]):
                    return result('absent','Não confirmei nas fontes locais o atributo: '+focus,limitation='sem_evidencia')
            status = {'evidencias':'complete','sem_evidencia':'absent','indisponivel':'unavailable','recusado':'blocked','limitado':'partial','simulado':'partial'}[response.status]
            # Fonte válida não prova completude. O modelo recebe a evidência e
            # deve julgar adequação ao objetivo; estado complete é disponibilidade.
            return result(status,response.texto,response.fontes,False,
                response.limitation_code or ('' if status=='complete' and action=='knowledge_public' and (WEATHER.search(plain(clean)) or CURRENCY.search(plain(clean))) else 'evidence_requires_relevance_review' if status=='complete' else response.status),response.grounding,response.evidence_coverage)
        if re.search(r"\b(?:nao|do not|don't)\s+(?:\w+\s+){0,2}(?:consulte|consultar|consult|check|access|verifique|acesse)\b",plain(clean)):
            return result('blocked','A solicitação restringe a consulta; nenhuma ferramenta individual foi chamada.',limitation='individual_request_required')
        from app.support import resolve_principal
        principal = resolve_principal(owner,principal)
        if principal is None:
            return result('blocked','Identificador sem catálogo de demonstração. Não tenho acesso a conta real e não realizei consulta.',limitation='unknown_demo_identity')
        if any(t in plain(clean) for t in ('outra conta','outro cliente','loja_ficticia_', 'demo-b', 'demo_b','outro usuario')):
            return result('blocked','Não posso consultar dados de outra identidade.',limitation='identity_boundary')
        from app.brazil_scope import market_of
        if market_of(clean).value in ('OUT','UNKNOWN'):
            return result('blocked','As ferramentas fictícias são de demonstração Getnet Brasil. Não há consulta deste mercado.',limitation='market_scope')
        def failure(error):
            safe=tool_failure(error)
            return result('blocked' if safe.blocked else 'unavailable',str(safe),limitation=safe.code)
        try: tools=self.tools_factory(principal)
        except Exception as error: return failure(error)
        if action == 'support_receivables':
            from app.intents import receivable_query
            period=receivable_query(clean)
            if not period.individual:
                return result('blocked','A pergunta não autoriza consulta individual de recebíveis. Use conhecimento público para explicações gerais.',limitation='individual_request_required')
            if period.needs_period:
                return result('partial',period.period_issue or 'De qual data são as vendas? Preciso do período antes de consultar a agenda fictícia.',limitation='period_required')
            try: data=read_support_tool(tools,principal,'consultar_recebiveis')
            except ToolFailure as error: return failure(error)
            if period.sale_period or period.settlement_period:
                lines,status=_receivable_period_lines(data,period)
                return result('complete' if status=='simulado' else 'partial',' '.join(lines),simulated=True)
            cents=data['total_centavos']
            return result('complete',f'Dados fictícios: total da agenda demonstrativa R$ {cents//100},{cents%100:02d}. Sem acesso a conta, depósito real ou condições comerciais.',simulated=True)
        if action == 'support_terminal':
            if not re.search(r'\b(?:maquininha|maquina|terminal|a920|dx8000|pax|card machine)\b',plain(clean)):
                return result('blocked','Não há pedido pertinente a terminal nesta parte da solicitação. Nenhuma consulta foi realizada.',limitation='individual_request_required')
            try: data=read_support_tool(tools,principal,'consultar_terminal')
            except ToolFailure as error: return failure(error)
            return result('complete',f"Terminal fictício {data['terminal_id']}: {data['status']}. É uma fixture; não diagnostica a maquininha física nem explica uma falha de conexão ou recusa.",simulated=True,limitation='status_only_not_diagnosis')
        raise ValueError('Unknown capability')
