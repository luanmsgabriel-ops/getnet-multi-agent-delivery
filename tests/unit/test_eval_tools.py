"""The tool-accuracy eval's argument matcher (relative dates, alternatives, nulls)."""

import json
from datetime import date
from pathlib import Path

from evals.tools import DATASET, args_match, resolve

TODAY = date(2026, 11, 19)


def test_relative_dates_resolve() -> None:
    assert resolve("D0", TODAY) == "2026-11-19"
    assert resolve("D-1", TODAY) == "2026-11-18"
    assert resolve("D+30", TODAY) == "2026-12-19"
    assert resolve(["D+1", "x"], TODAY) == ["2026-11-20", "x"]
    assert resolve("Dinheiro", TODAY) == "Dinheiro"


def test_args_match_reports_only_wrong_arguments() -> None:
    expected = {"by": "sale_date", "date_from": "D-1", "terminal_id": None, "topic": ["a", "b"]}
    actual = {"by": "sale_date", "date_from": "2026-11-18", "terminal_id": None, "topic": "b"}
    assert args_match(expected, actual, TODAY) == []
    wrong = args_match(expected, {**actual, "by": "payment_date"}, TODAY)
    assert len(wrong) == 1 and wrong[0].startswith("by=")


def test_dataset_covers_every_support_tool() -> None:
    from app.agents.support import TOOLS

    cases = [json.loads(x) for x in Path(DATASET).read_text("utf-8").splitlines() if x.strip()]
    covered = {c["expect"]["tool"] for c in cases}
    assert covered == {t.name for t in TOOLS}
    assert len({c["id"] for c in cases}) == len(cases) == 40
