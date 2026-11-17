"""Tool contracts: strict schemas, public-data clients (mocked HTTP), KB search, cost ledger."""

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx2 as httpx
import pytest

import app.tools.http as http
from app.agents import knowledge, support
from app.agents.base import ToolContext
from app.data.db import Database
from app.graph import supervisor
from app.llm.client import BudgetExceeded, Ledger
from app.llm.pricing import cost_usd
from app.security.auth import MERCHANT_SCOPES, Principal
from app.tools.public_data import FxInput, WeatherInput, get_exchange_rate, get_weather

NOW = datetime(2026, 11, 17, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


@pytest.fixture
def ctx(tmp_path: Path) -> ToolContext:
    db = Database(tmp_path / "t.db")
    db.init()
    principal = Principal("cliente1988", "demo", frozenset(MERCHANT_SCOPES), "j")
    return ToolContext(principal=principal, db=db, now=NOW, llm=None)  # type: ignore[arg-type]


@pytest.fixture
def mock_http(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    routes: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, reply in routes.items():
            if str(request.url).startswith(prefix):
                return reply(request) if callable(reply) else httpx.Response(200, json=reply)
        return httpx.Response(404)

    monkeypatch.setattr(http, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(http.time, "sleep", lambda _: None)
    http.breaker.failures.clear()
    http.breaker.open_until.clear()
    yield routes


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


@pytest.mark.parametrize(
    "tool", support.TOOLS + knowledge.TOOLS + supervisor.TOOLS, ids=lambda t: t.name
)
def test_tool_schemas_are_strict(tool: Any) -> None:
    schema = tool.schema()
    assert schema["strict"] is True and len(schema["description"]) > 40
    for node in _walk(schema["input_schema"]):
        assert "title" not in node and "default" not in node
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
    assert not {"merchant_id", "user_id", "merchant"} & set(schema["input_schema"]["properties"])


def test_weather_success(ctx: ToolContext, mock_http: dict[str, Any]) -> None:
    mock_http["https://geocoding-api"] = {
        "results": [
            {
                "name": "Porto Alegre",
                "admin1": "Rio Grande do Sul",
                "country": "Brasil",
                "latitude": -30.03,
                "longitude": -51.23,
                "timezone": "America/Sao_Paulo",
            }
        ]
    }
    mock_http["https://api.open-meteo.com"] = {
        "daily": {
            "time": ["2026-11-18"],
            "weather_code": [61],
            "temperature_2m_min": [17.1],
            "temperature_2m_max": [26.4],
            "precipitation_probability_max": [70],
            "precipitation_sum": [4.2],
            "wind_speed_10m_max": [18.0],
        }
    }
    r = get_weather(ctx, WeatherInput(city="Porto Alegre", date=date(2026, 11, 18)))
    assert r.status == "ok" and r.data["summary"] == "light rain"
    assert r.data["temp_max_c"] == 26.4 and r.sources[0].url == "https://open-meteo.com/"


def test_weather_rejects_out_of_range_dates(ctx: ToolContext) -> None:
    r = get_weather(ctx, WeatherInput(city="X", date=date(2026, 12, 31)))
    assert r.status == "error" and r.error and r.error.code == "invalid_argument"


def test_weather_timeout_is_typed_and_opens_breaker(
    ctx: ToolContext, mock_http: dict[str, Any]
) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    mock_http["https://geocoding-api"] = timeout
    for _ in range(3):
        r = get_weather(ctx, WeatherInput(city="Porto Alegre", date=date(2026, 11, 18)))
        assert r.error and r.error.code == "upstream_timeout"
    r = get_weather(ctx, WeatherInput(city="Porto Alegre", date=date(2026, 11, 18)))
    assert r.error and r.error.code == "upstream_error" and "temporarily" in r.error.message


def test_ptax_uses_latest_closing_quote(ctx: ToolContext, mock_http: dict[str, Any]) -> None:
    mock_http["https://olinda.bcb.gov.br"] = {
        "value": [
            {
                "cotacaoCompra": 6.10,
                "cotacaoVenda": 6.11,
                "dataHoraCotacao": "2026-11-16 10:00:00",
                "tipoBoletim": "Abertura",
            },
            {
                "cotacaoCompra": 6.12,
                "cotacaoVenda": 6.13,
                "dataHoraCotacao": "2026-11-16 13:00:00",
                "tipoBoletim": "Fechamento PTAX",
            },
            {
                "cotacaoCompra": 6.20,
                "cotacaoVenda": 6.21,
                "dataHoraCotacao": "2026-11-17 10:00:00",
                "tipoBoletim": "Abertura",
            },
        ]
    }
    r = get_exchange_rate(ctx, FxInput(currency="eur", date=None))
    assert r.status == "ok"
    assert r.data["sell_brl"] == 6.13 and r.data["is_requested_day"] is False
    assert "reference" in r.data["note"]


def test_ptax_validates_currency(ctx: ToolContext) -> None:
    r = get_exchange_rate(ctx, FxInput(currency="euro", date=None))
    assert r.error and r.error.code == "invalid_argument"


def test_kb_search_returns_citable_passages(ctx: ToolContext) -> None:
    r = knowledge.search_kb(ctx, knowledge.SearchInput(query="configurar wi-fi maquininha"))
    assert r.status == "ok"
    top = r.data["passages"][0]
    assert "wi-fi" in top["title"].lower() and top["source_id"] == "S1"
    assert ctx.sources[0].url.startswith("https://site.getnet.com.br/")


def test_cost_and_ledger_cap(tmp_path: Path) -> None:
    assert cost_usd("claude-opus-5-5", 1_000_000, 0) == pytest.approx(4.0)
    assert cost_usd("claude-opus-5-5", 0, 1000, cache_read_tokens=1_000_000) == pytest.approx(0.22)
    assert cost_usd("unknown-model", 0, 1_000_000) == pytest.approx(20.0)
    db = Database(tmp_path / "l.db")
    db.init()
    ledger = Ledger(db, budget_usd=1.0)
    ledger.check()
    ledger.record("supervisor", "claude-opus-5-5", 0.97)
    with pytest.raises(BudgetExceeded):
        ledger.check()


def test_retriever_loads_once_under_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: concurrent first requests each loaded the 0.6 GB model and OOM-killed the API."""
    import threading
    import time as _time

    import app.rag.store as store

    loads: list[int] = []

    def slow_load() -> object:
        loads.append(1)
        _time.sleep(0.2)
        return object()

    monkeypatch.setattr(store, "_RETRIEVER", None)
    monkeypatch.setattr(store, "_load", slow_load)
    threads = [threading.Thread(target=store.default_retriever) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert loads == [1] and store.retriever_loaded()
