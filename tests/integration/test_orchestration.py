"""Supervisor graph with a scripted LLM: parallel delegation, observation, replanning, limits."""

import json
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.graph.supervisor import MAX_SUPERVISOR_STEPS
from app.llm.client import BudgetExceeded, LLMResult
from app.main import create_app
from tests.conftest import auth
from tests.fakes import ScriptedLLM, calls, text


def _client(settings: Settings, llm: Any) -> TestClient:
    return TestClient(create_app(settings, llm=llm))


def _chat(c: TestClient, tok: str, message: str) -> Any:
    return c.post("/chat", json={"message": message, "user_id": "cliente1988"}, headers=auth(tok))


@pytest.fixture
def yesterday(settings: Settings) -> str:
    return (settings.today() - timedelta(days=1)).isoformat()


def _tool_results(request: dict[str, Any]) -> list[dict[str, Any]]:
    last = request["messages"][-1]
    assert last["role"] == "user"
    return [b for b in last["content"] if b["type"] == "tool_result"]


def test_parallel_specialists_then_synthesis(
    settings: Settings, token: Callable[..., str], yesterday: str
) -> None:
    llm = ScriptedLLM(
        {
            "supervisor": [
                calls(
                    ("ask_support", {"request": "Quando cai o dinheiro das vendas de ontem?"}),
                    ("ask_knowledge", {"question": "Como funciona a antecipação na Getnet?"}),
                ),
                text("As vendas de ontem caem conforme a agenda. Antecipação: veja [S1]."),
            ],
            "support": [
                calls(
                    (
                        "get_receivables",
                        {"by": "sale_date", "date_from": yesterday, "date_to": yesterday},
                    )
                ),
                text("STATUS: ok\nDébito cai amanhã; crédito em 30 dias."),
            ],
            "knowledge": [
                calls(("search_kb", {"query": "antecipar vendas app"})),
                text("STATUS: ok\nVocê pode antecipar pelo app [S1]."),
            ],
        }
    )
    with _client(settings, llm) as c:
        r = _chat(c, token(), "Quando cai o dinheiro de ontem? E como antecipo?")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agents_used"] == ["supervisor", "knowledge", "support"]
    assert body["outcome"] == "answered"
    tools = {(t["agent"], t["tool"]): t["status"] for t in body["tool_calls"]}
    assert tools[("support", "get_receivables")] == "ok"
    assert tools[("knowledge", "search_kb")] == "ok"
    assert tools[("supervisor", "ask_support")] == "ok"
    assert [s["id"] for s in body["sources"]] == ["S1"]
    assert body["usage"]["llm_calls"] == 6

    # Both observations go back to the supervisor in ONE user message, STATUS line stripped.
    results = _tool_results(llm.requests["supervisor"][1])
    assert len(results) == 2
    observations = [json.loads(r["content"]) for r in results]
    assert {o["data"]["coverage"] for o in observations} == {"ok"}
    assert all("STATUS" not in o["data"]["answer"] for o in observations)
    # The specialist got real data for the right merchant.
    receivables = json.loads(_tool_results(llm.requests["support"][1])[0]["content"])
    assert receivables["status"] == "ok" and receivables["data"]["total_net_brl"] > 0


def test_replans_when_knowledge_not_found(settings: Settings, token: Callable[..., str]) -> None:
    llm = ScriptedLLM(
        {
            "supervisor": [
                calls(("ask_knowledge", {"question": "Posso vender pelo WhatsApp com link?"})),
                calls(("ask_knowledge", {"question": "Link de pagamento Getnet WhatsApp"})),
                text("Sim, com o Link de Pagamento [S1]."),
            ],
            "knowledge": [
                text("STATUS: not_found\nNão encontrei."),
                calls(("search_kb", {"query": "link de pagamento"})),
                text("STATUS: ok\nSim [S1]."),
            ],
        }
    )
    with _client(settings, llm) as c:
        body = _chat(c, token(), "Posso vender pelo WhatsApp com o link?").json()
    first_observation = json.loads(_tool_results(llm.requests["supervisor"][1])[0]["content"])
    assert first_observation["status"] == "not_found"
    assert len(llm.requests["knowledge"]) == 3
    assert body["outcome"] == "answered"


