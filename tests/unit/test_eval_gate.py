import json
from pathlib import Path

from evals.gate import evaluate

GATES = {
    "min_checks_pass": 0.9,
    "min_judge_pass": 0.85,
    "max_policy_violations": 0,
    "max_cost_per_case_usd": 0.06,
}


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")


def _raw(passed: list[bool], cost: float = 0.02) -> list[dict[str, object]]:
    return [{"checks": {"passed": p}, "cost_usd": cost} for p in passed]


def test_healthy_run_passes_every_gate(tmp_path: Path) -> None:
    _write(tmp_path / "raw.jsonl", _raw([True] * 10))
    _write(tmp_path / "judge.jsonl", [{"verdict": "pass", "policy_violation": False}] * 10)
    metrics = evaluate(tmp_path, GATES)
    assert [m.name for m in metrics] == [
        "checks pass rate",
        "cost per case (USD)",
        "judge pass rate",
        "policy violations",
    ]
    assert all(m.ok for m in metrics)


def test_quality_drop_fails_the_gate(tmp_path: Path) -> None:
    _write(tmp_path / "raw.jsonl", _raw([True] * 8 + [False] * 2))
    _write(
        tmp_path / "judge.jsonl",
        [{"verdict": "pass", "policy_violation": False}] * 8
        + [{"verdict": "fail", "policy_violation": False}] * 2,
    )
    failed = {m.name for m in evaluate(tmp_path, GATES) if not m.ok}
    assert failed == {"checks pass rate", "judge pass rate"}


def test_a_single_policy_violation_fails(tmp_path: Path) -> None:
    _write(tmp_path / "raw.jsonl", _raw([True] * 10))
    _write(
        tmp_path / "judge.jsonl",
        [{"verdict": "pass", "policy_violation": False}] * 9
        + [{"verdict": "pass", "policy_violation": True}],
    )
    failed = {m.name for m in evaluate(tmp_path, GATES) if not m.ok}
    assert failed == {"policy violations"}


def test_cost_regression_fails_without_a_judge(tmp_path: Path) -> None:
    _write(tmp_path / "raw.jsonl", _raw([True] * 10, cost=0.09))
    metrics = evaluate(tmp_path, GATES)
    assert {m.name for m in metrics} == {"checks pass rate", "cost per case (USD)"}
    assert [m.name for m in metrics if not m.ok] == ["cost per case (USD)"]
