"""Decisões operacionais tipadas; não contêm raciocínio privado nem autoridade."""
import re
from typing import Literal,Annotated
from app.rag.grounding import GroundedClaim
from app.demo_tickets import TicketTopic
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

Capability = Literal['knowledge_getnet', 'knowledge_public', 'support_receivables', 'support_terminal', 'support_ticket_prepare', 'support_ticket_status']
Action = Literal['knowledge_getnet', 'knowledge_public', 'support_receivables', 'support_terminal', 'support_ticket_prepare', 'support_ticket_status', 'finish', 'clarify', 'limit']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)

class Goal(StrictModel):
    current_request_quote: str | None = Field(default=None, min_length=1, max_length=1000,
        description='Para uma continuacao reformulada, copie TODO o pedido atual literalmente e indique context_turn_id. O servidor ignora request interpretado e executa somente historico literal + esta ancora. Nos demais casos use null.')
    context_turn_id: str | None = Field(default=None, pattern=r'^t_[a-f0-9]{16,32}$')
    id: str = Field(pattern=r'^g[1-4]$')
    request: str = Field(min_length=1, max_length=1000, description="Trecho literal contíguo, sem reconstruir prefixos. Para partes documentais relacionadas, mantenha o pedido integral; não copie o prefixo de produto para uma oração diferente.")
    focus: str | None = Field(default=None, min_length=1, max_length=160,
        description='Use null para um único goal documental. Focus não é produto, tema ou palavra-chave de busca; só é usado em múltiplos goals que repartem atributos atômicos explícitos do mesmo request, cobrindo todos eles.')
    retrieval_services: list[Literal['crediario','anticipation','pix','link','dcc']] = Field(default_factory=list, max_length=3)
    non_geographic_spans: list[Annotated[str,Field(min_length=1,max_length=100)]] = Field(default_factory=list,max_length=4)

class Resolution(StrictModel):
    goal_id: str = Field(pattern=r'^g[1-4]$')
    status: Literal['answered', 'partial', 'missing', 'unavailable', 'pending']
    observation_ids: list[str] = Field(default_factory=list, max_length=6)

class Decision(StrictModel):
    ticket_topic: TicketTopic | None = None
    action: Action
    goals: list[Goal] = Field(default_factory=list, max_length=4, description='Preencha somente na fase initial. Em after_observation, use [] e preserve os goals existentes do payload.')
    goal_id: str | None = None
    query: str | None = Field(default=None, max_length=1000)
    uses: list[str] = Field(default_factory=list, max_length=6)
    resolutions: list[Resolution] = Field(default_factory=list, max_length=4, description='Use [] em ações knowledge_* ou support_*. Em finish/limit, resolva todos os goals com observações existentes. Não misture consulta com resolução.')
    clarification: Literal['request', 'currency_pair', 'date', 'location', 'terminal', 'terminal_error', 'connectivity', 'market'] | None = None
    reason: Literal['initial_request', 'need_evidence', 'need_guidance', 'sufficient', 'partial', 'missing', 'unavailable', 'ambiguous']

    @model_validator(mode='after')
    def shape(self):
        if (self.action=='support_ticket_prepare') != (self.ticket_topic is not None):
            raise ValueError('Ticket topic is required only for a demo proposal')
        if self.action in ('finish', 'limit', 'clarify'):
            if self.query is not None: raise ValueError('Terminal decision cannot call a tool')
            if self.action == 'clarify' and (self.clarification is None or self.goal_id is None):
                raise ValueError('Clarification needs target')
        elif not self.goal_id or not self.query or self.resolutions or self.clarification:
            raise ValueError('Capability needs one goal and query')
        return self

# The model sees action-specific shapes. The canonical Decision and its guards
# remain the server contract; no missing goal/query is inferred during conversion.
class ChoiceBase(StrictModel):
    uses: list[str] = Field(default_factory=list,max_length=6)
    reason: Literal['initial_request','need_evidence','need_guidance','sufficient','partial','missing','unavailable','ambiguous']

