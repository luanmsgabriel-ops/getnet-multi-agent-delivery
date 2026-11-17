"""Deterministic, date-relative mock data for three fictitious merchants.

Data is generated relative to "today" (America/Sao_Paulo) so questions like
"yesterday's sales" always have an answer. The seed is rebuilt when the date changes.
All values are fictitious and exist only to exercise the Support Agent tools.
"""

import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.data.db import MOCK_TABLES, Database

SEED_VERSION = "2"
HISTORY_DAYS = 45

MERCHANTS = [
    # id, tenant, trade name, settlement account, credit settlement days
    ("cliente1988", "demo", "Padaria Bom Pão (fictícia)", "Conta Getnet •••• 1988", 30),
    ("cliente2000", "demo", "Mercadinho Avenida (fictício)", "Banco parceiro •••• 2000", 30),
    ("cliente3000", "demo", "Ótica Central (fictícia)", "Conta Getnet •••• 3000", 2),
]

TERMINALS = [
    # id, merchant, model, connection, status, last seen (hours ago), firmware
    ("T-1988-01", "cliente1988", "Get Smart", "wifi", "offline", 3, "5.2.1"),
    ("T-1988-02", "cliente1988", "Get Clássica", "chip_4g", "online", 0, "3.8.0"),
    ("T-2000-01", "cliente2000", "Get Smart", "chip_4g", "online", 0, "5.2.1"),
    ("T-3000-01", "cliente3000", "Get Clássica", "wifi", "online", 0, "3.8.0"),
]

# Common issuer response codes (illustrative mapping for the demo).
DECLINE_CODES = [
    (
        "05",
        "Não autorizada pelo emissor (recusa genérica)",
        "Peça outro meio de pagamento; o portador deve contatar o banco emissor.",
        0,
    ),
    ("14", "Cartão inválido", "Confira o cartão e tente outro meio de pagamento.", 0),
    (
        "51",
        "Saldo ou limite insuficiente",
        "Ofereça outro cartão, débito ou Pix; o portador deve verificar o limite.",
        1,
    ),
    ("54", "Cartão vencido", "Solicite outro cartão.", 0),
    ("55", "Senha incorreta", "Peça para o portador digitar a senha novamente.", 1),
    (
        "57",
        "Transação não permitida para este cartão",
        "O cartão não aceita esse tipo de transação; ofereça outra forma de pagamento.",
        0,
    ),
    (
        "59",
        "Suspeita de fraude pelo emissor",
        "Não insista; o portador deve contatar o emissor.",
        0,
    ),
    ("91", "Emissor indisponível no momento", "Aguarde alguns minutos e tente novamente.", 1),
]

FEE_RATES = {"debito": 0.0137, "credito": 0.0315, "pix": 0.0099}
BRANDS = ["Visa", "Mastercard", "Elo"]


def _next_business_day(day: date) -> date:
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def ensure_seed(db: Database, today: date, tz: ZoneInfo) -> bool:
    """Rebuild mock tables if they were seeded for another day. Returns True if reseeded."""
    marker = f"{SEED_VERSION}:{today.isoformat()}"
    if db.get_meta("seed") == marker:
        return False
    with db.connect() as conn:
        for table in MOCK_TABLES:
            conn.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed table names
        conn.executemany("INSERT INTO merchants VALUES (?, ?, ?, ?, ?)", MERCHANTS)
        conn.executemany("INSERT INTO decline_codes VALUES (?, ?, ?, ?)", DECLINE_CODES)
        now = datetime.combine(today, time(15, 0), tz)
        conn.executemany(
            "INSERT INTO terminals VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (tid, mid, model, conn_type, status, _iso(now - timedelta(hours=hrs)), fw)
                for tid, mid, model, conn_type, status, hrs, fw in TERMINALS
            ],
        )
        sales, receivables = _generate(today, tz)
        conn.executemany("INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", sales)
        conn.executemany("INSERT INTO receivables VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", receivables)
        db.set_meta(conn, "seed", marker)
    return True


