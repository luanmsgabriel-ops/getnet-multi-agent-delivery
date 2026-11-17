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


def _evidence(record: dict[str, Any]) -> str:
    from app.rag.store import default_retriever

    parts = []
    for turn in record["turns"]:
        for call in turn["response"].get("tool_calls", []):
            if call["tool"] == "search_kb":
                hits = default_retriever().search(str(call["arguments"].get("query", "")), k=3)
                parts += [f"[site Getnet] {h.chunk.title}: {h.chunk.text[:700]}" for h in hits]
            elif call["tool"] == "escalate_to_human":
                parts.append("[sistema] encaminhamento humano criado (protocolo na resposta)")
            elif call.get("result") and not call["tool"].startswith("ask_"):
                parts.append(f"[{call['tool']}] {call['result'][:1200]}")
    return "\n\n".join(parts)[:5000]


def export(run_dirs: list[Path], n: int, seed: int = 7) -> None:
    """Sample n answers (about a third from judge 'fail' verdicts, hidden from the labeller)."""
    refs = {}
    for path in (Path(__file__).resolve().parent / "datasets").glob("*.jsonl"):
        for line in path.read_text("utf-8").splitlines():
            row = json.loads(line) if line else {}
            if row.get("reference"):
                refs[row["id"]] = row["reference"]
    pool: dict[str, list[dict[str, Any]]] = {"pass": [], "fail": []}
    for d in run_dirs:
        verdicts = {}
        if (d / "judge.jsonl").exists():
            for line in (d / "judge.jsonl").read_text("utf-8").splitlines():
                g = json.loads(line)
                verdicts[(g["case_id"], g["repeat"])] = g.get("verdict", "pass")
        for line in (d / "raw.jsonl").read_text("utf-8").splitlines():
            r = json.loads(line)
            if r["http_status"] != 200:
                continue
            evidence = _evidence(r)
            if r["case_id"] in refs:
                evidence = f"[resposta oficial do FAQ] {refs[r['case_id']]}\n\n{evidence}"
            row = {
                "run_dir": d.name,
                "case_id": r["case_id"],
                "repeat": r["repeat"],
                "question": " || ".join(t["message"] for t in r["turns"]),
                "answer": r["response"].get("answer", ""),
                "evidence": evidence,
                "human_verdict": "",
                "human_correctness": "",
            }
            pool[verdicts.get((r["case_id"], r["repeat"]), "pass")].append(row)
    rng = random.Random(seed)
    for rows in pool.values():
        rng.shuffle(rows)
    picked = pool["fail"][: n // 3]
    picked += pool["pass"][: n - len(picked)]
    rng.shuffle(picked)
    ROOT.mkdir(exist_ok=True)
    with (ROOT / "labels.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(picked)
    md = [
        "# Rotulação: 30 respostas",
        "",
        "Para cada item responda numa linha: `número P|F nota(1-5) [comentário]`.",
        "",
    ]
    for i, row in enumerate(picked, 1):
        md += [
            "---",
            f"## {i}",
            "",
            f"**Pergunta:** {row['question']}",
            "",
            "**Resposta do assistente:**",
            "",
            row["answer"],
            "",
            "**Evidência (o que o sistema consultou):**",
            "",
            "```",
            row["evidence"] or "(nenhuma)",
            "```",
            "",
        ]
    (ROOT / "labels.md").write_text("\n".join(md), "utf-8")
    print(f"wrote {ROOT / 'labels.md'} and labels.csv with {len(picked)} items")


def import_answers(text_file: Path) -> None:
    """Parse lines like '7 F 2 comment' into labels.csv (row order = item number)."""
    rows = list(csv.DictReader((ROOT / "labels.csv").open(encoding="utf-8-sig")))
    for line in text_file.read_text("utf-8").splitlines():
        parts = line.strip().split(maxsplit=3)
        if len(parts) >= 3 and parts[0].isdigit() and parts[1].upper() in ("P", "F"):
            row = rows[int(parts[0]) - 1]
            row["human_verdict"] = "pass" if parts[1].upper() == "P" else "fail"
            row["human_correctness"] = parts[2]
    with (ROOT / "labels.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"labelled {sum(bool(r['human_verdict']) for r in rows)}/{len(rows)}")


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
    imp = sub.add_parser("import")
    imp.add_argument("text_file", type=Path)
    args = parser.parse_args()
    if args.cmd == "export":
        export(args.run_dirs, args.n)
    elif args.cmd == "import":
        import_answers(args.text_file)
    else:
        score()


if __name__ == "__main__":
    main()
