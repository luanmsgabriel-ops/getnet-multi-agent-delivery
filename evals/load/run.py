"""`make load`: 10 concurrent merchants against the running compose stack, then a report.

    docker compose up -d            # or `make obs` for Grafana/Jaeger under load
    uv run python -m evals.load.run --users 10 --minutes 5

Issues one OIDC token per mock merchant through the API container, records the spend ledger
before and after (Postgres), runs Locust headless, and writes evals/results/<ts>-load-<users>/
with report.md (p50/p95/p99 per kind, first-event latency, errors, throughput, cost per turn,
SLO check), turns.jsonl (one row per turn) and Locust's CSV files.
"""

import argparse
import json
import math
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MERCHANTS = ("cliente1988", "cliente2000", "cliente3000")
# docs/SLO.md
SLO = {"availability": 0.995, "turn_p95_s": 30.0, "first_work_p95_s": 5.0, "cost_per_turn": 0.05}


def compose(*args: str) -> str:
    # Fixed argv (no shell); arguments come from this script, not from input.
    out = subprocess.run(  # noqa: S603
        ["docker", "compose", *args],  # noqa: S607
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def spent() -> float:
    value = compose(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "getnet",
        "-d",
        "getnet",
        "-tAc",
        "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_ledger",
    )
    return float(value or 0)


def pct(values: list[float], q: float) -> float:
    """Nearest-rank percentile."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--minutes", type=float, default=5)
    parser.add_argument("--host", default="http://127.0.0.1:8000")
    parser.add_argument("--label", default="", help="suffix for the results folder")
    parser.add_argument("--report", type=Path, help="rebuild report.md of an earlier run (no load)")
    opts = parser.parse_args()
    if opts.report:
        old = json.loads((opts.report / "summary.json").read_text("utf-8"))
        stamp = datetime.strptime(opts.report.name[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        report(opts.report, old["users"], stamp, old["minutes"], old["cost_usd"])
        return

    tokens = [
        compose("exec", "-T", "api", "python", "-m", "app.security.tokens", "issue", "--sub", m)
        for m in MERCHANTS
    ]
    suffix = f"-{opts.label}" if opts.label else ""
    name = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-load-{opts.users}{suffix}"
    out = ROOT / "evals" / "results" / name
    out.mkdir(parents=True)
    turns_file = out / "turns.jsonl"
    before = spent()
    started = datetime.now(UTC)
    env = {**os.environ, "LOAD_TOKENS": ",".join(tokens), "LOAD_TURNS_FILE": str(turns_file)}
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "locust",
            "-f",
            str(ROOT / "evals" / "load" / "locustfile.py"),
            "--headless",
            "-u",
            str(opts.users),
            "-r",
            "2",
            "-t",
            f"{int(opts.minutes * 60)}s",
            "--host",
            opts.host,
            "--csv",
            str(out / "locust"),
            "--only-summary",
            "--stop-timeout",
            "180",
        ],
        cwd=ROOT,
        env=env,
        check=False,
    )
    finished = datetime.now(UTC)
    report(out, opts.users, started, (finished - started).total_seconds() / 60, spent() - before)


def report(out: Path, users: int, started: datetime, minutes: float, cost: float) -> None:
    turns_file = out / "turns.jsonl"
    rows = [json.loads(x) for x in turns_file.read_text("utf-8").splitlines() if x]
    ok = [r for r in rows if not r["error"]]
    totals = [r["total_ms"] / 1000 for r in ok]
    firsts = [r["first_event_ms"] / 1000 for r in rows if r["first_event_ms"] is not None]
    works = [r["first_work_ms"] / 1000 for r in rows if r.get("first_work_ms") is not None]
    availability = len(ok) / len(rows) if rows else 0.0
    per_turn = cost / len(rows) if rows else float("nan")
    summary: dict[str, Any] = {
        "users": users,
        "minutes": round(minutes, 1),
        "turns": len(rows),
        "errors": Counter(str(r["error"]) for r in rows if r["error"]),
        "availability": round(availability, 4),
        "turn_p50_s": round(pct(totals, 0.5), 1),
        "turn_p95_s": round(pct(totals, 0.95), 1),
        "turn_p99_s": round(pct(totals, 0.99), 1),
        "first_event_p50_s": round(pct(firsts, 0.5), 2),
        "first_event_p95_s": round(pct(firsts, 0.95), 2),
        "first_work_p50_s": round(pct(works, 0.5), 2),
        "first_work_p95_s": round(pct(works, 0.95), 2),
        "throughput_turns_per_min": round(len(rows) / minutes, 1) if minutes else None,
        "cost_usd": round(cost, 4),
        "cost_per_turn_usd": round(per_turn, 4),
        "outcomes": Counter(str(r["outcome"]) for r in rows),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), "utf-8")

    by_kind: dict[str, list[float]] = defaultdict(list)
    for r in ok:
        by_kind[r["kind"]].append(r["total_ms"] / 1000)
    checks = [
        (
            "Availability (turns without error)",
            f"{availability:.1%}",
            f"≥ {SLO['availability']:.1%}",
            availability >= SLO["availability"],
        ),
        (
            "Turn p95",
            f"{summary['turn_p95_s']} s",
            f"< {SLO['turn_p95_s']:.0f} s",
            summary["turn_p95_s"] < SLO["turn_p95_s"],
        ),
        (
            "First specialist at work p95",
            f"{summary['first_work_p95_s']} s",
            f"< {SLO['first_work_p95_s']:.0f} s",
            summary["first_work_p95_s"] < SLO["first_work_p95_s"],
        ),
        (
            "Cost per turn",
            f"US$ {per_turn:.4f}",
            f"< US$ {SLO['cost_per_turn']:.2f}",
            per_turn < SLO["cost_per_turn"],
        ),
    ]
    lines = [
        f"# Load test: {users} concurrent merchants, {summary['minutes']} min",
        "",
        f"{started:%Y-%m-%d %H:%M} UTC, full docker compose stack (Postgres, Redis, OIDC), real "
        "model. Each user runs conversations from the 10 challenge scenarios and the 40 dev cases "
        "over `/chat/stream`, with 5 s between turns, spread over 3 merchants.",
        "",
        "| SLO (docs/SLO.md) | Measured | Target | Met |",
        "|---|---|---|---|",
        *(f"| {a} | {b} | {c} | {'yes' if d else '**no**'} |" for a, b, c, d in checks),
        "",
        f"Turns {len(rows)} · throughput {summary['throughput_turns_per_min']}/min · "
        f"p50 {summary['turn_p50_s']} s · p95 {summary['turn_p95_s']} s · p99 "
        f"{summary['turn_p99_s']} s · first event p50 {summary['first_event_p50_s']} s · "
        f"first specialist at work p50 {summary['first_work_p50_s']} s / p95 "
        f"{summary['first_work_p95_s']} s · "
        f"cost US$ {cost:.3f} · errors {dict(summary['errors']) or 'none'}",
        "",
        "| Kind | Turns | p50 (s) | p95 (s) |",
        "|---|---:|---:|---:|",
        *(
            f"| {k} | {len(v)} | {pct(v, 0.5):.1f} | {pct(v, 0.95):.1f} |"
            for k, v in sorted(by_kind.items(), key=lambda kv: -len(kv[1]))
        ),
        "",
        f"Outcomes: {dict(summary['outcomes'])}",
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines))
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