def _generate(
    today: date, tz: ZoneInfo
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    sales: list[tuple[object, ...]] = []
    receivables: list[tuple[object, ...]] = []
    credit_days = {m[0]: m[4] for m in MERCHANTS}
    terminals_by_merchant: dict[str, list[str]] = {}
    for tid, mid, *_ in TERMINALS:
        terminals_by_merchant.setdefault(mid, []).append(tid)

    def add_sale(
        merchant: str,
        sold_at: datetime,
        method: str,
        amount: int,
        installments: int,
        status: str,
        decline: str | None,
        last4: str | None,
        terminal: str,
    ) -> None:
        sale_id = f"S-{merchant[-4:]}-{len(sales) + 1:05d}"
        # the brand is a property of the card, so the same card always has the same brand
        brand = "Pix" if method == "pix" else BRANDS[int(last4 or "0") % len(BRANDS)]
        sales.append(
            (
                sale_id,
                merchant,
                terminal,
                _iso(sold_at),
                method,
                brand,
                None if method == "pix" else last4,
                amount,
                installments,
                status,
                decline,
            )
        )
        if status != "aprovada":
            return
        day = sold_at.date()
        for n in range(1, installments + 1):
            if method == "pix":
                expected = day
            elif method == "debito":
                expected = _next_business_day(day + timedelta(days=1))
            else:
                expected = _next_business_day(day + timedelta(days=credit_days[merchant] * n))
            gross = amount // installments + (amount % installments if n == 1 else 0)
            fee = round(gross * FEE_RATES[method])
            state = "pago" if expected <= today - timedelta(days=1) else "previsto"
            receivables.append(
                (
                    f"R-{sale_id[2:]}-{n}",
                    merchant,
                    sale_id,
                    n,
                    expected.isoformat(),
                    gross,
                    fee,
                    gross - fee,
                    state,
                )
            )

    for merchant, *_ in MERCHANTS:
        rng = random.Random(f"{merchant}:{SEED_VERSION}")  # same pattern every day
        terminals = terminals_by_merchant[merchant]
        for offset in range(HISTORY_DAYS, -1, -1):
            day = today - timedelta(days=offset)
            if offset == 0:
                count = 4  # partial day
            else:
                count = rng.randint(6, 14) if day.weekday() < 6 else rng.randint(2, 5)
            for _ in range(count):
                sold_at = datetime.combine(day, time(rng.randint(8, 19), rng.randint(0, 59)), tz)
                method = rng.choices(["credito", "debito", "pix"], weights=[45, 35, 20])[0]
                installments = 1
                if method == "credito" and rng.random() < 0.3:
                    installments = rng.choice([2, 3, 4, 6])
                amount = rng.randint(900, 48000)
                declined = method != "pix" and rng.random() < 0.06
                code = rng.choice(["05", "51", "51", "55", "91"]) if declined else None
                add_sale(
                    merchant,
                    sold_at,
                    method,
                    amount,
                    installments,
                    "recusada" if declined else "aprovada",
                    code,
                    f"{rng.randint(0, 9999):04d}",
                    rng.choice(terminals),
                )

    # Fixed "stories" for cliente1988 used by the challenge scenarios.
    yesterday = today - timedelta(days=1)

    def at(day: date, hour: int, minute: int) -> datetime:
        return datetime.combine(day, time(hour, minute), tz)

    add_sale(
        "cliente1988",
        at(yesterday, 17, 40),
        "credito",
        15890,
        1,
        "recusada",
        "51",
        "4421",
        "T-1988-02",
    )
    add_sale(
        "cliente1988", at(today, 9, 12), "debito", 4250, 1, "recusada", "57", "7310", "T-1988-02"
    )
    # Possible duplicate charge (same card, same amount, 1 minute apart) -> human review.
    add_sale(
        "cliente1988",
        at(yesterday, 11, 5),
        "credito",
        23990,
        1,
        "aprovada",
        None,
        "8812",
        "T-1988-02",
    )
    add_sale(
        "cliente1988",
        at(yesterday, 11, 6),
        "credito",
        23990,
        1,
        "aprovada",
        None,
        "8812",
        "T-1988-02",
    )
    return sales, receivables
