"""Final-answer verifier (docs/adr/012) with a scripted LLM: pass, replan, limit, skip."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agents.base import ToolContext, cited_evidence
from app.config import Settings
from app.data.db import Database
from app.llm.client import AnthropicLLM, Ledger
from app.main import create_app
from app.security.auth import Principal
from tests.conftest import auth
from tests.fakes import ScriptedLLM, text


def _chat(c: TestClient, tok: str, message: str) -> Any:
    r = c.post("/chat", json={"message": message, "user_id": "cliente1988"}, headers=auth(tok))
    assert r.status_code == 200, r.text
    return r.json()


def _verifier_events(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for t in body["tool_calls"] if t["tool"] == "verify_answer"]


def test_high_risk_answer_is_checked_by_the_verifier_model(
    settings: Settings, token: Callable[..., str]
) -> None:
    llm = ScriptedLLM({"supervisor": [text("Anotei: seu protocolo é HD-77.")]})
    with TestClient(create_app(settings, llm=llm)) as c:
        body = _chat(c, token(), "Meu protocolo anterior é HD-77, anota aí?")
    assert body["answer"] == "Anotei: seu protocolo é HD-77."
    (request,) = llm.requests["verifier"]
    assert request["model"] == settings.verifier_model == "claude-haiku-5-5"
    prompt = request["messages"][0]["content"]
    assert "HD-77, anota" in prompt  # the merchant's own words are evidence
    assert "<answer>" in prompt and "Router/Supervisor" not in prompt  # never the supervisor prompt
    assert _verifier_events(body)[0]["status"] == "ok"


def test_unsupported_figure_makes_the_supervisor_replan(
    settings: Settings, token: Callable[..., str]
) -> None:
    llm = ScriptedLLM(
        {
            "supervisor": [
                text("A taxa do crédito à vista é 2,99%."),
                text("Não consegui confirmar a taxa nas fontes oficiais."),
            ]
        }
    )
    with TestClient(create_app(settings, llm=llm)) as c:
        body = _chat(c, token(), "Qual a taxa do crédito?")
    assert body["answer"] == "Não consegui confirmar a taxa nas fontes oficiais."
    feedback = llm.requests["supervisor"][1]["messages"][-1]["content"]
    assert "<verification>" in feedback and "2,99%" in feedback
    assert "verifier" not in llm.requests  # caught by the free rule check, no model call
    assert [e["arguments"]["result"] for e in _verifier_events(body)] == ["replan", "skipped"]


def test_claim_unsupported_twice_is_removed_with_a_limitation(
    settings: Settings, token: Callable[..., str]
) -> None:
    verdict = text(json.dumps({"unsupported": [{"claim": "limite é 5000", "reason": "no data"}]}))
    answer = "Seu limite é 5000 reais por dia.\nPosso ajudar em algo mais?"
    llm = ScriptedLLM({"supervisor": [text(answer), text(answer)], "verifier": [verdict, verdict]})
    with TestClient(create_app(settings, llm=llm)) as c:
        body = _chat(c, token(), "Qual meu limite diário?")
    assert "5000" not in body["answer"]
    assert "Posso ajudar em algo mais?" in body["answer"]
    assert "não puderam ser confirmadas" in body["answer"]  # reply language detected: pt
    assert [e["arguments"]["result"] for e in _verifier_events(body)] == ["replan", "limited"]


def test_low_risk_answer_skips_the_model(settings: Settings, token: Callable[..., str]) -> None:
    llm = ScriptedLLM({"supervisor": [text("Olá! Como posso ajudar você hoje?")]})
    with TestClient(create_app(settings, llm=llm)) as c:
        body = _chat(c, token(), "Oi")
    assert "verifier" not in llm.requests
    assert _verifier_events(body)[0]["arguments"]["result"] == "skipped"


def test_web_citations_become_evidence(settings: Settings) -> None:
    ctx = ToolContext(
        principal=Principal("cliente1988", "demo", frozenset(), jti="t"),
        db=Database(settings.data_dir / "x.db"),
        now=settings.now(),
        llm=ScriptedLLM({}),
    )
    content = [
        {
            "type": "text",
            "text": "A taxa é 1,99% [web].",
            "citations": [{"url": "https://site.getnet.com.br/x", "cited_text": "taxa de 1,99%"}],
        }
    ]
    cited_evidence(content, ctx)
    assert ctx.evidence == ["[web https://site.getnet.com.br/x] taxa de 1,99%"]


def test_haiku_requests_carry_no_server_side_fallback(tmp_path: Path) -> None:
    db = Database(tmp_path / "l.db")
    db.init()
    llm = AnthropicLLM("sk-test", Ledger(db, 10.0))
    sent: dict[str, Any] = {}

    class Stop(Exception):
        pass

    def capture(**kwargs: Any) -> Any:
        sent.update(kwargs)
        raise Stop

    llm._client.beta.messages.create = capture  # type: ignore[method-assign]
    for model, expects_fallback in (("claude-haiku-5-5", False), ("claude-sonnet-5-5", True)):
        sent.clear()
        with pytest.raises(Stop):
            llm.create(agent="x", system="s", messages=[], tools=[], effort="low", model=model)
        assert sent["model"] == model
        assert ("fallbacks" in sent) is expects_fallback