class ToolChoice(ChoiceBase):
    action: Literal['knowledge_getnet','support_receivables','support_terminal','support_ticket_prepare','support_ticket_status']
    goal_id: str = Field(pattern=r'^g[1-4]$')
    query: str = Field(min_length=1,max_length=1000)
    ticket_topic: TicketTopic | None = None

class PublicToolChoice(ToolChoice):
    action: Literal['knowledge_public'] = Field(description='Use para clima, câmbio ou assunto geral externo ao atendimento Getnet. Perguntas sobre produtos, serviços e recebimento de vendas neste atendimento consultam knowledge_getnet primeiro, mesmo sem repetir a marca. Só considere busca geral para essas perguntas após observação de ausência de fonte pertinente no corpus.')

class EndResolution(Resolution):
    status: Literal['answered','partial','missing','unavailable']

class EndChoice(ChoiceBase):
    action: Literal['finish','limit'] = Field(description='Antes de encerrar uma resposta parcial, verifique se falta um dado do usuário que algum campo de clarification pode obter. Nesse caso use clarify, preservando observações úteis. Uma definição genérica não resolve um problema individual; falha de ferramenta por si só não pede esclarecimento.')
    resolutions: list[EndResolution] = Field(min_length=1,max_length=4)

class ClarifyChoice(ChoiceBase):
    action: Literal['clarify']
    goal_id: str = Field(pattern=r'^g[1-4]$')
    clarification: Literal['request','currency_pair','date','location','terminal','terminal_error','connectivity','market']
    resolutions: list[Resolution] = Field(default_factory=list,max_length=4)

class DecisionProposal(StrictModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True,title='Decision')
    goals: list[Goal] = Field(default_factory=list,max_length=4)
    choice: ToolChoice | PublicToolChoice | EndChoice | ClarifyChoice

    def canonical(self):
        return Decision.model_validate({**self.choice.model_dump(),
                                        'goals':[g.model_dump() for g in self.goals]})


def literal_request_choices(request):
    """Offer literal spans, not a semantic decomposition or a routing decision.

    Keep the full request. Bound the wire size; long/complex requests retain the
    existing canonical quote validation without an enum. History uses that same
    existing contract, rather than guessing a current/historical concatenation.
    """
    if not isinstance(request,str) or not request or len(request)>1000:return None
    starts={0};ends={len(request)}
    for match in re.finditer(r'[;.!?,]\s*|\s+(?:e|and|também|tambem|also)\s+',request,re.I):
        starts.add(match.end());ends.add(match.start());ends.add(match.end())
    if len(starts)>12:return None
    choices=[request]
    for start in sorted(starts):
        for end in sorted(ends):
            value=request[start:end].strip()
            if start<end and value and value not in choices:choices.append(value)
    return choices if len(choices)<=80 and sum(map(len,choices))<=6000 else None


