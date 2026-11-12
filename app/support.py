"""Customer Support sem acesso a dados ou ferramentas reais nesta etapa."""
from app.contracts import Entrada, RespostaEspecialista, ToolTrace
from time import perf_counter
from app.response_notices import TECHNICAL_LIMIT, Notice

class SupportDemo:
    def responder(self, entrada: Entrada, contexto: tuple[RespostaEspecialista, ...]) -> RespostaEspecialista:
        return RespostaEspecialista(texto="Demonstração: rota de suporte selecionada. Nenhuma consulta a recebíveis ou terminal foi realizada.")

# Fixtures publicas exclusivamente sinteticas. Nao adicionar dados reais aqui.
from dataclasses import dataclass
from types import MappingProxyType
import unicodedata

@dataclass(frozen=True)
class Principal:
    """Contexto confiavel criado pelo servidor, nunca pelo texto ou user_id."""
    subject: str
    tenant: str
    scopes: frozenset[str]

DEMO_PRINCIPAL = Principal('demo_A', 'loja_ficticia_A', frozenset({'recebiveis:read', 'terminal:read'}))
_RECEBIVEIS = MappingProxyType({'loja_ficticia_A': 125000, 'loja_ficticia_B': 987600})
_TERMINAIS = MappingProxyType({'loja_ficticia_A': ('DEMO-A-001', 'online'), 'loja_ficticia_B': ('DEMO-B-001', 'offline')})

from pydantic import BaseModel, ConfigDict, Field, model_validator
from datetime import date, datetime, timedelta, timezone
from typing import Literal

# Deslocamentos de uma simulação, NÃO prazos comerciais nem dias úteis Getnet.
_SCHEDULE=MappingProxyType({
    'loja_ficticia_A':((-1,2,75000),(-2,3,50000)),
    'loja_ficticia_B':((-1,5,987600),),
})

def simulation_date():
    """Dia de referência do protótipo em UTC-03, independente do fuso Docker."""
    return datetime.now(timezone(timedelta(hours=-3))).date()
