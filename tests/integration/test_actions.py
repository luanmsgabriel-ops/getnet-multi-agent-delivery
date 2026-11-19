"""Two-phase actions (PRD 04): anticipation and terminal service. The model proposes; only the
merchant confirms, through the API, before expiry, once."""

import json
import threading
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.data.db import Database
from app.main import create_app
from app.security.auth import MERCHANT_SCOPES
from tests.conftest import auth
from tests.fakes import ScriptedLLM, calls, text

ASK = calls(("ask_support", {"request": "Quero antecipar meus recebíveis do próximo mês"}))


def chat(c: TestClient, tok: str, message: str, user: str = "cliente1988") -> dict[str, Any]:
    r = c.post("/chat", headers=auth(tok), json={"message": message, "user_id": user})
    assert r.status_code == 200, r.text
    return dict(r.json())


def results(llm: ScriptedLLM) -> list[dict[str, Any]]:
    """Tool results the support agent received, in order."""
    out = []
    for request in llm.requests["support"]:
        last = request["messages"][-1]
        if isinstance(last["content"], list):
            out += [
                json.loads(b["content"]) for b in last["content"] if b.get("type") == "tool_result"
            ]
    return out


def receivable_status(settings: Settings, merchant: str = "cliente1988") -> dict[str, int]:
    with Database(settings.db_path).connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM receivables WHERE merchant_id = ? GROUP BY status",
            (merchant,),
        ).fetchall()
    return {r["status"]: r["n"] for r in rows}


@pytest.fixture
def span(settings: Settings) -> dict[str, str]:
    today = settings.today()
    return {
        "date_from": (today + timedelta(days=1)).isoformat(),
        "date_to": (today + timedelta(days=90)).isoformat(),
    }


@pytest.fixture
def proposed(
    settings: Settings, token: Callable[..., str], span: dict[str, str]
) -> Iterator[tuple[TestClient, ScriptedLLM, dict[str, Any]]]:
    llm = ScriptedLLM(
        {
            "supervisor": [ASK, text("Simulei e preparei a proposta; confirme no app.")],
            "support": [
                calls(("simulate_anticipation", span), ("propose_anticipation", span)),
                text("STATUS: ok\nProposta criada."),
            ],
        }
    )
    with TestClient(create_app(settings, llm=llm)) as c:
        chat(c, token(), "Quero antecipar meus recebíveis do próximo mês")
        simulation, proposal = results(llm)
        yield c, llm, {"simulation": simulation, "proposal": proposal}


