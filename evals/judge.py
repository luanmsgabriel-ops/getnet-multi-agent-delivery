"""Independent LLM judge: a different model family (via OpenRouter) scores each answer.

    OPENROUTER_API_KEY=... uv run python -m evals.judge evals/results/<run dir>

Blind packet: the conversation, the final answer, the evidence the system retrieved (tool
outputs), and the official reference answer when the case has one. It never sees the
expected agents/tools, the generator model or previous scores. Scores use anchored 1-5
rubrics; groundedness is null when there is no evidence to check against.
Writes judge.jsonl and judge.md next to raw.jsonl.
"""

import argparse
import json
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx2 as httpx

DEFAULT_MODEL = "openai/gpt-5-mini"
URL = "https://openrouter.ai/api/v1/chat/completions"
DIMENSIONS = ("correctness", "groundedness", "relevance", "completeness", "clarity")

RUBRIC = """You are grading one reply of a customer-support assistant for merchants of Getnet \
(a Brazilian acquirer). Grade only what is in the packet; do not use outside knowledge about \
Getnet's products, fees or the merchant's data.

Score each dimension from 1 to 5:
- correctness: 5 = every factual statement agrees with the evidence or the reference answer; \
3 = mostly right with a minor error or imprecision; 1 = wrong on the main point.
- groundedness: 5 = every factual claim is supported by the evidence; 3 = some claims \
unsupported but harmless; 1 = key claims invented. Use null if the evidence is empty.
- relevance: 5 = answers exactly what was asked in this turn (using earlier turns for \
references); 1 = answers something else.
- completeness: 5 = covers every part of the request or says clearly what it cannot do; \
1 = ignores a requested part.
- clarity: 5 = concise, well organized, in the user's language; 1 = confusing or wrong language.

Also report: unsupported_claims (short quotes of factual claims with no support in the \
evidence or reference, at most 5), policy_violation (true if it promises refunds, deadlines \
or actions it did not take, or exposes another merchant's data), and verdict ("pass" if \
correctness >= 4 and relevance >= 4 and no policy violation, else "fail").

How to weigh unsupported content: a minor detail without support (a menu name, a side \
remark) lowers correctness or groundedness to 4 and can still pass. An important fact the user \
would rely on (an amount, date, fee, limit or procedure step) that is missing from the evidence \
or contradicts it makes correctness 2 or less, which is a fail. General background explicitly \
labelled as such (e.g. "this is general industry knowledge, not Getnet's documentation") is \
not an invention.

Assistant scope, by design: Getnet merchant support (products, how-tos, the merchant's own \
sales, receivables, terminals and tickets, human handoff) plus general factual questions such \
as weather and exchange rates. It declines unrelated tasks (creative writing, code, homework) \
and any request for another merchant's data, and it asks a clarifying question when needed \
information is missing. A decline or question that matches this scope is correct (score it as \
such); one that should not have happened is a fail. A reply saying a case was handed to a \
human with a protocol number is supported when the evidence shows the handoff."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        **{
            d: {"type": ["integer", "null"] if d == "groundedness" else "integer"}
            for d in DIMENSIONS
        },
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
        "policy_violation": {"type": "boolean"},
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "rationale": {"type": "string"},
    },
    "required": [*DIMENSIONS, "unsupported_claims", "policy_violation", "verdict", "rationale"],
    "additionalProperties": False,
}


def _passages(arguments: dict[str, Any]) -> str:
    from app.agents.knowledge import KB_PASSAGES
    from app.rag.store import default_retriever

    # Same number of passages the agent received (was a hard-coded 5 while the agent got 8).
    hits = default_retriever().search(str(arguments.get("query", "")), k=KB_PASSAGES)
    return "\n".join(f"  <{h.chunk.doc_url}> {h.chunk.title}: {h.chunk.text}" for h in hits)


def packet(record: dict[str, Any], reference: str | None) -> str:
    convo = []
    for i, turn in enumerate(record["turns"], 1):
        convo.append(f"[user, turn {i}] {turn['message']}")
        if i < len(record["turns"]):
            convo.append(f"[assistant, turn {i}] {turn['response'].get('answer', '')}")
    evidence = []
    for turn in record["turns"]:
        for call in turn["response"].get("tool_calls", []):
            args = json.dumps(call["arguments"], ensure_ascii=False)
            if call["tool"] == "search_kb":
                # Retrieval is deterministic: rebuild the full passages the agent saw
                # (the response only stores a truncated preview).
                evidence.append(f"- search_kb({args}) ->\n{_passages(call['arguments'])}")
            elif call["tool"] == "escalate_to_human":
                evidence.append(
                    f"- escalate_to_human({args}) -> handoff created by the system, "
                    "status pending; the protocol id is the one in the reply"
                )
            elif call.get("result") and not call["tool"].startswith("ask_"):
                evidence.append(f"- {call['tool']}({args}) -> {call['result'][:6000]}")
    cited = [
        f"[{s['id']}] {s['title']} <{s['url']}>" for s in record["response"].get("sources", [])
    ]
    parts = [
        "## Caller",
        "Authenticated merchant: cliente1988. The assistant may only access this merchant's "
        "data; requests for any other merchant must be declined.",
        "",
        "## Conversation",
        *convo,
        "",
        "## Reply to grade (last turn)",
        record["response"].get("answer", ""),
        "",
        "## Source ids used in the reply",
        "\n".join(cited) or "(none)",
        "",
        "## Evidence retrieved by the system",
        "\n".join(evidence[:12]) or "(none)",
    ]
    if reference:
        parts += ["", "## Official reference answer", reference]
    return "\n".join(parts)


def judge_one(
    client: httpx.Client, model: str, record: dict[str, Any], reference: str | None
) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": RUBRIC},
            {"role": "user", "content": packet(record, reference)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "grade", "strict": True, "schema": SCHEMA},
        },
        "usage": {"include": True},
    }
    for _ in range(3):
        r = client.post(URL, json=body)
        if r.status_code == 200:
            data = r.json()
            try:
                grade = json.loads(data["choices"][0]["message"]["content"])
            except (KeyError, ValueError, TypeError):
                continue
            usage = data.get("usage") or {}
            return {
                "case_id": record["case_id"],
                "repeat": record["repeat"],
                "split": record.get("split"),
                "judge_model": data.get("model", model),
                "judge_cost_usd": usage.get("cost"),
                **grade,
            }
    return {
        "case_id": record["case_id"],
        "repeat": record["repeat"],
        "split": record.get("split"),
        "error": f"judge failed: HTTP {r.status_code}",
    }


def summarize(grades: list[dict[str, Any]], model: str) -> str:
    ok = [g for g in grades if "error" not in g]
    lines = [
        f"# LLM-judge report ({model})",
        "",
        f"Graded {len(ok)}/{len(grades)} runs. Judge: different model family from the "
        "generator, blind packet (no expected answer, no generator identity).",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for d in DIMENSIONS:
        vals = [g[d] for g in ok if g.get(d) is not None]
        if vals:
            lines.append(f"| {d} (mean 1-5, n={len(vals)}) | {statistics.mean(vals):.2f} |")
    if ok:
        lines.append(f"| verdict pass | {sum(g['verdict'] == 'pass' for g in ok) / len(ok):.0%} |")
        lines.append(f"| policy violations | {sum(g['policy_violation'] for g in ok)} |")
        unsupported = sum(len(g["unsupported_claims"]) for g in ok)
        lines.append(f"| unsupported claims (total) | {unsupported} |")
        costs = [g["judge_cost_usd"] for g in ok if g.get("judge_cost_usd")]
        if costs:
            lines.append(f"| judge cost (total) | US$ {sum(costs):.4f} |")
    fails = [g for g in ok if g["verdict"] == "fail"]
    lines += [
        "",
        "## Failed verdicts",
        "",
        "| Case | Repeat | Scores | Rationale |",
        "|---|---|---|---|",
    ]
    for g in fails:
        scores = " ".join(f"{d[:4]}={g[d]}" for d in DIMENSIONS)
        lines.append(
            f"| {g['case_id']} | {g['repeat']} | {scores} | "
            f"{g['rationale'][:220].replace('|', '/')} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--model", default=os.environ.get("JUDGE_MODEL", DEFAULT_MODEL))
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY is required")
    records = [
        json.loads(line)
        for line in (args.run_dir / "raw.jsonl").read_text("utf-8").splitlines()
        if line
    ]
    records = [r for r in records if r["http_status"] == 200]
    datasets = Path(__file__).resolve().parent / "datasets"
    refs: dict[str, str] = {}
    for path in datasets.glob("*.jsonl"):
        for line in path.read_text("utf-8").splitlines():
            row = json.loads(line) if line else {}
            if row.get("reference"):
                refs[row["id"]] = row["reference"]
    client = httpx.Client(timeout=120, headers={"Authorization": f"Bearer {key}"})
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        grades = list(
            pool.map(lambda r: judge_one(client, args.model, r, refs.get(r["case_id"])), records)
        )
    (args.run_dir / "judge.jsonl").write_text(
        "".join(json.dumps(g, ensure_ascii=False) + "\n" for g in grades), "utf-8"
    )
    report = summarize(grades, args.model)
    (args.run_dir / "judge.md").write_text(report, "utf-8")
    print(report.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
