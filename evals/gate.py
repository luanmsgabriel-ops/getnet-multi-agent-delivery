"""Regression gate for a real-model eval run.

    uv run python -m evals.gate evals/results/<run dir> --split original

Reads raw.jsonl (deterministic checks, cost) and judge.jsonl (when the judge ran) and fails
with exit code 1 if any metric crosses its threshold in evals/gates.json. The thresholds sit
below the committed results (docs/EVALUATION.md) by more than the measured judge noise
(3-10 points), so a failure means a real regression, not a re-roll.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GATES = Path(__file__).resolve().parent / "gates.json"


@dataclass(frozen=True)
class Metric:
    name: str
    value: float
    limit: float
    higher_is_better: bool

    @property
    def ok(self) -> bool:
        return self.value >= self.limit if self.higher_is_better else self.value <= self.limit


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def evaluate(run_dir: Path, gates: dict[str, float]) -> list[Metric]:
    raw = _rows(run_dir / "raw.jsonl")
    if not raw:
        raise ValueError(f"no records in {run_dir / 'raw.jsonl'}")
    metrics = [
        Metric(
            "checks pass rate",
            sum(bool(r["checks"]["passed"]) for r in raw) / len(raw),
            gates["min_checks_pass"],
            True,
        ),
        Metric(
            "cost per case (USD)",
            sum(r.get("cost_usd", 0.0) for r in raw) / len(raw),
            gates["max_cost_per_case_usd"],
            False,
        ),
    ]
    judged = _rows(run_dir / "judge.jsonl")
    if judged:
        metrics += [
            Metric(
                "judge pass rate",
                sum(g.get("verdict") == "pass" for g in judged) / len(judged),
                gates["min_judge_pass"],
                True,
            ),
            Metric(
                "policy violations",
                sum(bool(g.get("policy_violation")) for g in judged),
                gates["max_policy_violations"],
                False,
            ),
        ]
    return metrics


def render(split: str, run_dir: Path, metrics: list[Metric]) -> str:
    lines = [
        f"### Eval gate: `{split}` ({run_dir.name})",
        "",
        "| Metric | Value | Limit | |",
        "|---|---:|---:|---|",
    ]
    for m in metrics:
        sign = ">=" if m.higher_is_better else "<="
        status = "ok" if m.ok else "FAIL"
        lines.append(f"| {m.name} | {m.value:.3f} | {sign} {m.limit} | {status} |")
    if not any(m.name == "judge pass rate" for m in metrics):
        lines += ["", "Judge not run: only deterministic checks and cost were gated."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--split", required=True)
    args = parser.parse_args()
    gates = json.loads(GATES.read_text("utf-8"))
    if args.split not in gates:
        sys.exit(f"no gate defined for split {args.split!r} in {GATES}")
    metrics = evaluate(args.run_dir, gates[args.split])
    report = render(args.split, args.run_dir, metrics)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report)
    sys.exit(0 if all(m.ok for m in metrics) else 1)


if __name__ == "__main__":
    main()
