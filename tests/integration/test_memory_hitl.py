"""Conversation memory, human handoff (interrupt -> operator -> resume) and two-phase tickets."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import auth
from tests.fakes import ScriptedLLM, calls, text


@pytest.fixture
def webhooks(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str | None, str, dict[str, Any]]]:
    sent: list[tuple[str | None, str, dict[str, Any]]] = []

    def record(url: str | None, secret: str | None, event: str, payload: dict[str, Any]) -> bool:
        sent.append((url, event, payload))
        return True

    monkeypatch.setattr("app.hitl.notify.send", record)
    return sent


@pytest.fixture
def hitl_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "operator_webhook_url": "http://sink/operator",
            "merchant_webhook_url": "http://sink/merchant",
        }
    )


def chat(c: TestClient, tok: str, message: str, session: str = "s1") -> dict[str, Any]:
    r = c.post(
        "/chat",
        headers=auth(tok),
        json={"message": message, "user_id": "cliente1988", "session_id": session},
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


def history_of(request: dict[str, Any]) -> list[str]:
    return [
        m["content"] if isinstance(m["content"], str) else "<blocks>" for m in request["messages"]
    ]


def test_memory_carries_previous_turns_per_session(
    settings: Settings, token: Callable[..., str]
) -> None:
    llm = ScriptedLLM(
        {"supervisor": [text("Amanhã chove em Porto Alegre."), text("Sim."), text("Olá.")]}
    )
    with TestClient(create_app(settings, llm=llm)) as c:
        chat(c, token(), "Vai chover em Porto Alegre amanhã?")
        chat(c, token(), "E depois de amanhã?")
        chat(c, token(), "Oi", session="other")
    second, third = llm.requests["supervisor"][1], llm.requests["supervisor"][2]
    assert history_of(second)[:2] == [
        "Vai chover em Porto Alegre amanhã?",
        "Amanhã chove em Porto Alegre.",
    ]
    assert len(second["messages"]) == 3 and len(third["messages"]) == 1


def test_reset_and_restart(settings: Settings, token: Callable[..., str]) -> None:
    llm = ScriptedLLM({"supervisor": [text("R1"), text("R2"), text("R3")]})
    with TestClient(create_app(settings, llm=llm)) as c:
        chat(c, token(), "primeira")
    with TestClient(create_app(settings, llm=llm)) as c:  # new process, same volume
        chat(c, token(), "segunda")
        assert c.delete("/sessions/s1", headers=auth(token())).status_code == 204
        chat(c, token(), "terceira")
    assert len(llm.requests["supervisor"][1]["messages"]) == 3  # survived the restart
    assert len(llm.requests["supervisor"][2]["messages"]) == 1  # reset cleared it


def test_handoff_pauses_notifies_and_resumes(
    hitl_settings: Settings, token: Callable[..., str], webhooks: list[Any]
) -> None:
    llm = ScriptedLLM(
        {
            "supervisor": [
                calls(
                    ("ask_support", {"request": "Vendas duplicadas de ontem?"}),
                    (
                        "escalate_to_human",
                        {
                            "reason": "charge_dispute",
                            "priority": "high",
                            "summary": "2 vendas de R$ 239,90 no cartão 8812",
                        },
                    ),
                ),
                text("O especialista confirmou a análise do estorno (protocolo citado)."),
            ],
            "support": [text("STATUS: ok\nDuas vendas iguais às 11:05 e 11:06.")],
        }
    )
    merchant, operator = token(), token(sub="operador1", scopes=("operator",))
    with TestClient(create_app(hitl_settings, llm=llm)) as c:
        first = chat(c, merchant, "Cobraram duas vezes meu cliente, quero estornar")
        assert first["outcome"] == "handoff" and first["handoff"]["status"] == "pending"
        handoff_id = first["handoff"]["id"]
        assert handoff_id in first["answer"] and "escalation" in first["agents_used"]
        assert webhooks[0][:2] == ("http://sink/operator", "handoff.created")
        assert webhooks[0][2]["priority"] == "high"

        waiting = chat(c, merchant, "e aí?")
        assert waiting["outcome"] == "handoff_pending"
        assert len(llm.requests["supervisor"]) == 1  # no model call while waiting

        assert c.get("/operator/handoffs", headers=auth(merchant)).status_code == 403
        queue = c.get("/operator/handoffs", headers=auth(operator)).json()
        assert [h["id"] for h in queue] == [handoff_id] and "scopes" not in queue[0]

        reply = c.post(
            f"/operator/handoffs/{handoff_id}/reply",
            headers=auth(operator),
            json={"action": "reply", "message": "Estorno da 2a venda em análise."},
        )
        assert reply.status_code == 200, reply.text
        assert reply.json()["outcome"] == "handoff_resolved"
        again = c.post(
            f"/operator/handoffs/{handoff_id}/reply",
            headers=auth(operator),
            json={"action": "reply", "message": "de novo"},
        )
        assert again.status_code == 409

        events = c.get("/sessions/s1/events?wait_s=1", headers=auth(merchant)).text
        assert "event: handoff.resolved" in events and handoff_id in events
        status = c.get(f"/handoffs/{handoff_id}", headers=auth(merchant)).json()
        assert status["status"] == "resolved"

    resumed = llm.requests["supervisor"][1]["messages"][-1]["content"]
    results = {json.loads(b["content"])["data"].get("operator_message", "support") for b in resumed}
    assert results == {"Estorno da 2a venda em análise.", "support"}  # one message, both results
    assert webhooks[-1][:2] == ("http://sink/merchant", "handoff.resolved")


def test_handoff_survives_restart(
    hitl_settings: Settings, token: Callable[..., str], webhooks: list[Any]
) -> None:
    llm = ScriptedLLM(
        {
            "supervisor": [
                calls(
                    (
                        "escalate_to_human",
                        {
                            "reason": "customer_request",
                            "priority": "normal",
                            "summary": "Quer falar com humano",
                        },
                    )
                ),
                text("Pronto, o especialista respondeu."),
            ]
        }
    )
    with TestClient(create_app(hitl_settings, llm=llm)) as c:
        handoff_id = chat(c, token(), "Quero falar com uma pessoa")["handoff"]["id"]
    with TestClient(create_app(hitl_settings, llm=llm)) as c:
        r = c.post(
            f"/operator/handoffs/{handoff_id}/reply",
            headers=auth(token(sub="op", scopes=("operator",))),
            json={"action": "reply", "message": "Olá, posso ajudar."},
        )
    assert r.status_code == 200 and r.json()["answer"] == "Pronto, o especialista respondeu."


def test_ticket_requires_explicit_confirmation(
    settings: Settings, token: Callable[..., str]
) -> None:
    llm = ScriptedLLM(
        {
            "supervisor": [calls(("ask_support", {"request": "abrir chamado"})), text("Proposto.")],
            "support": [
                calls(("propose_ticket", {"topic": "terminal", "summary": "Get Smart off"})),
                text("STATUS: ok\nProposta criada."),
            ],
        }
    )
    with TestClient(create_app(settings, llm=llm)) as c:
        chat(c, token(), "abre um chamado para minha maquininha")
        proposal = json.loads(llm.requests["support"][1]["messages"][-1]["content"][0]["content"])
        ticket_id = proposal["data"]["proposal_id"]
        assert c.get("/tickets", headers=auth(token())).json() == []  # not created yet
        other = c.post(f"/tickets/{ticket_id}/confirm", headers=auth(token(sub="cliente2000")))
        assert other.status_code == 404
        first = c.post(f"/tickets/{ticket_id}/confirm", headers=auth(token())).json()
        second = c.post(f"/tickets/{ticket_id}/confirm", headers=auth(token())).json()
        assert first["status"] == "open" and first == second  # idempotent
        assert [t["id"] for t in c.get("/tickets", headers=auth(token())).json()] == [ticket_id]


def test_failed_resume_returns_handoff_to_queue(
    hitl_settings: Settings, token: Callable[..., str], webhooks: list[Any]
) -> None:
    from app.llm.client import LLMResult, LLMUnavailable

    def outage(_: list[dict[str, Any]]) -> LLMResult:
        raise LLMUnavailable("provider_error_529")

    llm = ScriptedLLM(
        {
            "supervisor": [
                calls(
                    (
                        "escalate_to_human",
                        {"reason": "unresolved", "priority": "normal", "summary": "x"},
                    )
                ),
                outage,
                text("Resolvido."),
            ]
        }
    )
    operator = token(sub="op", scopes=("operator",))
    with TestClient(create_app(hitl_settings, llm=llm)) as c:
        handoff_id = chat(c, token(), "preciso de ajuda humana")["handoff"]["id"]
        url = f"/operator/handoffs/{handoff_id}/reply"
        body = {"action": "reply", "message": "ok"}
        failed = c.post(url, headers=auth(operator), json=body)
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "llm_unavailable"
        assert c.get(f"/handoffs/{handoff_id}", headers=auth(token())).json()["status"] == "pending"
        retried = c.post(url, headers=auth(operator), json=body)
        assert retried.status_code == 200 and retried.json()["answer"] == "Resolvido."
