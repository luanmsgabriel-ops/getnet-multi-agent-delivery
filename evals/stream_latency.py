"""Latency as the merchant feels it, through POST /chat/stream (in-process, real model).

    uv run python -m evals.stream_latency --split original

For each case: time to the first event, to the first specialist status (real work started),
to the first answer text, and to the end. Writes evals/results/<ts>-stream-<split>/report.md.
"""

import argparse
import json
import os
import statistics
from datetime import UTC, datetime
from typing import Any

from evals.run import ROOT, load_cases

WORK_STEPS = {"knowledge", "support", "escalation"}


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, round(q * (len(s) - 1)))] if s else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="original")
    args = parser.parse_args()
    os.environ["EXPOSE_TOOL_RESULTS"] = "1"
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app
    from app.security.auth import issue_token

    settings = get_settings()
    rows: list[dict[str, Any]] = []
    with TestClient(create_app(settings)) as c:
        tok = issue_token(settings, "cliente1988")[0]
        for case in load_cases(args.split, None):
            if len(case["turns"]) != 1:
                continue
            body = {"message": case["turns"][0], "user_id": "cliente1988"}
            with c.stream(
                "POST", "/chat/stream", json=body, headers={"Authorization": f"Bearer {tok}"}
            ) as r:
                raw = "".join(r.iter_text())
            events = []
            for block in raw.strip().split("\n\n"):
                lines = dict(ln.split(": ", 1) for ln in block.splitlines() if ": " in ln)
                events.append((lines["event"], json.loads(lines["data"])))
            first = events[0][1]["elapsed_ms"]
            work = next(
                (d["elapsed_ms"] for k, d in events if k == "status" and d["step"] in WORK_STEPS),
                None,
            )
            text = next((d["elapsed_ms"] for k, d in events if k == "delta"), None)
            final = events[-1][1]
            rows.append(
                {
                    "case": case["id"],
                    "first_event_ms": first,
                    "first_work_status_ms": work,
                    "first_text_ms": text,
                    "total_ms": final["elapsed_ms"],
                    "outcome": final.get("outcome"),
                    "steps": [d["step"] for k, d in events if k == "status"],
                }
            )
            print(case["id"], rows[-1]["first_work_status_ms"], rows[-1]["total_ms"], flush=True)

    def col(key: str) -> list[float]:
        return [float(r[key]) / 1000 for r in rows if r[key] is not None]

    lines = [
        f"# Stream latency: `{args.split}` ({len(rows)} cases, "
        f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC)",
        "",
        "| Moment | p50 (s) | p95 (s) | mean (s) |",
        "|---|---:|---:|---:|",
    ]
    for key, label in (
        ("first_event_ms", "first event (analyzing)"),
        ("first_work_status_ms", "first specialist status"),
        ("first_text_ms", "first answer text"),
        ("total_ms", "end of turn"),
    ):
        v = col(key)
        if v:
            lines.append(
                f"| {label} | {pct(v, 0.5):.1f} | {pct(v, 0.95):.1f} | {statistics.mean(v):.1f} |"
            )
    lines += [
        "",
        "| Case | First status (s) | First work (s) | Total (s) | Steps |",
        "|---|---:|---:|---:|---|",
    ]
    for r in rows:
        work = f"{r['first_work_status_ms'] / 1000:.1f}" if r["first_work_status_ms"] else "-"
        lines.append(
            f"| {r['case']} | {r['first_event_ms'] / 1000:.2f} | {work} | "
            f"{r['total_ms'] / 1000:.1f} | {', '.join(r['steps'])} |"
        )
    report = "\n".join(lines) + "\n"
    out = ROOT / "results" / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-stream-{args.split}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(report, encoding="utf-8")
    (out / "raw.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
