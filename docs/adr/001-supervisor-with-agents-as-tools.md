# ADR 001: Supervisor with specialist agents as tools

**Context.** v1 and v2 routed with rules (regex, keyword lists), which cannot decompose multi-intent requests, replan after a failed lookup, or decide when a human is needed.
**Decision.** The Router is an LLM supervisor. It calls the Knowledge, Support and Escalation agents as tools, in parallel when needs are independent, reads their structured observations (`status`, `coverage`, `answer`) and decides again. Each specialist is a small agent with its own prompt, tools and step limit.
**Alternatives.** A classifier router plus fixed pipelines (rejected: no replanning). A single agent with every tool (rejected: one long prompt mixing data access, RAG and policy, and no least-privilege per agent).
**Consequences.** More LLM calls per turn (measured: about 5) and higher latency, in exchange for multi-intent handling and replanning. On the same cases a keyword router gets 74% exact routing (`evals/baseline.py`).
