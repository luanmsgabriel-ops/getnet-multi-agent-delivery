"""95% confidence intervals for eval runs (Wilson for rates, bootstrap for means and p95).

    uv run python -m evals.stats evals/results/<run> [<run> ...] [--out table.md]

For each run folder (raw.jsonl from evals.run, judge.jsonl from evals.judge when present):
deterministic checks pass rate, judge pass rate, mean correctness and groundedness, latency
p50/p95 and cost per run, each with a 95% interval. Small sets give wide intervals; the point
is to show them, not to hide them.
"""

import argparse
import json
import math
import random
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

Z = 1.96
RESAMPLES = 2000


def wilson(k: int, n: int, z: float = Z) -> tuple[float, float]:
    """Wilson score interval for a proportion k/n."""
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def bootstrap(
    values: Sequence[float],
    stat: Callable[[Sequence[float]], float],
    resamples: int = RESAMPLES,
    seed: int = 7,
) -> tuple[float, float]:
    """Percentile bootstrap interval for any statistic."""
    if not values:
        return (math.nan, math.nan)
    rng = random.Random(seed)
    n = len(values)
    stats = sorted(stat([values[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples))
    return (stats[int(0.025 * resamples)], stats[int(0.975 * resamples) - 1])


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else math.nan


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def summarize(run: Path) -> dict[str, Any]:
    raw = _load(run / "raw.jsonl")
    judged = _load(run / "judge.jsonl")
    passed = sum(bool(r.get("checks", {}).get("passed")) for r in raw)
    latency = [
        float(r["response"]["latency_ms"]) / 1000
        for r in raw
        if isinstance(r.get("response"), dict) and r["response"].get("latency_ms") is not None
    ]
    cost = [float(r.get("cost_usd") or 0) for r in raw]
    verdicts = [g for g in judged if g.get("verdict") in ("pass", "fail")]
    judge_pass = sum(g["verdict"] == "pass" for g in verdicts)
    correctness = [float(g["correctness"]) for g in judged if g.get("correctness") is not None]
    grounded = [float(g["groundedness"]) for g in judged if g.get("groundedness") is not None]
    return {
        "run": run.name,
        "n": len(raw),
        "checks": (passed, len(raw), wilson(passed, len(raw))),
        "judge_pass": (judge_pass, len(verdicts), wilson(judge_pass, len(verdicts))),
        "correctness": (mean(correctness), bootstrap(correctness, mean)),
        "groundedness": (mean(grounded), bootstrap(grounded, mean)),
        "unsupported": sum(len(g.get("unsupported_claims") or []) for g in judged),
        "latency_p50": (percentile(latency, 0.5), bootstrap(latency, lambda v: percentile(v, 0.5))),
        "latency_p95": (
            percentile(latency, 0.95),
            bootstrap(latency, lambda v: percentile(v, 0.95)),
        ),
        "cost": (mean(cost), bootstrap(cost, mean)),
    }


def _rate(cell: tuple[int, int, tuple[float, float]]) -> str:
    k, n, (lo, hi) = cell
    if not n:
        return "n/a"
    return f"{100 * k / n:.0f}% [{100 * lo:.0f}-{100 * hi:.0f}]"


def _num(cell: tuple[float, tuple[float, float]], fmt: str = "{:.2f}") -> str:
    value, (lo, hi) = cell
    if math.isnan(value):
        return "n/a"
    return f"{fmt.format(value)} [{fmt.format(lo)}-{fmt.format(hi)}]"


def table(runs: list[Path]) -> str:
    lines = [
        "| Run | n | Checks pass | Judge pass | Correctness | Groundedness | Unsupported | "
        "Latency p50 (s) | Latency p95 (s) | Cost/run (US$) |",
        "|---|---:|---|---|---|---|---:|---|---|---|",
    ]
    for run in runs:
        s = summarize(run)
        lines.append(
            f"| `{s['run']}` | {s['n']} | {_rate(s['checks'])} | {_rate(s['judge_pass'])} | "
            f"{_num(s['correctness'])} | {_num(s['groundedness'])} | {s['unsupported']} | "
            f"{_num(s['latency_p50'], '{:.1f}')} | {_num(s['latency_p95'], '{:.1f}')} | "
            f"{_num(s['cost'], '{:.3f}')} |"
        )
    lines += [
        "",
        "Brackets: 95% intervals (Wilson for rates; bootstrap, 2,000 resamples, for means and "
        "percentiles).",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path)
    opts = parser.parse_args()
    text = table(opts.runs)
    if opts.out:
        opts.out.write_text(text + "\n", "utf-8")
    print(text)


if __name__ == "__main__":
    main()
