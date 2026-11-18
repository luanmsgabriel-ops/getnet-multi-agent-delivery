# ADR 009: Rolling summary for long chats, allow-listed long-term merchant memory

**Context.** The checkpointer kept the last 8 turns verbatim and dropped older ones. In a long chat, the protocol number or amount from the first message was lost. Nothing carried over between sessions, so merchants had to repeat who they are.
**Decision.** Two separate stores.
- **Short-term memory:** when a session passes 8 turns, the oldest are folded into a rolling summary by a small, low-effort LLM call. The last 4 turns stay verbatim. The summary rides in the checkpointer state and is prefixed to the conversation as a tagged block. If the summary call fails, the turn still succeeds and only the last turns are kept.
- **Long-term memory:** the supervisor has a `remember` tool limited to three categories: `business_profile`, `communication_preference` and `recurring_context`. Each category holds one value of at most 200 characters, and the newest value wins. Values are redacted before storage and keyed by the token's tenant and merchant. They are injected as a `<merchant_memory>` data block. The merchant can read and erase them via `GET/DELETE /me/memory`.

**Alternatives.**
- Summarize every turn: a cost on every turn for no gain in short chats.
- A vector store of past conversations: more recall, but it keeps personal data and is hard to erase or audit.
- Free-form memory: open to poisoning, and it would retain whatever the merchant typed.

**Consequences.**
- Long chats keep their facts for about one extra small call every 4 turns after the 8th.
- Long-term memory is small, auditable and erasable (LGPD), and tested for isolation and redaction (`tests/integration/test_long_memory.py`).
- The summary is lossy by design. The facts that matter for a dispute also live in the handoff summary and the tickets.
