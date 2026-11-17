"""Judge calibration against human labels.

uv run python -m evals.calibration export <run dir> [<run dir> ...] --n 30
    -> evals/calibration/labels.csv (fill human_verdict = pass/fail, human_correctness 1-5)
uv run python -m evals.calibration score
    -> evals/calibration/calibration.md (agreement and Cohen's kappa vs the LLM judge)
"""

import argparse
import csv
import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent / "calibration"
FIELDS = [
    "run_dir",
    "case_id",
    "repeat",
    "question",
    "answer",
    "evidence",
    "human_verdict",
    "human_correctness",
]


def export(run_dirs: list[Path], n: int, seed: int = 7) -> None:
    rows = []
    for d in run_dirs:
        for line in (d / "raw.jsonl").read_text("utf-8").splitlines():
            r = json.loads(line)
            if r["http_status"] != 200:
                continue
            evidence = [
                f"{c['tool']}: {c.get('result', '')[:600]}"
                for t in r["turns"]
                for c in t["response"].get("tool_calls", [])
                if not c["tool"].startswith("ask_")
            ]
            rows.append(
                {
                    "run_dir": d.name,
                    "case_id": r["case_id"],
                    "repeat": r["repeat"],
                    "question": " || ".join(t["message"] for t in r["turns"]),
                    "answer": r["response"].get("answer", ""),
                    "evidence": "\n".join(evidence)[:3000],
                    "human_verdict": "",
                    "human_correctness": "",
                }
            )
    random.Random(seed).shuffle(rows)
    ROOT.mkdir(exist_ok=True)
    with (ROOT / "labels.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows[:n])
    print(f"wrote {ROOT / 'labels.csv'} with {min(n, len(rows))} rows to label")


def kappa(a: list[str], b: list[str]) -> float:
    labels = sorted(set(a) | set(b))
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    expected = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in labels)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def score() -> None:
    labels = list(csv.DictReader((ROOT / "labels.csv").open(encoding="utf-8-sig")))
    labels = [row for row in labels if row["human_verdict"].strip()]
    results = Path(__file__).resolve().parent / "results"
    judged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in labels:
        path = results / row["run_dir"] / "judge.jsonl"
        for line in path.read_text("utf-8").splitlines():
            g = json.loads(line)
            judged[(row["run_dir"], g["case_id"], str(g["repeat"]))] = g
    pairs = [(row, judged.get((row["run_dir"], row["case_id"], row["repeat"]))) for row in labels]
    pairs = [(row, g) for row, g in pairs if g and "error" not in g]
    human = [row["human_verdict"].strip().lower() for row, _ in pairs]
    model = [g["verdict"] for _, g in pairs]
    agree = sum(h == m for h, m in zip(human, model, strict=True)) / len(pairs)
    diffs = [
        abs(int(row["human_correctness"]) - g["correctness"])
        for row, g in pairs
        if row["human_correctness"].strip()
    ]
    lines = [
        "# Judge calibration",
        "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC from {len(pairs)} answers "
        "labelled by a person without seeing the judge's grades.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Verdict agreement (pass/fail) | {agree:.0%} |",
        f"| Cohen's kappa (verdict) | {kappa(human, model):.2f} |",
    ]
    if diffs:
        within = sum(d <= 1 for d in diffs) / len(diffs)
        lines.append(f"| Correctness within 1 point | {within:.0%} (n={len(diffs)}) |")
    lines += ["", "| Case | Human | Judge |", "|---|---|---|"]
    lines += [
        f"| {row['case_id']}#{row['repeat']} | {h} | {m} |"
        for (row, _), h, m in zip(pairs, human, model, strict=True)
        if h != m
    ]
    (ROOT / "calibration.md").write_text("\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    exp = sub.add_parser("export")
    exp.add_argument("run_dirs", nargs="+", type=Path)
    exp.add_argument("--n", type=int, default=30)
    sub.add_parser("score")
    args = parser.parse_args()
    if args.cmd == "export":
        export(args.run_dirs, args.n)
    else:
        score()


if __name__ == "__main__":
    main()
