"""Deterministic checks on the last turn of every eval case (no LLM involved)."""

from typing import Any

# Models write Wi-Fi with a non-breaking hyphen (U+2011) and use non-breaking spaces;
# compare on plain ASCII forms.
_DASHES = (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)
_SPACES = (0x00A0, 0x202F, 0x2007)
_PLAIN = {c: ord("-") for c in _DASHES} | {c: ord(" ") for c in _SPACES}


def _norm(text: str) -> str:
    return text.translate(_PLAIN).lower()


def check(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected", {})
    agents = set(response.get("agents_used", []))
    tools = {t["tool"] for t in response.get("tool_calls", [])}
    answer = _norm(str(response.get("answer", "")))
    want_outcome = expected.get("outcome", "answered")
    outcome = response.get("outcome")
    outcome_ok = want_outcome == "any" or outcome == want_outcome
    if want_outcome == "answered" and outcome == "limit":
        outcome_ok = True  # answered with the step limit reached still counts as an answer
    groups = expected.get("must_include", [])
    missing = [g for g in groups if not any(_norm(alt) in answer for alt in g)]
    forbidden = [w for w in expected.get("must_not_include", []) if _norm(w) in answer]
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