class SettlementRow(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    sale_date: date
    expected_date: date
    amount_centavos: int = Field(ge=1,le=1_000_000_000_000)
    @model_validator(mode='after')
    def chronological(self):
        if self.expected_date < self.sale_date:raise ValueError('Agenda invalida')
        return self

class RecebiveisResult(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    simulated: Literal[True]
    currency: Literal['BRL']
    total_centavos: int = Field(ge=0,le=1_000_000_000_000)
    reference_date: date | None = None
    schedule: list[SettlementRow] = Field(default_factory=list,max_length=20)
    @model_validator(mode='after')
    def consistent(self):
        if self.schedule and (self.reference_date is None or sum(r.amount_centavos for r in self.schedule)!=self.total_centavos):
            raise ValueError('Agenda inconsistente')
        return self


class TerminalResult(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    simulated: Literal[True]
    terminal_id: str = Field(pattern=r'^DEMO-[AB]-[0-9]{3}$')
    status: Literal['online','offline']

class SyntheticTools:
    """Somente leitura, tenant derivado do principal vinculado pelo servidor."""
    def __init__(self, principal: Principal, *, today=None):
        self.principal = principal
        self.today = today if today is not None else simulation_date
    def _authorize(self, scope):
        if scope not in self.principal.scopes:
            raise PermissionError('Operacao nao autorizada')
        if self.principal.tenant not in _RECEBIVEIS:
            raise PermissionError('Operacao nao autorizada')
    def consultar_recebiveis(self):
        self._authorize('recebiveis:read')
        reference = self.today()  # Uma leitura por consulta, inclusive na virada do dia.
        if type(reference) is not date:
            raise ValueError('Data de simulacao invalida')
        return {'simulated': True, 'currency': 'BRL', 'total_centavos': _RECEBIVEIS[self.principal.tenant], 'reference_date':reference,'schedule':[{'sale_date':reference+timedelta(days=sold),'expected_date':reference+timedelta(days=expected),'amount_centavos':amount} for sold,expected,amount in _SCHEDULE[self.principal.tenant]]}
    def consultar_terminal(self):
        self._authorize('terminal:read')
        terminal,status = _TERMINAIS[self.principal.tenant]
        return {'simulated': True, 'terminal_id': terminal, 'status': status}

def _receivable_period_lines(data, query):
    """Filtra somente a agenda sintética validada, no campo temporal pedido."""
    reference=data['reference_date']
    try:
        sale=query.sale_period.resolve(reference) if query.sale_period else None
        settlement=query.settlement_period.resolve(reference) if query.settlement_period else None
    except (ValueError,TypeError,OverflowError) as error:
        return [str(error)+' Não posso confirmar o recebimento nem usar o total sem esse período.'],'limitado'
    if sale and sale[1]>reference:
        return ['O período de venda inclui uma data futura. A fixture não permite prever vendas que ainda serão feitas; informe um período de vendas realizadas.'],'limitado'
    def label(bounds):
        return bounds[0].isoformat() if bounds[0]==bounds[1] else f'{bounds[0].isoformat()} a {bounds[1].isoformat()} (inclusive)'
    descriptions=[]
    if sale:descriptions.append('vendas de '+label(sale))
    if settlement:descriptions.append('créditos previstos de '+label(settlement))
    lines=[f'Cenário fictício: data de referência {reference.isoformat()} (UTC-03); consulta de '+ '; '.join(descriptions)+', sem acesso a sua conta real.']
    sale_rows=[row for row in data['schedule'] if not sale or sale[0]<=row['sale_date']<=sale[1]]
    selected=[row for row in sale_rows if not settlement or settlement[0]<=row['expected_date']<=settlement[1]]
    if not selected:
        lines.append('Não há vendas correspondentes nesta agenda sintética.' if sale and not sale_rows else 'Não há créditos previstos correspondentes nesta agenda sintética.')
        lines.append('Isso não confirma ausência de vendas ou recebimentos na sua conta real.')
    if sale and settlement:
        lines.append('Para as vendas selecionadas, '+('há' if selected else 'não há')+' crédito previsto no período de recebimento solicitado.')
    for row in selected:
        amount=row['amount_centavos']
        lines.append(f"Venda ficticia de {row['sale_date'].isoformat()}: R$ {amount//100},{amount%100:02d}, crédito previsto na fixture em {row['expected_date'].isoformat()}.")
    if sale and settlement and not selected and sale_rows:
        for row in sale_rows:
            lines.append(f"A venda fictícia de {row['sale_date'].isoformat()} tem previsão em {row['expected_date'].isoformat()}, fora do período de recebimento solicitado.")
    if selected and (query.explicit_total or any(bounds and bounds[0]!=bounds[1] for bounds in (sale,settlement))):
        cents=sum(row['amount_centavos'] for row in selected)
        lines.append(f'Total deste recorte fictício: R$ {cents//100},{cents%100:02d}.')
    lines.append('Nao e promessa de deposito real nem regra de prazo da Getnet. A agenda informa previsões sintéticas, não comprova liquidação ou depósito realizado.')
    return lines,'simulado'


class SupportSintetico:
    def __init__(self, principal=DEMO_PRINCIPAL, tools=None, *, today=None):
        self.principal = principal
        self.tools = tools if tools is not None else SyntheticTools(principal, today=today)
        if self.tools.principal != principal:
            raise ValueError('Contexto de ferramenta divergente')
    def responder(self, entrada, contexto):
        # user_id so verifica consistencia. Nao concede identidade ou tenant.
        if entrada.user_id != self.principal.subject:
            return RespostaEspecialista(texto='Acesso recusado: identificador nao corresponde ao contexto desta demonstracao.',status='recusado')
        from app.knowledge import KnowledgeRag
        if KnowledgeRag._suspicious(entrada.message):
            return RespostaEspecialista(texto='Nao posso alterar regras ou consultar outra conta.',status='recusado')
        from app.intents import normalize, classify
        text=normalize(entrada.message)
        intent=classify(entrada.message)
        # Nenhuma consulta aceita conta/tenant/terminal informado pelo interlocutor.
        if any(word in text for word in ('outra conta','outro cliente','loja_ficticia_', 'demo-b', 'demo_b', 'troque o tenant')):
            return RespostaEspecialista(texto='Nao posso consultar dados de outra conta.',status='recusado')
        lines=[]
        response_status="simulado"
        traces=[]
        def call(name):
            started=perf_counter()
            status='falha'
            try:
                result=getattr(self.tools,name)()
                schema=RecebiveisResult if name=='consultar_recebiveis' else TerminalResult
                result=schema.model_validate(result).model_dump()
                if name=='consultar_terminal' and result['terminal_id'] != _TERMINAIS[self.principal.tenant][0]:
                    raise PermissionError('Resultado nao pertence ao contexto')
                status='ok'
                return result
            finally:
                traces.append(ToolTrace(ferramenta=name,status=status,duracao_ms=(perf_counter()-started)*1000))
        try:
            if intent.receivables:
                from app.rag.scope import FOREIGN
                import re
                if set(re.findall(r'\w+',text)) & FOREIGN:
                    return RespostaEspecialista(texto='As fixtures de recebíveis são uma simulação brasileira. Não há consulta individual disponível para o mercado estrangeiro solicitado; nenhuma agenda desse país foi confirmada.',status='limitado')
                from app.intents import receivable_query
                query=receivable_query(entrada.message)
                if query.needs_period:
                    lines.append((query.period_issue or 'De qual data são as vendas que você quer consultar? Preciso do período para selecionar a agenda fictícia.')+' Nenhuma consulta foi realizada.')
                    response_status='limitado' if query.period_issue else 'simulado'
                else:
                    data=call('consultar_recebiveis')
                    if query.sale_period or query.settlement_period:
                        period_lines,response_status=_receivable_period_lines(data,query)
                        lines.extend(period_lines)
                    else:
                        cents=data['total_centavos']
                        lines.append(f'Recebiveis ficticios: R$ {cents//100},{cents%100:02d}.')
            from app.intents import request_facts
            decline = request_facts(entrada.message).decline
            if decline:
                lines.append('Nao ha ferramenta de consulta de transacoes reais nesta demonstracao; estado do terminal nao determina motivo de recusa.')
            if not decline and intent.terminal:
                data=call('consultar_terminal')
                lines.append(f"Terminal ficticio {data['terminal_id']}: {data['status']}.")
        except PermissionError:
            return RespostaEspecialista(texto='Consulta nao autorizada neste contexto.',status='recusado',tool_traces=traces)
        except Exception:
            return RespostaEspecialista(texto='Consulta indisponivel. Nenhuma operacao foi confirmada.',status='indisponivel',tool_traces=traces)
        if not lines:
            return RespostaEspecialista(texto='Nesta demonstracao posso consultar recebiveis ou estado do terminal ficticio.')
        return RespostaEspecialista(texto='SIMULACAO: dados sinteticos, sem acesso a conta real. '+ ' '.join(lines),status=response_status,tool_traces=traces)


class SupportCatalogoDemo:
    """Seleção de fixtures públicas, não autenticação ou autorização bancária.

    Somente dois identificadores cadastrados pelo servidor selecionam a mesma
    loja fictícia. Outros IDs nunca selecionam tenant nem executam ferramentas.
    SupportSintetico continua vinculado a um único Principal imutável.
    """
    def __init__(self, *, today=None):
        self.today = today
        self._principals=MappingProxyType({
            'demo_A': DEMO_PRINCIPAL,
            'cliente1988': Principal('cliente1988', DEMO_PRINCIPAL.tenant, DEMO_PRINCIPAL.scopes),
        })

    def responder(self, entrada, contexto):
        from app.intents import normalize
        text=normalize(entrada.message)
        # Security denial is distinct from a missing demonstration identity.
        if any(word in text for word in ('outra conta','outro cliente','loja_ficticia_', 'demo-b', 'demo_b', 'troque o tenant')):
            return RespostaEspecialista(texto='Não posso consultar dados de outra conta.',status='recusado')
        principal=self._principals.get(entrada.user_id)
        if principal is not None:
            return SupportSintetico(principal=principal, today=self.today).responder(entrada,contexto)
        from app.intents import public_technical_only
        from app.knowledge import KnowledgeRag
        if public_technical_only(entrada.message) and not KnowledgeRag._suspicious(entrada.message):
            return RespostaEspecialista(
                texto=TECHNICAL_LIMIT, presentation=[Notice('technical')],
                status='simulado')
        return RespostaEspecialista(texto='Não tenho acesso à sua conta para consultar vendas ou recebimentos. Nenhuma consulta foi realizada. Confira a agenda de recebimentos no app Getnet Brasil ou Portal do Cliente; não consigo confirmar uma data de depósito real.',status='recusado',limitation_code='unknown_demo_identity')