def decision_schema(*,initial,observation_ids=(),public_request=None,public_query_choices=None,allow_scope_plan=True,literal_request=None,documentary_mode=False):
    schema=DecisionProposal.model_json_schema()
    if documentary_mode:
        schema['$defs']['Goal']['properties']['focus']={'type':'null','description':'Atributos documentais são obligations do RAG. Use um goal integral; separe apenas pedidos independentes.'}
    choices=literal_request_choices(literal_request) if initial else None
    if choices:schema['$defs']['Goal']['properties']['request']['enum']=choices
    if not allow_scope_plan:
        schema['$defs']['Goal']['properties']['non_geographic_spans']['maxItems']=0
    # Do not embed a request-derived unbounded regex in the provider grammar.
    # Literal word binding remains enforced by bound_search_query on the server.
    schema['$defs']['PublicToolChoice']['properties']['query']['description']='Para assunto geral, use o nome do assunto ou objeto: uma expressão nominal curta, sem moldura interrogativa nem verbo da pergunta. Não copie o request inteiro. Em nova busca após source_insufficient, escolha entre as opções o núcleo temático mais curto ainda não tentado. Use somente palavras literais do request, sem tradução para outro idioma, e preserve nomes e condições essenciais. Clima e câmbio exigem o request integral. O servidor preserva o pedido completo na síntese e valida o vínculo.'
    if public_query_choices is not None:
        field=schema['$defs']['PublicToolChoice']['properties']['query']
        field.pop('pattern',None)
        if public_query_choices:field['enum']=public_query_choices
        else:
            schema['properties']['choice']['anyOf']=[v for v in schema['properties']['choice']['anyOf'] if v.get('$ref')!='#/$defs/PublicToolChoice']
    schema['properties']['goals']['minItems']=1 if initial else 0
    schema['properties']['goals']['maxItems']=4 if initial else 0
    # Historical conversation IDs are never current tool evidence.
    for definition in schema.get('$defs',{}).values():
        for name,field in definition.get('properties',{}).items():
            if name in ('uses','observation_ids'):
                if observation_ids:field['items']={'type':'string','enum':list(observation_ids)}
                else:field['maxItems']=0
    return schema


def parse_decision(raw):
    # Compatibility for existing scripted/canonical callers. The remote JSON
    # schema only accepts the proposal shape; both paths use all runtime guards.
    return DecisionProposal.model_validate(raw).canonical() if isinstance(raw,dict) and 'choice' in raw else Decision.model_validate(raw)


class Observation(StrictModel):
    demo_ticket_topic: TicketTopic | None = None

    @model_validator(mode='after')
    def demo_offer_only(self):
        if self.demo_ticket_topic is not None and (self.capability!='support_ticket_prepare' or self.status!='partial' or not self.simulated):
            raise ValueError('Invalid demo offer binding')
        return self

    evidence_coverage: Literal['not_assessed', 'partial', 'supported'] | None = None
    grounding: list[GroundedClaim] = Field(default_factory=list,max_length=12)
    id: str = Field(pattern=r'^o[1-6]$')
    goal_id: str = Field(pattern=r'^g[1-4]$')
    capability: Capability
    status: Literal['complete', 'partial', 'absent', 'unavailable', 'blocked']
    content: str = Field(max_length=4000)
    sources: list[str] = Field(default_factory=list, max_length=3)
    simulated: bool = False
    observed_at: str = Field(max_length=40)
    limitation: Literal['','generation_unavailable','source_insufficient','answer_rejected_with_sufficient_source','answer_rejected','budget_exhausted','untrusted_output','unsafe_query','unsupported_action','search_paused',
        'evidence_requires_relevance_review','web_disabled','source_unavailable','unknown_demo_identity',
        'evidencias','sem_evidencia','indisponivel','recusado','limitado','simulado',
        'identity_boundary','market_scope','period_required','individual_request_required',
        'status_only_not_diagnosis','tool_failure','tool_permission_denied','tool_invalid_result','tool_timeout','tool_provider_failure','demo_disabled','demo_confirmation_required','demo_session_required','demo_request_required','demo_ticket_absent'] = ''

    @field_validator('observed_at')
    @classmethod
    def timestamp(cls,value):
        from datetime import datetime
        parsed=datetime.fromisoformat(value)
        if parsed.tzinfo is None:raise ValueError('Timezone required')
        return value

class TraceEvent(StrictModel):
    step: int
    kind: Literal['decision', 'observation', 'guard', 'stop']
    action: str
    goal_id: str | None = None
    observation_id: str | None = None
    status: str
    uses: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    seconds: float = Field(default=0, ge=0)

class RunInfo(StrictModel):
    mode: Literal['model_supervisor', 'controlled_supervisor']
    stop: str
    decisions: int
    tool_calls: int
    trace: list[TraceEvent]
    coverage: list[Resolution]
    context_mode: Literal['stateless', 'sanitized_dialogue'] = 'stateless'
    clarification: str | None = None
    clarification_goal_id: str | None = None
    goals: list[Goal] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
