"""Metrics, traces, structured logs and feedback."""

import json
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.config import Settings
from app.main import create_app
from tests.conftest import auth
from tests.fakes import ScriptedLLM, calls, text

_EXPORTER = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def _tracing() -> Iterator[None]:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
    trace.set_tracer_provider(provider)
    yield


def _llm() -> ScriptedLLM:
    return ScriptedLLM(
        {
            "supervisor": [calls(("ask_support", {"request": "status"})), text("Tudo certo.")],
            "support": [
                calls(("get_terminal_status", {"terminal_id": None})),
                text("STATUS: ok\nOnline."),
            ],
        }
    )


def test_chat_produces_trace_tree_and_metrics(
    settings: Settings, token: Callable[..., str]
) -> None:
    _EXPORTER.clear()
    with TestClient(create_app(settings, llm=_llm())) as c:
        body = c.post(
            "/chat",
            headers=auth(token()),
            json={"message": "status da maquininha", "user_id": "cliente1988"},
        ).json()
        metrics = c.get("/metrics").text
    spans = {s.name: s for s in _EXPORTER.get_finished_spans()}
    assert {"POST /chat", "tool.ask_support", "agent.support", "tool.get_terminal_status"} <= set(
        spans
    )
    root = spans["POST /chat"]
    assert body["trace_id"] == format(root.context.trace_id, "032x")
    assert spans["tool.get_terminal_status"].attributes["agent"] == "support"
    assert 'chat_turns_total{outcome="answered"}' in metrics
    assert 'tool_calls_total{agent="support",status="ok",tool="get_terminal_status"}' in metrics
    assert 'http_requests_total{route="/chat",status="200"}' in metrics
    assert "cliente1988" not in metrics  # no merchant ids in labels


def test_logs_are_json_with_request_id_and_no_message_text(
    settings: Settings, token: Callable[..., str], capsys: pytest.CaptureFixture[str]
) -> None:
    with TestClient(create_app(settings, llm=_llm())) as c:
        c.post(
            "/chat",
            headers={**auth(token()), "x-request-id": "req-123"},
            json={"message": "segredo do lojista 4111 1111 1111 1111", "user_id": "cliente1988"},
        )
    lines = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    turn = next(entry for entry in lines if entry["msg"] == "chat_turn")
    assert turn["request_id"] == "req-123" and turn["outcome"] == "answered"
    assert turn["redacted"] == ["card_number"]
    assert "segredo" not in json.dumps(lines) and "4111" not in json.dumps(lines)


def test_feedback_is_recorded(settings: Settings, token: Callable[..., str]) -> None:
    with TestClient(create_app(settings, llm=_llm())) as c:
        r = c.post(
            "/feedback",
            headers=auth(token()),
            json={"request_id": "req-1", "rating": "down", "comment": "valor errado"},
        )
        assert r.status_code == 204
        assert 'feedback_total{rating="down"}' in c.get("/metrics").text
        assert c.post("/feedback", json={"request_id": "x", "rating": "up"}).status_code == 401
