"""Figure check: fees, limits and deadlines must come from the retrieved evidence."""

from app.rag.grounding import unsupported_figures

EVIDENCE = [
    '{"passages": [{"text": "Parcelamento em até 48x. Receba em até 2 dias úteis. '
    'Taxa a partir de 3,15% no crédito. Antecipação mínima de R$ 50,00. Débito em D+1."}]}'
]


def test_supported_figures_pass() -> None:
    answer = "Até 48x, recebe em 2 dias úteis, taxa de 3,15%, mínimo de R$ 50,00 e débito D+1."
    assert unsupported_figures(answer, EVIDENCE) == []


def test_invented_fee_and_limit_are_flagged() -> None:
    answer = "A taxa é 2,99% e o parcelamento vai até 24x, com mínimo de R$ 1.000,00."
    assert unsupported_figures(answer, EVIDENCE) == ["2,99%", "24x", "R$ 1.000,00"]


def test_number_formats_are_normalized() -> None:
    evidence = ['{"amount_brl": 1234.56, "rate": "3.15"}']
    assert unsupported_figures("Total de R$ 1.234,56 e taxa de 3,15%.", evidence) == []


def test_dates_times_and_bare_numbers_are_ignored() -> None:
    assert unsupported_figures("Em 18/11 às 10:30, protocolo H-1234, item 7.", EVIDENCE) == []


def test_json_decimals_with_three_places_are_not_read_as_thousands() -> None:
    # Regression: PTAX 6.372 from the exchange-rate tool was read as 6372, so a correct
    # "R$ 6,3720" was flagged and the supervisor said the rate could not be confirmed.
    evidence = ['{"buy_brl": 6.3702, "sell_brl": 6.372}']
    assert unsupported_figures("Compra R$ 6,3702 e venda R$ 6,3720.", evidence) == []


def test_rounded_figures_are_supported_but_wrong_ones_are_not() -> None:
    evidence = ['{"sell_brl": 6.3702, "fee_pct": 3.15}']
    assert unsupported_figures("Cerca de R$ 6,37 e taxa de 3,2%.", evidence) == []
    assert unsupported_figures("Cerca de R$ 6,40 e taxa de 3%.", evidence) == ["R$ 6,40", "3%"]