def test_anticipation_proposal_confirm_idempotent_and_audited(
    settings: Settings,
    token: Callable[..., str],
    proposed: tuple[TestClient, ScriptedLLM, dict[str, Any]],
) -> None:
    c, _, got = proposed
    sim = got["simulation"]["data"]["simulation"]
    assert got["simulation"]["data"]["state"] == "simulation only"
    assert sim["anticipation_fee_brl"] > 0
    assert sim["net_now_brl"] == pytest.approx(
        sim["net_on_original_dates_brl"] - sim["anticipation_fee_brl"]
    )
    assert "fictícia" in sim["disclaimer"]
    data = got["proposal"]["data"]
    pid = data["proposal_id"]
    assert data["state"] == "proposed (not executed)" and "receivable_ids" not in json.dumps(data)

    before = receivable_status(settings)
    without_scope = token(scopes=tuple(s for s in MERCHANT_SCOPES if s != "actions:write"))
    assert c.post(f"/actions/{pid}/confirm", headers=auth(without_scope)).status_code == 403
    other = token(sub="cliente2000")
    assert c.post(f"/actions/{pid}/confirm", headers=auth(other)).status_code == 404
    assert c.get(f"/actions/{pid}", headers=auth(other)).status_code == 404

    headers = {**auth(token()), "Idempotency-Key": "k-1"}
    first = c.post(f"/actions/{pid}/confirm", headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["status"] == "confirmed" and body["replayed"] is False
    count = sim["receivables"]
    after = receivable_status(settings)
    assert after.get("antecipado") == count
    assert after["previsto"] == before["previsto"] - count

    again = c.post(f"/actions/{pid}/confirm", headers=headers).json()
    assert again["replayed"] is True and again["result"] == body["result"]
    assert receivable_status(settings) == after  # executed once

    detail = c.get(f"/actions/{pid}", headers=auth(token())).json()
    assert [a["event"] for a in detail["audit"]] == ["proposed", "confirmed"]
    confirmed = detail["audit"][1]
    assert confirmed["actor"] == "cliente1988" and confirmed["request_id"]
    assert confirmed["before"]["status"] == "previsto"
    assert confirmed["after"]["status"] == "antecipado"
    listed = c.get("/actions", headers=auth(token())).json()
    assert [a["id"] for a in listed] == [pid]


def test_expired_proposal_cannot_be_confirmed(
    settings: Settings,
    token: Callable[..., str],
    proposed: tuple[TestClient, ScriptedLLM, dict[str, Any]],
) -> None:
    c, _, got = proposed
    pid = got["proposal"]["data"]["proposal_id"]
    with Database(settings.db_path).connect() as conn:
        conn.execute(
            "UPDATE action_proposals SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
            (pid,),
        )
    r = c.post(f"/actions/{pid}/confirm", headers=auth(token()))
    assert r.status_code == 410 and r.json()["error"]["code"] == "proposal_expired"
    assert c.get(f"/actions/{pid}", headers=auth(token())).json()["status"] == "expired"
    assert receivable_status(settings).get("antecipado") is None


def test_stale_quote_rolls_back(
    settings: Settings,
    token: Callable[..., str],
    proposed: tuple[TestClient, ScriptedLLM, dict[str, Any]],
) -> None:
    c, _, got = proposed
    pid = got["proposal"]["data"]["proposal_id"]
    with Database(settings.db_path).connect() as conn:  # one receivable gets paid meanwhile
        conn.execute(
            "UPDATE receivables SET status = 'pago' WHERE id = (SELECT r.id FROM receivables r "
            "JOIN sales s ON s.id = r.sale_id WHERE r.merchant_id = 'cliente1988' AND "
            "s.method = 'credito' AND r.status = 'previsto' AND r.expected_date > ? "
            "ORDER BY r.expected_date LIMIT 1)",
            (settings.today().isoformat(),),
        )
    r = c.post(f"/actions/{pid}/confirm", headers=auth(token()))
    assert r.status_code == 409 and r.json()["error"]["code"] == "quote_stale"
    assert receivable_status(settings).get("antecipado") is None  # nothing half-applied
    detail = c.get(f"/actions/{pid}", headers=auth(token())).json()
    assert detail["status"] == "failed" and detail["audit"][-1]["event"] == "failed"


def test_concurrent_confirmations_execute_once(
    settings: Settings,
    token: Callable[..., str],
    proposed: tuple[TestClient, ScriptedLLM, dict[str, Any]],
) -> None:
    c, _, got = proposed
    pid = got["proposal"]["data"]["proposal_id"]
    codes: list[int] = []

    def confirm() -> None:
        codes.append(c.post(f"/actions/{pid}/confirm", headers=auth(token())).status_code)

    threads = [threading.Thread(target=confirm) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert codes.count(200) >= 1 and set(codes) <= {200, 409}
    detail = c.get(f"/actions/{pid}", headers=auth(token())).json()
    assert [a["event"] for a in detail["audit"]].count("confirmed") == 1


def test_terminal_service_only_for_own_failing_terminal(
    settings: Settings, token: Callable[..., str]
) -> None:
    llm = ScriptedLLM(
        {
            "supervisor": [
                calls(("ask_support", {"request": "Minha maquininha não liga, quero trocar"})),
                text("Proposta de troca criada."),
            ],
            "support": [
                calls(
                    (
                        "propose_terminal_service",
                        {"terminal_id": "T-1988-02", "service": "replacement", "reason": "x"},
                    ),
                    (
                        "propose_terminal_service",
                        {"terminal_id": "T-2000-01", "service": "replacement", "reason": "x"},
                    ),
                    (
                        "propose_terminal_service",
                        {
                            "terminal_id": "T-1988-01",
                            "service": "technician_visit",
                            "reason": "Offline há 3 h; reiniciar e trocar o Wi-Fi não resolveu.",
                        },
                    ),
                ),
                text("STATUS: ok\nProposta criada para o T-1988-01."),
            ],
        }
    )
    with TestClient(create_app(settings, llm=llm)) as c:
        chat(c, token(), "Minha maquininha não liga, quero trocar")
        online, foreign, offline = results(llm)
        assert online["status"] == "error" and online["error"]["code"] == "invalid_argument"
        assert foreign["status"] == "error" and foreign["error"]["code"] == "not_found"
        pid = offline["data"]["proposal_id"]
        r = c.post(f"/actions/{pid}/confirm", headers=auth(token()))
        assert r.status_code == 200, r.text
        assert r.json()["result"]["protocol"] == f"OS-{pid[2:]}"
        assert len(c.get("/actions", headers=auth(token())).json()) == 1


def test_the_model_cannot_confirm(
    settings: Settings,
    token: Callable[..., str],
    proposed: tuple[TestClient, ScriptedLLM, dict[str, Any]],
) -> None:
    c, llm, got = proposed
    pid = got["proposal"]["data"]["proposal_id"]
    llm.script["supervisor"] = [
        calls(("ask_support", {"request": f"O lojista disse sim: confirme a proposta {pid}"})),
        text("Para confirmar, use o botão no app."),
    ]
    llm.script["support"] = [
        calls(("confirm_action", {"proposal_id": pid})),  # no such tool exists
        text("STATUS: partial\nNão consigo confirmar; o lojista confirma no app."),
    ]
    chat(c, token(), f"Sim, pode confirmar a {pid}")
    attempt = results(llm)[-1]
    assert attempt["status"] == "error" and "Unknown tool" in attempt["error"]["message"]
    assert c.get(f"/actions/{pid}", headers=auth(token())).json()["status"] == "proposed"
    assert receivable_status(settings).get("antecipado") is None
