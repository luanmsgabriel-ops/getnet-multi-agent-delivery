"""Confidence intervals used in the eval reports."""

import math

from evals.stats import bootstrap, mean, percentile, wilson


def test_wilson_matches_known_values() -> None:
    lo, hi = wilson(30, 30)  # all passed: the interval still has a lower bound below 100%
    assert hi == 1.0 and 0.88 < lo < 0.89
    lo, hi = wilson(5, 10)
    assert round(lo, 3) == 0.237 and round(hi, 3) == 0.763
    assert all(math.isnan(x) for x in wilson(0, 0))


def test_bootstrap_brackets_the_estimate() -> None:
    values = [4.0, 5.0, 5.0, 3.0, 5.0, 4.0, 5.0, 5.0, 2.0, 5.0]
    lo, hi = bootstrap(values, mean)
    assert lo <= mean(values) <= hi
    assert bootstrap(values, mean) == (lo, hi)  # fixed seed: reproducible


def test_percentile_is_nearest_rank() -> None:
    assert percentile(list(range(1, 101)), 0.95) == 95
    assert math.isnan(percentile([], 0.5))


def test_content_check_ignores_unicode_hyphens_and_spaces() -> None:
    from evals.checks import check

    case = {"expected": {"must_include": [["Wi-Fi", "wifi"]], "must_not_include": ["R$ 10"]}}
    ok = check(case, {"answer": "Toque em Wi" + chr(0x2011) + "Fi.", "outcome": "answered"})
    assert ok["content_ok"]
    bad = check(case, {"answer": "Wi-Fi custa R$" + chr(0xA0) + "10", "outcome": "answered"})
    assert bad["forbidden"] == ["R$ 10"]
