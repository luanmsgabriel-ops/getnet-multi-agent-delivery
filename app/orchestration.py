"""Grafo G1 isolado do terminal legado; execução limitada e sem persistência."""
from time import perf_counter
from typing import Protocol, TypedDict
from uuid import uuid4
from langgraph.graph import StateGraph, START, END
from app.contracts import Entrada, Plano, RespostaEspecialista, Evento, Saida
from app.router import RouterDemo
from app.knowledge import KnowledgeDemo
from app.support import SupportDemo
from app.response_notices import Notice, compose_notices, response_parts

class Router(Protocol):
    def planejar(self, entrada: Entrada) -> Plano: ...

class Especialista(Protocol):
    def responder(self, entrada: Entrada, contexto: tuple[RespostaEspecialista, ...]) -> RespostaEspecialista: ...

class Estado(TypedDict):
    entrada: Entrada
    request_id: str
    rota: str
    respostas: list[RespostaEspecialista]
    eventos: list[Evento]
    falhou: bool
    policy_responses: list[RespostaEspecialista]
    public_input: Entrada | None

class Orquestrador:
    """Adaptadores síncronos locais: não usar provedores sem timeout próprio."""
    def __init__(self, router: Router | None = None, knowledge: Especialista | None = None,
                 support: Especialista | None = None):
        self.router = router if router is not None else RouterDemo()
        self.knowledge = knowledge if knowledge is not None else KnowledgeDemo()
        self.support = support if support is not None else SupportDemo()
        grafo = StateGraph(Estado)
        grafo.add_node("router", self._rotear)
        grafo.add_node("support", lambda estado: self._especialista(estado, "support"))
        grafo.add_node("knowledge", lambda estado: self._especialista(estado, "knowledge"))
        grafo.add_edge(START, "router")
        grafo.add_conditional_edges("router", self._apos_router,
                                   {"support": "support", "knowledge": "knowledge", "fim": END})
        grafo.add_conditional_edges("support", self._apos_support, {"knowledge": "knowledge", "fim": END})
        grafo.add_edge("knowledge", END)
        self.grafo = grafo.compile()

    def _rotear(self, estado):
        inicio = perf_counter()
        try:
            plano = Plano.model_validate(self.router.planejar(estado["entrada"]))
            from app.service_policy import service_plan
            policy = service_plan(estado['entrada'].message)
            entrada = estado['entrada']
            if policy.replies:
                if policy.message:
                    entrada = Entrada(message=policy.message,user_id=entrada.user_id)
                    plano = Plano.model_validate(self.router.planejar(entrada))
                else:
                    plano = Plano(rota='clarify')
            public_input=None
            if policy.message and plano.rota in ('support','support_knowledge'):
                from app.request_plan import independent_public_request
                partition=independent_public_request(entrada.message)
                if partition:
                    private,public=partition
                    entrada=Entrada(message=private,user_id=entrada.user_id)
                    public_input=Entrada(message=public,user_id=entrada.user_id)
                    plano=Plano(rota='support_knowledge')
            return {'public_input':public_input, "rota": plano.rota, 'entrada':entrada, 'policy_responses':list(policy.replies), "eventos": [Evento(agente="router", status="ok",
                    duracao_ms=(perf_counter()-inicio)*1000)]}
        except Exception:
            return self._falha(estado, "router", inicio)

    def _especialista(self, estado, nome):
        inicio = perf_counter()
        try:
            resposta = RespostaEspecialista.model_validate(getattr(self, nome).responder(
                estado['public_input'] if nome=='knowledge' and estado.get('public_input') else estado['entrada'],
                () if nome=='knowledge' and estado.get('public_input') else tuple(estado['respostas'])))
            return {"respostas": [*estado["respostas"], resposta],
                    "falhou": resposta.status == "indisponivel",
                    "eventos": [*estado["eventos"],
                        *[Evento(agente=nome, ferramenta=t.ferramenta, status=t.status, duracao_ms=t.duracao_ms) for t in resposta.tool_traces],
                        Evento(agente=nome, status="falha" if resposta.status == "indisponivel" else "ok",
                        duracao_ms=(perf_counter()-inicio)*1000)]}
        except Exception:
            return self._falha(estado, nome, inicio)

    @staticmethod
    def _falha(estado, nome, inicio):
        # Nunca incluir mensagem, identidade, exceção ou traceback no trace.
        return {"falhou": True, "eventos": [*estado["eventos"],
                Evento(agente=nome, status="falha", duracao_ms=(perf_counter()-inicio)*1000)]}

    @staticmethod
    def _apos_router(estado):
        if estado["falhou"] or estado["rota"] == "clarify":
            return "fim"
        return "knowledge" if estado["rota"] == "knowledge" else "support"

    @staticmethod
    def _apos_support(estado):
        # Recusa/limite encerram o fluxo: nao chamar outro adaptador apos negacao.
        blocked = any(r.status in ('recusado','limitado') and not (
            estado.get('public_input') and r.limitation_code=='unknown_demo_identity'
        ) for r in estado['respostas'])
        return "knowledge" if not estado["falhou"] and not blocked and estado["rota"] == "support_knowledge" else "fim"

    def executar(self, dados: Entrada | dict) -> Saida:
        entrada = Entrada.model_validate(dados)
        estado = self.grafo.invoke({"entrada": entrada, "request_id": str(uuid4()),
            "rota": "clarify", "respostas": [], "policy_responses":[], "public_input":None, "eventos": [], "falhou": False},
            config={"recursion_limit": 5})
        if estado["falhou"]:
            texto = "Atendimento indisponível nesta tentativa. Nenhuma operação foi confirmada; tente novamente."
            reasons={'web_disabled':'A busca externa está desativada nesta execução. Não realizei uma consulta online.','source_unavailable':'A busca oficial está indisponível nesta tentativa. Não consegui consultar a fonte; isso não significa que a informação não exista.'}
            if estado['respostas'] and estado['respostas'][-1].limitation_code in reasons:
                texto=reasons[estado['respostas'][-1].limitation_code]
        elif estado["rota"] == "clarify":
            texto = "" if estado['policy_responses'] else "Qual é sua dúvida sobre a Getnet?"
        else:
            blocks=[p for r in estado['respostas'] for p in response_parts(r)]
            # Sem aviso editorial, preservar exatamente o separador histórico dos dados.
            texto = (compose_notices(*blocks) if any(isinstance(p,Notice) for p in blocks)
                     else "\n".join(r.texto for r in estado['respostas']))
        respostas = estado["respostas"]
        if not estado['falhou'] and estado['policy_responses']:
            texto = compose_notices(texto,*(p for r in estado['policy_responses'] for p in response_parts(r)))
            respostas = [*respostas,*estado['policy_responses']]
        fontes = [] if estado["falhou"] else list(dict.fromkeys(f for r in respostas for f in r.fontes))
        modos = {r.modo for r in respostas}
        modo = "misto" if len(modos) > 1 else next(iter(modos), "demonstracao")
        status = "simulado"
        for prioridade in ("recusado", "limitado", "sem_evidencia", "evidencias"):
            if any(r.status == prioridade for r in respostas):
                status = prioridade
                break
        return Saida(request_id=estado["request_id"], route=estado["rota"],
            status="indisponivel" if estado["falhou"] else status,
            answer=str(texto), presentation=list(getattr(texto,'parts',())), sources=fontes, simulated_data=not respostas or any(r.modo == "demonstracao" for r in respostas),
            modo=modo, eventos=estado["eventos"])
