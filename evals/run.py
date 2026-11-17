"""Run an eval split against the real system and write raw results plus a report.

    uv run python -m evals.run --split original --repeats 3
    uv run python -m evals.run --split original --url http://127.0.0.1:8000 --token "$TOKEN"

Without --url the app runs in-process with the local .env (real LLM, real budget ledger).
Results go to evals/results/<UTC timestamp>-<split>/{raw.jsonl,report.md}.
"""

import argparse
import json
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.checks import check

ROOT = Path(__file__).resolve().parent


def load_cases(split: str, ids: list[str] | None) -> list[dict[str, Any]]:
    path = ROOT / "datasets" / f"{split}.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [c for c in cases if not ids or c["id"] in ids]


def _poster(url: str | None, token: str | None) -> Any:
    if url:
        import httpx2 as httpx

        client = httpx.Client(base_url=url, timeout=180)
        return lambda body: client.post(
            "/chat", json=body, headers={"Authorization": f"Bearer {token}"}
        )
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app
    from app.security.auth import issue_token

    settings = get_settings()
    test_client = TestClient(create_app(settings))
    test_client.__enter__()
    tokens = {"cliente1988": issue_token(settings, "cliente1988")[0]}
    return lambda body: test_client.post(
        "/chat", json=body, headers={"Authorization": f"Bearer {tokens[body['user_id']]}"}
    )


def run(args: argparse.Namespace) -> Path:
    cases = load_cases(args.split, args.ids)
    post = _poster(args.url, args.token)
    jobs = [(c, r) for c in cases for r in range(1, args.repeats + 1)]

    def one(job: tuple[dict[str, Any], int]) -> dict[str, Any]:
        case, rep = job
        response = post({"message": case["message"], "user_id": case.get("user_id", "cliente1988")})
        body = response.json()
        record = {
            "case_id": case["id"],
            "repeat": rep,
            "http_status": response.status_code,
            "message": case["message"],
            "response": body,
        }
        record["checks"] = (
            check(case, body)
            if response.status_code == 200
            else {"passed": False, "error": body.get("error")}
        )
        print(
            f"{case['id']} #{rep}: {response.status_code} "
            f"{'PASS' if record['checks']['passed'] else 'FAIL'}",
            flush=True,
        )
        return record

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        records = list(pool.map(one, jobs))

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "results" / f"{stamp}-{args.split}"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "raw.jsonl").open("w", encoding="utf-8") as f:
        for r in sorted(records, key=lambda r: (r["case_id"], r["repeat"])):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out / "report.md").write_text(report(args.split, cases, records), encoding="utf-8")
    print(f"\nwrote {out}")
    return out


def _pct(values: list[bool]) -> str:
    return f"{100 * sum(values) / max(1, len(values)):.0f}%"


def report(split: str, cases: list[dict[str, Any]], records: list[dict[str, Any]]) -> str:
    ok = [r for r in records if r["http_status"] == 200]
    lat = sorted(r["response"]["latency_ms"] for r in ok)
    cost = [r["response"]["usage"]["cost_usd"] for r in ok]
    calls = [r["response"]["usage"]["llm_calls"] for r in ok]
    lines = [
        f"# Eval report: `{split}`",
        "",
        f"- Generated: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        f"- Runs: {len(records)} ({len(cases)} cases x {len(records) // max(1, len(cases))} "
        "repeats); deterministic checks only (no LLM judge in this report)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| HTTP 200 | {_pct([r['http_status'] == 200 for r in records])} |",
        f"| Routing (expected agents used) | {_pct([r['checks'].get('routing_ok', False) for r in records])} |",  # noqa: E501
        f"| Tools (expected tools called) | {_pct([r['checks'].get('tools_ok', False) for r in records])} |",  # noqa: E501
        f"| Content (must-include terms) | {_pct([r['checks'].get('content_ok', False) for r in records])} |",  # noqa: E501
        f"| All checks passed | {_pct([r['checks']['passed'] for r in records])} |",
    ]
    if ok:
        lines += [
            f"| Latency p50 / p95 | {statistics.median(lat) / 1000:.1f}s / "
            f"{lat[max(0, int(len(lat) * 0.95) - 1)] / 1000:.1f}s |",
            f"| LLM calls per chat (mean) | {statistics.mean(calls):.1f} |",
            f"| Cost per chat (mean / total) | US$ {statistics.mean(cost):.4f} / "
            f"US$ {sum(cost):.4f} |",
        ]
    lines += [
        "",
        "## Per case",
        "",
        "| Case | Pass (runs) | Agents | Tools | Notes |",
        "|---|---|---|---|---|",
    ]
    for case in cases:
        runs = [r for r in records if r["case_id"] == case["id"]]
        passed = sum(r["checks"]["passed"] for r in runs)
        agents = {
            ", ".join(r["response"].get("agents_used", [])) for r in runs if r["http_status"] == 200
        }
        tools = {
            ", ".join(sorted({t["tool"] for t in r["response"].get("tool_calls", [])}))
            for r in runs
            if r["http_status"] == 200
        }
        notes = sorted(
            {
                json.dumps(
                    r["checks"].get("missing") or r["checks"].get("error") or "", ensure_ascii=False
                )
                for r in runs
                if not r["checks"]["passed"]
            }
        )
        lines.append(
            f"| {case['id']} | {passed}/{len(runs)} | {' / '.join(sorted(agents))} | "
            f"{' / '.join(sorted(tools))} | {' '.join(n for n in notes if n != '""')} |"
        )
    lines += ["", "## Answers (first repeat)", ""]
    for case in cases:
        first = next(r for r in records if r["case_id"] == case["id"])
        lines += [
            f"### {case['id']}: {case['message']}",
            "",
            first["response"].get("answer") or json.dumps(first["response"]),
            "",
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="original")
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--url")
    parser.add_argument("--token")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
