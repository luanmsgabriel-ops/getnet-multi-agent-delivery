# ADR 002: LangGraph for state, the official Anthropic SDK for model calls

**Context.** We need persistent conversation state, a pause/resume point for human handoff, and full control of each model call (tools, structured output, caching, cost).
**Decision.** LangGraph `StateGraph` with a SQLite checkpointer owns the turn: prepare → supervisor ⇄ specialists → escalate → `interrupt()` → finalize. Inside the nodes, calls go through the `anthropic` SDK directly, with no LangChain model wrapper.
**Alternatives.** A hand-written loop with our own persistence (more code, reinventing interrupts). LangChain chat models (an extra abstraction between us and caching, structured outputs and usage accounting).
**Consequences.** Handoff and memory come from the framework (`interrupt`, `Command(resume)`, `thread_id`). Every model call is explicit, typed and costed in one place (`app/llm/client.py`).
