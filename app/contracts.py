"""Contratos da orquestração G1; nenhuma identidade aqui autentica clientes."""
from typing import Literal
from app.response_notices import Notice
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    message: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")

    @field_validator("message")
    @classmethod
    def nao_vazia(cls, value):
        if not value.strip():
            raise ValueError("Mensagem vazia")
        return value

class Plano(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    rota: Literal["knowledge", "support", "support_knowledge", "clarify"]

class ToolTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    ferramenta: Literal["consultar_recebiveis", "consultar_terminal"]
    status: Literal["ok", "falha"]
    duracao_ms: float = Field(ge=0, allow_inf_nan=False)

class RespostaEspecialista(BaseModel):
    presentation: list[str | Notice] = Field(default_factory=list, exclude=True)
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    texto: str = Field(min_length=1, max_length=4000)
    status: Literal["simulado", "indisponivel", "evidencias", "sem_evidencia", "recusado", "limitado"] = "simulado"
    limitation_code: Literal["web_disabled", "source_unavailable", "unknown_demo_identity"] | None = None
    fontes: list[str] = Field(default_factory=list, max_length=3)
    tool_traces: list[ToolTrace] = Field(default_factory=list, max_length=2)
    modo: Literal["demonstracao", "extrativo", "gerado", "pesquisa"] = "demonstracao"

    @field_validator("texto")
    @classmethod
    def nao_vazio(cls, value):
        if not value.strip():
            raise ValueError("Resposta vazia")
        return value

class Evento(BaseModel):
    agente: Literal["router", "knowledge", "support"]
    status: Literal["ok", "falha"]
    ferramenta: Literal["consultar_recebiveis", "consultar_terminal"] | None = None
    duracao_ms: float

class Saida(BaseModel):
    presentation: list[str | Notice] = Field(default_factory=list, exclude=True)
    request_id: str
    route: Literal["knowledge", "support", "support_knowledge", "clarify"]
    status: Literal["simulado", "indisponivel", "evidencias", "sem_evidencia", "recusado", "limitado"]
    answer: str
    sources: list[str] = Field(default_factory=list)
    simulated_data: bool = True
    eventos: list[Evento]
    modo: Literal["demonstracao", "extrativo", "gerado", "pesquisa", "misto"] = "demonstracao"
