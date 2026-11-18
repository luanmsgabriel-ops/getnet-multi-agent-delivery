"""Run eval splits against the real system and write raw results plus a report.

    uv run python -m evals.run --split dev --repeats 3 --model claude-sonnet-5-5
    uv run python -m evals.run --split original --url http://127.0.0.1:8000 --token "$TOKEN"

In-process (default) the app uses the local .env with a real LLM and budget ledger, and
evaluation mode (`EXPOSE_TOOL_RESULTS`) so the judge can see tool outputs. Each case and
repeat gets its own session; multi-turn cases send their turns in order and are checked on
the last turn. Results: evals/results/<UTC timestamp>-<split>/{raw.jsonl,report.md}.
"""

import argparse
import json
import os
import statistics
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.checks import check

ROOT = Path(__file__).resolve().parent
Poster = Callable[[dict[str, Any]], Any]


def load_cases(split: str, ids: list[str] | None) -> list[dict[str, Any]]:
    path = ROOT / "datasets" / f"{split}.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    for c in cases:  # original.jsonl uses a single "message"
        c.setdefault("turns", [c["message"]] if "message" in c else [])
    return [c for c in cases if not ids or c["id"] in ids]


def _poster(url: str | None, token: str | None) -> Poster:
    if url:
        import httpx2 as httpx

        client = httpx.Client(base_url=url, timeout=300)
        return lambda body: client.post(
            "/chat", json=body, headers={"Authorization": f"Bearer {token}"}
        )
    os.environ["EXPOSE_TOOL_RESULTS"] = "1"
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app
    from app.security.auth import issue_token

    settings = get_settings()
    test_client = TestClient(create_app(settings))
    test_client.__enter__()
    tok = issue_token(settings, "cliente1988")[0]
    return lambda body: test_client.post(
        "/chat", json=body, headers={"Authorization": f"Bearer {tok}"}
    )


def run_case(post: Poster, case: dict[str, Any], repeat: int) -> dict[str, Any]:
    session = f"eval-{case['id']}-{repeat}-{uuid.uuid4().hex[:6]}"
    turns = []
    for message in case["turns"]:
        r = post({"message": message, "user_id": "cliente1988", "session_id": session})
        turns.append({"message": message, "http_status": r.status_code, "response": r.json()})
        if r.status_code != 200:
            break
    last = turns[-1]
    record = {
        "case_id": case["id"],
        "split": case.get("split"),
        "repeat": repeat,
        "http_status": last["http_status"],
        "turns": turns,
        "response": last["response"],
    }
    record["checks"] = (
        check(case, last["response"])
        if last["http_status"] == 200
        else {"passed": False, "error": last["response"].get("error")}
    )
    total = sum(t["response"].get("usage", {}).get("cost_usd", 0) for t in turns)
    record["cost_usd"] = round(total, 5)
    print(
        f"{case['id']} #{repeat}: {last['http_status']} "
        f"{'PASS' if record['checks']['passed'] else 'FAIL'}",
        flush=True,
    )
    return record


def run(args: argparse.Namespace) -> Path:
    if args.model:
        os.environ["LLM_MODEL"] = args.model
    cases = load_cases(args.split, args.ids)
    post = _poster(args.url, args.token)
    jobs = [(c, r) for c in cases for r in range(1, args.repeats + 1)]
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        records = list(pool.map(lambda j: run_case(post, *j), jobs))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    label = f"{args.split}-{args.model}" if args.model else args.split
    out = ROOT / "results" / f"{stamp}-{label}"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "raw.jsonl").open("w", encoding="utf-8") as f:
        for r in sorted(records, key=lambda r: (r["case_id"], r["repeat"])):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out / "report.md").write_text(report(label, cases, records), encoding="utf-8")
    print(f"\nwrote {out}")
    return out


def _pct(values: list[bool]) -> str:
    return f"{100 * sum(values) / max(1, len(values)):.0f}%"


def pass_k(records: list[dict[str, Any]]) -> str:
    by_case: dict[str, list[bool]] = {}
    for r in records:
        by_case.setdefault(r["case_id"], []).append(bool(r["checks"]["passed"]))
    return _pct([all(v) for v in by_case.values()])


def report(label: str, cases: list[dict[str, Any]], records: list[dict[str, Any]]) -> str:
    ok = [r for r in records if r["http_status"] == 200]
    lat = sorted(sum(t["response"].get("latency_ms", 0) for t in r["turns"]) for r in ok)
    cost = [r["cost_usd"] for r in ok]
    calls = [r["response"]["usage"]["llm_calls"] for r in ok]
    repeats = len(records) // max(1, len(cases))

    def rate(key: str) -> str:
        return _pct([r["checks"].get(key, False) for r in records])

    lines = [
        f"# Eval report: `{label}`",
        "",
        f"- Generated: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        f"- Runs: {len(records)} ({len(cases)} cases x {repeats} repeats). Deterministic checks "
        "on the last turn; LLM-judge scores are in `judge.md` when present.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| HTTP 200 | {_pct([r['http_status'] == 200 for r in records])} |",
        f"| Outcome as expected (answer / clarify / handoff / block) | {rate('outcome_ok')} |",
        f"| Routing (expected agents used) | {rate('routing_ok')} |",
        f"| Tools (expected tools called) | {rate('tools_ok')} |",
        f"| Content (required terms, no forbidden terms) | {rate('content_ok')} |",
        f"| All checks passed (per run) | {rate('passed')} |",
        f"| pass^{repeats} (case passes in every repeat) | {pass_k(records)} |",
    ]
    if ok:
        lines += [
            f"| Latency per case p50 / p95 | {statistics.median(lat) / 1000:.1f}s / "
            f"{lat[max(0, int(len(lat) * 0.95) - 1)] / 1000:.1f}s |",
            f"| LLM calls per turn (mean, last turn) | {statistics.mean(calls):.1f} |",
            f"| Cost per case (mean / total) | US$ {statistics.mean(cost):.4f} / "
            f"US$ {sum(cost):.4f} |",
        ]
    lines += [
        "",
        "## Per case",
        "",
        "| Case | Pass | Outcome | Agents | Tools | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for case in cases:
        runs = [r for r in records if r["case_id"] == case["id"]]
        passed = sum(r["checks"]["passed"] for r in runs)
        outcomes = sorted({str(r["checks"].get("outcome")) for r in runs})
        agents = sorted({", ".join(r["response"].get("agents_used", [])) for r in runs})
        tools = sorted(
            {
                ", ".join(sorted({t["tool"] for t in r["response"].get("tool_calls", [])}))
                for r in runs
            }
        )
        notes = sorted(
            {
                json.dumps(
                    r["checks"].get("missing") or r["checks"].get("error") or "", ensure_ascii=False
                )
                for r in runs
                if not r["checks"]["passed"]
            }
        )
        notes = [n for n in notes if n != '""']
        lines.append(
            f"| {case['id']} | {passed}/{len(runs)} | {' / '.join(outcomes)} | "
            f"{' / '.join(agents)} | {' / '.join(tools)} | {' '.join(notes)} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="original")
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--model", help="override LLM_MODEL for all agents (in-process only)")
    parser.add_argument("--url")
    parser.add_argument("--token")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
