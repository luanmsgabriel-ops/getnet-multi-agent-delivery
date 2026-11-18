"""Long conversations (rolling summary) and long-term merchant memory, with a scripted LLM."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.graph.supervisor import KEEP_AFTER_SUMMARY, MAX_TURNS
from app.main import create_app
from tests.conftest import auth
from tests.fakes import ScriptedLLM, calls, text


def _chat(
    c: TestClient, tok: str, message: str, session: str = "long", user: str = "cliente1988"
) -> Any:
    return c.post(
        "/chat",
        json={"message": message, "user_id": user, "session_id": session},
        headers=auth(tok),
    )


def _first_user_message(request: dict[str, Any]) -> str:
    return str(request["messages"][0]["content"])


def _broken_summary(_: list[dict[str, Any]]) -> Any:
    raise RuntimeError("summary model unavailable")


def test_long_conversation_is_folded_into_a_summary(
    settings: Settings, token: Callable[..., str]
) -> None:
    llm = ScriptedLLM(
        {
            "supervisor": [text("Certo.")],
            "memory": [text("Lojista abriu o protocolo HD-77 sobre a máquina T-2 offline.")],
        },
        repeat_last=True,
    )
    with TestClient(create_app(settings, llm=llm)) as c:
        _chat(c, token(), "Minha máquina T-2 está offline, protocolo HD-77.")
        for n in range(MAX_TURNS):
            assert _chat(c, token(), f"Mensagem {n}").status_code == 200
        r = _chat(c, token(), "Qual era o protocolo mesmo?")
    assert r.status_code == 200
    # One summary call, covering the oldest turns, including the very first message.
    assert len(llm.requests["memory"]) == 1
    assert "HD-77" in str(llm.requests["memory"][0]["messages"][0]["content"])
    # The next turn sees the summary plus only the most recent turns verbatim.
    last = llm.requests["supervisor"][-1]
    first = _first_user_message(last)
    assert first.startswith("<earlier_conversation_summary>") and "HD-77" in first
    assert len(last["messages"]) == 2 * KEEP_AFTER_SUMMARY + 1


def test_summary_failure_never_breaks_the_turn(
    settings: Settings, token: Callable[..., str]
) -> None:
    llm = ScriptedLLM(
        {"supervisor": [text("Certo.")], "memory": [_broken_summary]}, repeat_last=True
    )
    with TestClient(create_app(settings, llm=llm)) as c:
        statuses = [_chat(c, token(), f"Mensagem {n}").status_code for n in range(MAX_TURNS + 2)]
    assert set(statuses) == {200}
    last = llm.requests["supervisor"][-1]
    assert len(last["messages"]) == 2 * MAX_TURNS + 1  # fell back to the last turns only
    assert "<earlier_conversation_summary>" not in _first_user_message(last)


def test_remember_saves_redacted_facts_per_merchant(
    settings: Settings, token: Callable[..., str]
) -> None:
    fact = "padaria com duas lojas; meu CPF é 123.456.789-09"
    llm = ScriptedLLM(
        {
            "supervisor": [
                calls(("remember", {"category": "business_profile", "value": fact})),
                text("Anotado!"),
                text("Olá de novo."),
                text("Olá, outro lojista."),
                text("Sem memória agora."),
            ]
        }
    )
    with TestClient(create_app(settings, llm=llm)) as c:
        r = _chat(c, token(), "Tenho uma padaria com duas lojas.", session="s1")
        assert r.status_code == 200
        assert r.json()["agents_used"] == ["supervisor"]  # remember is not an agent
        saved = c.get("/me/memory", headers=auth(token())).json()
        assert "padaria com duas lojas" in saved["business_profile"]
        assert "123.456.789-09" not in saved["business_profile"]

        # A new session of the same merchant gets the saved fact as a data block.
        _chat(c, token(), "Oi", session="s2")
        context = str(llm.requests["supervisor"][2]["messages"][-1]["content"])
        assert "<merchant_memory" in context and "padaria com duas lojas" in context

        # Another merchant never sees it.
        other = token(sub="cliente2002")
        assert c.get("/me/memory", headers=auth(other)).json() == {}
        _chat(c, other, "Oi", session="s1", user="cliente2002")
        assert "<merchant_memory" not in str(llm.requests["supervisor"][3]["messages"][-1])

        # The merchant can erase it.
        assert c.delete("/me/memory", headers=auth(token())).status_code == 204
        assert c.get("/me/memory", headers=auth(token())).json() == {}
        _chat(c, token(), "Oi", session="s3")
        assert "<merchant_memory" not in str(llm.requests["supervisor"][4]["messages"][-1])


def test_remember_rejects_categories_outside_the_allow_list(
    settings: Settings, token: Callable[..., str]
) -> None:
    llm = ScriptedLLM(
        {
            "supervisor": [
                calls(("remember", {"category": "password", "value": "hunter2"})),
                text("Não posso guardar isso."),
            ]
        }
    )
    with TestClient(create_app(settings, llm=llm)) as c:
        r = _chat(c, token(), "Guarda minha senha hunter2")
        assert r.status_code == 200
        assert c.get("/me/memory", headers=auth(token())).json() == {}
    result = str(llm.requests["supervisor"][1]["messages"][-1]["content"])
    assert "error" in result
