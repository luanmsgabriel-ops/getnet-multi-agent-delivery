"""Keyword-router baseline: what a rule-based router (like v1/v2's) would route.

    uv run python -m evals.baseline [<run dir> ...]

Computes routing accuracy of a keyword router on the same cases (no LLM, free) and, when
run directories are given, puts the supervisor's measured routing next to it.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

from evals.run import load_cases

SUPPORT = (
    r"vend|receb|caiu|cair|cai |deposit|terminal|maquininha.*(online|offline)|recus|declin|"
    r"chamado|ticket|taxa.*(ontem|hoje)|sold|sales|receivable|code \d|codigo \d"
)
KNOWLEDGE = (
    r"getnet|pix|link|credi|antecip|wi-?fi|erro|tap|smart|classica|cancel|chargeback|"
    r"tempo|chov|weather|temperatura|cota|dolar|euro|libra|ptax|rate|whatsapp|dcc|status"
)


def norm(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in plain if not unicodedata.combining(c))


def keyword_route(message: str) -> set[str]:
    text = norm(message)
    agents = set()
    if re.search(SUPPORT, text):
        agents.add("support")
    if re.search(KNOWLEDGE, text):
        agents.add("knowledge")
    return agents or {"knowledge"}


def main(run_dirs: list[str]) -> None:
    cases = [
        c
        for split in ("original", "dev")
        for c in load_cases(split, None)
        if c["expected"]["agents"]
        if "expected" in c
    ]
    exact = [keyword_route(c["turns"][-1]) == set(c["expected"]["agents"]) for c in cases]
    covered = [set(c["expected"]["agents"]) <= keyword_route(c["turns"][-1]) for c in cases]
    multi = [c for c in cases if len(c["expected"]["agents"]) > 1]
    multi_ok = [set(c["expected"]["agents"]) <= keyword_route(c["turns"][-1]) for c in multi]
    print(f"Keyword router on {len(cases)} single-turn cases with expected agents:")
    print(f"  exact agent set: {sum(exact)}/{len(cases)} ({sum(exact) / len(cases):.0%})")
    print(f"  expected agents covered: {sum(covered)}/{len(cases)}")
    print(f"  multi-intent covered: {sum(multi_ok)}/{len(multi)}")
    for d in run_dirs:
        rows = [
            json.loads(line) for line in (Path(d) / "raw.jsonl").read_text("utf-8").splitlines()
        ]
        ok = [r["checks"].get("routing_ok", False) for r in rows]
        print(
            f"  supervisor ({Path(d).name}): expected agents used in "
            f"{sum(ok)}/{len(ok)} runs ({sum(ok) / len(ok):.0%})"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
