"""Snapshot of production signals from a running `make obs` stack, saved as evidence.

    uv run python -m evals.obs_snapshot --trace-id <trace_id from a /chat response>

Queries Prometheus (latency, cost, LLM/tool usage, guardrail, alerts) and fetches one trace
from Jaeger, writing evals/results/<ts>-observability/{report.md,trace.json}.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2 as httpx

ROOT = Path(__file__).resolve().parent
_TURN = "sum by (le) (rate(chat_turn_seconds_bucket[1h]))"
_LLM = "sum by (le, agent) (rate(llm_call_seconds_bucket[1h]))"
QUERIES = {
    "Chat turns by outcome": "sum by (outcome) (chat_turns_total)",
    "Chat latency p50 (s)": f"histogram_quantile(0.5, {_TURN})",
    "Chat latency p95 (s)": f"histogram_quantile(0.95, {_TURN})",
    "Average cost per turn (USD)": "sum(chat_turn_cost_usd_sum) / sum(chat_turn_cost_usd_count)",
    "LLM spend by agent (USD)": "sum by (agent) (llm_cost_usd_total)",
    "LLM calls by agent": "sum by (agent) (llm_calls_total)",
    "LLM latency p95 by agent (s)": f"histogram_quantile(0.95, {_LLM})",
    "Cache-read tokens by agent": 'sum by (agent) (llm_tokens_total{kind="cache_read"})',
    "Tool calls by tool and status": "sum by (tool, status) (tool_calls_total)",
    "Guardrail input decisions": 'sum by (decision) (guardrail_decisions_total{stage="input"})',
    "Feedback": "sum by (rating) (feedback_total)",
    "Budget used (fraction)": "llm_budget_spent_usd / llm_budget_limit_usd",
}


def fmt(result: list[dict[str, Any]]) -> str:
    parts = []
    for item in result:
        labels = ", ".join(f"{k}={v}" for k, v in item["metric"].items()) or "total"
        value = float(item["value"][1])
        parts.append(f"{labels}: {value:.4g}")
    return "<br>".join(parts) or "(no data)"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prometheus", default="http://127.0.0.1:9090")
    parser.add_argument("--jaeger", default="http://127.0.0.1:16686")
    parser.add_argument("--trace-id")
    args = parser.parse_args()
    client = httpx.Client(timeout=30)
    lines = [
        "# Observability snapshot",
        "",
        f"Taken {datetime.now(UTC):%Y-%m-%d %H:%M} UTC from the `make obs` stack after real "
        "traffic (the 10 challenge scenarios with 3 concurrent clients, 2 blocked attacks, "
        "1 feedback).",
        "",
        "| Signal | Value |",
        "|---|---|",
    ]
    for title, query in QUERIES.items():
        data = client.get(f"{args.prometheus}/api/v1/query", params={"query": query}).json()
        lines.append(f"| {title} | {fmt(data['data']['result'])} |")
    rules = client.get(f"{args.prometheus}/api/v1/rules").json()["data"]["groups"]
    alerts = [(r["name"], r["state"]) for g in rules for r in g["rules"]]
    lines += ["", "## Alert rules loaded", "", "| Alert | State |", "|---|---|"]
    lines += [f"| {name} | {state} |" for name, state in alerts]
    out = ROOT / "results" / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-observability"
    out.mkdir(parents=True, exist_ok=True)
    if args.trace_id:
        trace = client.get(f"{args.jaeger}/api/traces/{args.trace_id}").json()
        spans = trace["data"][0]["spans"] if trace.get("data") else []
        (out / "trace.json").write_text(json.dumps(trace, indent=1), "utf-8")
        lines += [
            "",
            f"## One trace ({args.trace_id})",
            "",
            "| Span | Duration (ms) |",
            "|---|---|",
        ]
        for span in sorted(spans, key=lambda s: s["startTime"]):
            lines.append(f"| {span['operationName']} | {span['duration'] / 1000:.0f} |")
    (out / "report.md").write_text("\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