def test_ask_user_ends_the_turn_with_a_question(
    settings: Settings, token: Callable[..., str]
) -> None:
    llm = ScriptedLLM({"supervisor": [calls(("ask_user", {"question": "Qual o código de erro?"}))]})
    with _client(settings, llm) as c:
        body = _chat(c, token(), "Minha maquininha deu erro").json()
    assert body["outcome"] == "clarify"
    assert body["answer"] == "Qual o código de erro?"
    assert body["agents_used"] == ["supervisor"]


def test_supervisor_loop_is_bounded(settings: Settings, token: Callable[..., str]) -> None:
    llm = ScriptedLLM(
        {
            "supervisor": [calls(("ask_support", {"request": "x"}))],
            "support": [text("STATUS: partial\nAlgo.")],
        },
        repeat_last=True,
    )
    with _client(settings, llm) as c:
        body = _chat(c, token(), "loop").json()
    assert body["outcome"] == "limit"
    assert len(llm.requests["supervisor"]) == MAX_SUPERVISOR_STEPS + 1
    assert llm.requests["supervisor"][-1]["tool_choice"] == {"type": "none"}


def test_tool_errors_are_typed_and_returned_to_the_model(
    settings: Settings, token: Callable[..., str]
) -> None:
    llm = ScriptedLLM(
        {
            "supervisor": [calls(("ask_support", {"request": "vendas"})), text("ok")],
            "support": [
                calls(
                    ("get_sales_summary", {"date_from": "2026-11-10", "date_to": "2026-11-01"}),
                    ("get_sales_summary", {"date_from": "ontem"}),
                    ("delete_everything", {}),
                ),
                text("STATUS: partial\nNão consegui."),
            ],
        }
    )
    with _client(settings, llm) as c:
        _chat(c, token(), "vendas")
    results = _tool_results(llm.requests["support"][1])
    assert all(r.get("is_error") for r in results)
    codes = [json.loads(r["content"])["error"]["code"] for r in results]
    assert codes == ["invalid_argument", "invalid_argument", "invalid_argument"]


def test_specialist_cannot_reach_other_merchant(
    settings: Settings, token: Callable[..., str]
) -> None:
    llm = ScriptedLLM(
        {
            "supervisor": [calls(("ask_support", {"request": "status T-2000-01"})), text("ok")],
            "support": [
                calls(("get_terminal_status", {"terminal_id": "T-2000-01"})),
                text("STATUS: not_found\nNão encontrado."),
            ],
        }
    )
    with _client(settings, llm) as c:
        _chat(c, token(), "status do terminal T-2000-01")
    result = json.loads(_tool_results(llm.requests["support"][1])[0]["content"])
    assert result["status"] == "not_found"


def test_budget_exhaustion_is_a_clean_503(settings: Settings, token: Callable[..., str]) -> None:
    def broke(_: list[dict[str, Any]]) -> LLMResult:
        raise BudgetExceeded("LLM budget of US$ 10.00 reached.")

    with _client(settings, ScriptedLLM({"supervisor": [broke]})) as c:
        r = _chat(c, token(), "oi")
    assert r.status_code == 503 and r.json()["error"]["code"] == "budget_exceeded"


def test_ready_when_llm_is_wired(settings: Settings) -> None:
    with _client(settings, ScriptedLLM({})) as c:
        assert c.get("/ready").json() == {"ready": True, "checks": {"database": True, "llm": True}}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    import app.tools.http as http

    def fail(*_: Any, **__: Any) -> Any:
        raise AssertionError("network access in integration tests")

    monkeypatch.setattr(http, "get_json", fail)
    yield
