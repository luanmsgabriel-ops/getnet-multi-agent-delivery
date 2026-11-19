"""Tool selection and argument accuracy of the Customer Support Agent, per tool (PRD 04).

    uv run python -m evals.tools [--repeats 1]

Each case in evals/datasets/tools.jsonl is one merchant request sent to the support agent with
the real model, on a fresh copy of the mock data. A case passes selection when the expected
tool is called and no forbidden tool is (for example, a simulation must not create a
proposal). It passes arguments when that call's arguments match: relative dates are written as
D-1, D0, D+30 (today in America/Sao_Paulo), and a list means any of those values.
Cost: one to three Claude Sonnet calls per case, charged to the project's spend ledger.
"""

import argparse
import json
import tempfile
import time
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

DATASET = Path(__file__).parent / "datasets" / "tools.jsonl"
RESULTS = Path(__file__).parent / "results"


def resolve(value: Any, today: date) -> Any:
    if isinstance(value, list):
        return [resolve(v, today) for v in value]
    if isinstance(value, str) and value.startswith("D") and value[1:].lstrip("+-").isdigit():
        return (today + timedelta(days=int(value[1:] or 0))).isoformat()
    if value == "D0":
        return today.isoformat()
    return value


def args_match(expected: dict[str, Any], actual: dict[str, Any], today: date) -> list[str]:
    """Names of the expected arguments that do not match."""
    wrong = []
    for name, want in expected.items():
        want = resolve(want, today)
        got = actual.get(name)
        if isinstance(got, str):
            got = got.strip()
        ok = got in want if isinstance(want, list) else got == want
        if not ok:
            wrong.append(f"{name}={got!r} (expected {want!r})")
    return wrong


def run_case(case: dict[str, Any], llm: Any, today_override: date | None = None) -> dict[str, Any]:
    from app.actions import ActionStore
    from app.agents.base import ToolContext
    from app.agents.support import run_support
    from app.config import get_settings
    from app.data.db import Database
    from app.data.seed import ensure_seed
    from app.hitl.store import HitlStore
    from app.security.auth import MERCHANT_SCOPES, Principal

    settings = get_settings()
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "mock.db")
        db.init()
        ensure_seed(db, settings.today(), settings.tz)
        principal = Principal("cliente1988", "demo", frozenset(MERCHANT_SCOPES), "eval-tools")
        ctx = ToolContext(
            principal=principal,
            db=db,
            now=settings.now(),
            llm=llm,
            session_id="eval-tools",
            language="pt",
            services={
                "hitl": HitlStore(db),
                "actions": ActionStore(db, db),
                "request_id": f"eval-{case['id']}",
                "support_model": settings.support_model,
                "notify": lambda *a, **k: None,
            },
        )
        started = time.monotonic()
        run = run_support(ctx, case["request"])
        latency = time.monotonic() - started
    today = today_override or settings.today()
    calls = [(e.tool, e.arguments) for e in ctx.trace if e.agent == "support"]
    expect = case["expect"]
    names = [name for name, _ in calls]
    forbidden = [f for f in expect.get("forbid", []) if f in names]
    selected = expect["tool"] in names and not forbidden
    match = next((a for n, a in calls if n == expect["tool"]), None)
    wrong = args_match(expect["args"], match, today) if match is not None else ["not called"]
    return {
        "case_id": case["id"],
        "request": case["request"],
        "expected_tool": expect["tool"],
        "calls": [{"tool": n, "arguments": a} for n, a in calls],
        "selected": selected,
        "forbidden_called": forbidden,
        "args_ok": selected and not wrong,
        "wrong_args": wrong,
        "answer": str(getattr(run, "text", ""))[:400],
        "latency_s": round(latency, 2),
    }


def main() -> None:
    from app.config import get_settings
    from app.data.db import Database
    from app.llm.client import AnthropicLLM, Ledger, UsageTracker, current_usage

    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=1)
    opts = parser.parse_args()

    settings = get_settings()
    assert settings.anthropic_api_key is not None, "ANTHROPIC_API_KEY is required"
    ledger_db = Database(settings.state_database_url or settings.db_path)
    ledger_db.init_state()
    llm = AnthropicLLM(
        settings.anthropic_api_key.get_secret_value(),
        Ledger(ledger_db, settings.llm_budget_usd),
        model=settings.llm_model,
    )
    cases = [json.loads(x) for x in DATASET.read_text("utf-8").splitlines() if x.strip()]
    out = RESULTS / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-tools"
    out.mkdir(parents=True)
    tracker = UsageTracker(max_cost_usd=50.0)
    token = current_usage.set(tracker)
    rows = []
    try:
        for repeat in range(opts.repeats):
            for case in cases:
                row = {**run_case(case, llm), "repeat": repeat}
                rows.append(row)
                mark = "ok" if row["args_ok"] else ("sel" if row["selected"] else "MISS")
                print(f"{case['id']} r{repeat} {mark:4s} {[c['tool'] for c in row['calls']]}")
    finally:
        current_usage.reset(token)
    with (out / "raw.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    per_tool: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "selected": 0, "args": 0})
    for row in rows:
        t = per_tool[row["expected_tool"]]
        t["n"] += 1
        t["selected"] += row["selected"]
        t["args"] += row["args_ok"]
    n = len(rows)
    summary = {
        "model": settings.llm_model,
        "cases": len(cases),
        "repeats": opts.repeats,
        "selection": round(sum(r["selected"] for r in rows) / n, 3),
        "arguments": round(sum(r["args_ok"] for r in rows) / n, 3),
        "per_tool": {
            k: {
                "n": v["n"],
                "selection": round(v["selected"] / v["n"], 3),
                "arguments": round(v["args"] / v["n"], 3),
            }
            for k, v in sorted(per_tool.items())
        },
        "cost_usd": round(tracker.cost_usd, 4),
        "date": settings.today().isoformat(),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), "utf-8")
    lines = [
        f"# Tool accuracy ({summary['date']}, {settings.llm_model}, {n} runs)",
        "",
        f"Selection **{summary['selection']:.0%}** · arguments **{summary['arguments']:.0%}** · "
        f"cost US$ {summary['cost_usd']}",
        "",
        "| Tool | Cases | Selection | Arguments |",
        "|---|---:|---:|---:|",
        *(
            f"| `{k}` | {v['n']} | {v['selection']:.0%} | {v['arguments']:.0%} |"
            for k, v in summary["per_tool"].items()
        ),
        "",
        "## Misses",
        "",
        *(
            f"- {r['case_id']} ({r['expected_tool']}): calls {[c['tool'] for c in r['calls']]}"
            f"{'; forbidden ' + str(r['forbidden_called']) if r['forbidden_called'] else ''}"
            f"{'; ' + '; '.join(r['wrong_args']) if r['selected'] and r['wrong_args'] else ''}"
            for r in rows
            if not r["args_ok"]
        ),
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines))
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
