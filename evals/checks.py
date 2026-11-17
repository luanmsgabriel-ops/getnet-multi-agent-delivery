"""Deterministic checks applied to every eval response (no LLM involved)."""

from typing import Any


def check(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected", {})
    agents = set(response.get("agents_used", []))
    tools = {t["tool"] for t in response.get("tool_calls", [])}
    tool_errors = [t for t in response.get("tool_calls", []) if t["status"] == "error"]
    answer = str(response.get("answer", "")).lower()
    groups = expected.get("must_include", [])
    missing = [g for g in groups if not any(alt.lower() in answer for alt in g)]
    forbidden = [w for w in expected.get("must_not_include", []) if w.lower() in answer]
    routing_ok = set(expected.get("agents", [])) <= agents
    tools_ok = set(expected.get("tools", [])) <= tools
    content_ok = not missing and not forbidden
    return {
        "routing_ok": routing_ok,
        "tools_ok": tools_ok,
        "content_ok": content_ok,
        "passed": routing_ok and tools_ok and content_ok,
        "missing": missing,
        "forbidden": forbidden,
        "unexpected_tools": sorted(tools - set(expected.get("tools", []))),
        "tool_errors": len(tool_errors),
    }
