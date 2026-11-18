"""Scripted LLM used by integration tests: deterministic tool calls, no network."""

import itertools
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from app.llm.client import CallRecord, LLMResult, current_usage

_ids = itertools.count(1)

Step = LLMResult | Callable[[list[dict[str, Any]]], LLMResult]


def text(value: str) -> LLMResult:
    return LLMResult(
        content=[{"type": "text", "text": value}], stop_reason="end_turn", model="fake"
    )


def calls(*uses: tuple[str, dict[str, Any]]) -> LLMResult:
    content = [
        {"type": "tool_use", "id": f"toolu_{next(_ids)}", "name": name, "input": args}
        for name, args in uses
    ]
    return LLMResult(content=content, stop_reason="tool_use", model="fake")


class ScriptedLLM:
    """Returns the next scripted step for each agent; records every request."""

    def __init__(self, script: dict[str, list[Step]], repeat_last: bool = False) -> None:
        self.script = {k: list(v) for k, v in script.items()}
        self.repeat_last = repeat_last
        self.requests: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def create(
        self,
        *,
        agent: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        effort: str,
        max_tokens: int = 16000,
        tool_choice: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        self.requests[agent].append(
            {
                "messages": [dict(m) for m in messages],
                "tools": tools,
                "tool_choice": tool_choice,
                "effort": effort,
            }
        )
        if agent == "guardrail" and agent not in self.script:
            return text('{"category": "ok", "language": "en", "reason": "test default"}')
        queue = self.script.get(agent) or []
        if not queue:
            raise AssertionError(f"no scripted step left for agent '{agent}'")
        step = queue[0] if (self.repeat_last and len(queue) == 1) else queue.pop(0)
        if tool_choice == {"type": "none"}:
            step = text("Resposta final com o que foi obtido.")
        result = step(messages) if callable(step) else step
        tracker = current_usage.get()
        if tracker is not None:
            tracker.add(CallRecord(agent, "fake", 100, 20, 0, 0, 0, 0.001, 5, result.stop_reason))
        return result
