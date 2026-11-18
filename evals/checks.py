"""Deterministic checks on the last turn of every eval case (no LLM involved)."""

from typing import Any


def check(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected", {})
    agents = set(response.get("agents_used", []))
    tools = {t["tool"] for t in response.get("tool_calls", [])}
    answer = str(response.get("answer", "")).lower()
    want_outcome = expected.get("outcome", "answered")
    outcome = response.get("outcome")
    outcome_ok = want_outcome == "any" or outcome == want_outcome
    if want_outcome == "answered" and outcome == "limit":
        outcome_ok = True  # answered with the step limit reached still counts as an answer
    groups = expected.get("must_include", [])
    missing = [g for g in groups if not any(alt.lower() in answer for alt in g)]
    forbidden = [w for w in expected.get("must_not_include", []) if w.lower() in answer]
    routing_ok = set(expected.get("agents", [])) <= agents
    tools_ok = set(expected.get("tools", [])) <= tools
    content_ok = not missing and not forbidden
    return {
        "outcome_ok": outcome_ok,
        "routing_ok": routing_ok,
        "tools_ok": tools_ok,
        "content_ok": content_ok,
        "passed": outcome_ok and routing_ok and tools_ok and content_ok,
        "missing": missing,
        "forbidden": forbidden,
        "outcome": outcome,
        "unexpected_tools": sorted(tools - set(expected.get("tools", []))),
        "tool_errors": sum(t["status"] == "error" for t in response.get("tool_calls", [])),
    }
