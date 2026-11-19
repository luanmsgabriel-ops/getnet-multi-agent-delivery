"""Bench the final-answer verifier offline against the judge, on recorded DEV answers.

    uv run python -m evals.verifier_bench evals/results/<dev run without the verifier>

For each recorded answer, rebuilds the evidence the agents had (knowledge passages are re-run,
retrieval is deterministic; other tool outputs come from the recorded results; plus the
merchant's message), runs app.graph.verify.verify, and compares with the judge's
unsupported_claims for the same answer:
  - false alarm: the verifier fails an answer the judge found fully supported;
  - catch: the verifier fails an answer the judge found unsupported claims in.
Cost: one Claude Haiku 5.5 call per high-risk answer.
"""

import json
import sys
from pathlib import Path
from typing import Any

from app.graph.verify import date_facts, verify


def evidence_for(record: dict[str, Any]) -> list[str]:
    from app.agents.knowledge import KB_PASSAGES
    from app.config import get_settings
    from app.rag.store import default_retriever

    ev: list[str] = [date_facts(get_settings().now())]
    for turn in record["turns"]:
        ev.append(turn["message"])
        for call in turn["response"].get("tool_calls", []):
            if call["tool"] == "search_kb":
                hits = default_retriever().search(
                    str(call["arguments"].get("query", "")), k=KB_PASSAGES
                )
                ev += [f"{h.chunk.title}: {h.chunk.text}" for h in hits]
            elif not call["tool"].startswith(("ask_", "verify")) and call.get("result"):
                ev.append(str(call["result"]))
    return ev


EFFORT = sys.argv[2] if len(sys.argv) > 2 else "low"


def main(run_dir: Path) -> None:
    from app.config import get_settings
    from app.data.db import Database
    from app.llm.client import AnthropicLLM, Ledger

    settings = get_settings()
    db = Database(settings.data_dir / "getnet.db")
    llm = AnthropicLLM(
        settings.anthropic_api_key.get_secret_value(), Ledger(db, settings.llm_budget_usd)
    )  # type: ignore[union-attr]
    raw = [json.loads(x) for x in (run_dir / "raw.jsonl").read_text("utf-8").splitlines() if x]
    judged = {
        (g["case_id"], g["repeat"]): g
        for g in (
            json.loads(x) for x in (run_dir / "judge.jsonl").read_text("utf-8").splitlines() if x
        )
    }
    rows = []
    for r in raw:
        answer = str(r["response"].get("answer", ""))
        if r["response"].get("outcome") != "answered":
            continue
        verdict = verify(answer, evidence_for(r), llm, settings.verifier_model, EFFORT)
        judge_claims = judged.get((r["case_id"], r["repeat"]), {}).get("unsupported_claims") or []
        rows.append(
            (r["case_id"], verdict.status, verdict.checked_by, verdict.unsupported, judge_claims)
        )
    fails = [x for x in rows if x[1] == "fail"]
    judge_bad = [x for x in rows if x[4]]
    false_alarms = [x for x in fails if not x[4]]
    catches = [x for x in fails if x[4]]
    clean = len(rows) - len(judge_bad)
    print(f"answers {len(rows)} | verifier fails {len(fails)} | judge issues in {len(judge_bad)}")
    print(f"catches {len(catches)}/{len(judge_bad)} | false alarms {len(false_alarms)}/{clean}")
    for case, status, by, claims, jc in rows:
        if status == "fail" or jc:
            print(f"- {case} verifier={status}/{by} {claims[:2]} | judge={jc[:2]}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
