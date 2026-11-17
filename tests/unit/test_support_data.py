"""Mock merchant data: date-relative seed, ownership isolation and scopes."""

from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.data.db import Database
from app.data.seed import ensure_seed
from app.data.support_repo import SupportRepository
from app.security.auth import MERCHANT_SCOPES, AuthError, Principal

TZ = ZoneInfo("America/Sao_Paulo")
TODAY = date(2026, 11, 17)


def principal(sub: str = "cliente1988", scopes: tuple[str, ...] = MERCHANT_SCOPES) -> Principal:
    return Principal(sub=sub, tenant="demo", scopes=frozenset(scopes), jti="t")


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "t.db")
    database.init()
    ensure_seed(database, TODAY, TZ)
    return database


def test_yesterday_has_sales_and_receivables(db: Database) -> None:
    repo = SupportRepository(db, principal())
    yesterday = TODAY - timedelta(days=1)
    sales = repo.sales(yesterday, yesterday)
    assert len(sales) >= 5
    assert {s["merchant_id"] for s in sales} == {"cliente1988"}
    approved = [s["id"] for s in sales if s["status"] == "aprovada"]
    receivables = repo.receivables(yesterday, yesterday + timedelta(days=400))
    assert set(approved) <= {r["sale_id"] for r in receivables}


def test_scenario_stories_exist(db: Database) -> None:
    repo = SupportRepository(db, principal())
    declined = repo.recent_transactions("recusada", 50)
    assert {"51", "57"} <= {d["decline_code"] for d in declined}
    assert any(t["status"] == "offline" and t["connection"] == "wifi" for t in repo.terminals())
    assert repo.decline_code("51")["retry_allowed"] == 1  # type: ignore[index]


def test_seed_is_deterministic_and_rebuilt_on_new_day(db: Database) -> None:
    assert ensure_seed(db, TODAY, TZ) is False
    first = SupportRepository(db, principal()).sales(TODAY - timedelta(days=3), TODAY)
    assert ensure_seed(db, TODAY + timedelta(days=1), TZ) is True
    assert ensure_seed(db, TODAY, TZ) is True
    again = SupportRepository(db, principal()).sales(TODAY - timedelta(days=3), TODAY)
    assert first == again


def test_merchants_cannot_see_each_other(db: Database) -> None:
    a = SupportRepository(db, principal("cliente1988"))
    b = SupportRepository(db, principal("cliente2000"))
    window = (TODAY - timedelta(days=45), TODAY)
    ids_a = {s["id"] for s in a.sales(*window)}
    ids_b = {s["id"] for s in b.sales(*window)}
    assert ids_a and ids_b and not ids_a & ids_b
    assert {t["merchant_id"] for t in b.terminals()} == {"cliente2000"}
    assert a.terminals("T-2000-01") == []


def test_unknown_principal_sees_nothing(db: Database) -> None:
    repo = SupportRepository(db, principal("intruso"))
    assert repo.sales(TODAY - timedelta(days=45), TODAY) == []
    assert repo.merchant() is None


@pytest.mark.parametrize(
    ("call", "scope"),
    [
        (lambda r: r.sales(TODAY, TODAY), "sales:read"),
        (lambda r: r.recent_transactions(None, 5), "sales:read"),
        (lambda r: r.receivables(TODAY, TODAY), "receivables:read"),
        (lambda r: r.terminals(), "terminal:read"),
    ],
)
def test_each_read_requires_its_scope(db: Database, call: object, scope: str) -> None:
    scopes = tuple(s for s in MERCHANT_SCOPES if s != scope)
    with pytest.raises(AuthError) as exc:
        call(SupportRepository(db, principal(scopes=scopes)))  # type: ignore[operator]
    assert exc.value.status == 403


def test_same_card_always_has_the_same_brand(db: Database) -> None:
    sales = SupportRepository(db, principal()).recent_transactions(None, 50)
    brands: dict[str, set[str]] = {}
    for s in sales:
        if s["card_last4"]:
            brands.setdefault(s["card_last4"], set()).add(s["brand"])
    assert all(len(b) == 1 for b in brands.values())
