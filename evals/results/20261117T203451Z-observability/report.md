# Observability snapshot

Taken 2026-11-17 20:34 UTC from the `make obs` stack after real traffic (the 10 challenge scenarios with 3 concurrent clients, 2 blocked attacks, 1 feedback).

| Signal | Value |
|---|---|
| Chat turns by outcome | outcome=answered: 10<br>outcome=blocked: 2 |
| Chat latency p50 (s) | total: 43.36 |
| Chat latency p95 (s) | total: 84.88 |
| Average cost per turn (USD) | total: 0.1016 |
| LLM spend by agent (USD) | agent=guardrail: 0.02377<br>agent=supervisor: 0.2587<br>agent=knowledge: 0.8208<br>agent=support: 0.1165 |
| LLM calls by agent | agent=guardrail: 12<br>agent=supervisor: 20<br>agent=knowledge: 20<br>agent=support: 7 |
| LLM latency p95 by agent (s) | agent=support: 18<br>agent=guardrail: 4.838<br>agent=supervisor: 19.5<br>agent=knowledge: 42.75 |
| Cache-read tokens by agent | agent=guardrail: 6363<br>agent=supervisor: 2.842e+04<br>agent=knowledge: 2.217e+05<br>agent=support: 1.13e+04 |
| Tool calls by tool and status | status=ok, tool=get_sales_summary: 1<br>status=ok, tool=get_receivables: 1<br>status=ok, tool=ask_support: 3<br>status=ok, tool=ask_knowledge: 8<br>status=ok, tool=search_kb: 21<br>status=ok, tool=get_weather: 1<br>status=ok, tool=get_terminal_status: 2<br>status=not_found, tool=get_tickets: 1<br>status=ok, tool=get_exchange_rate: 1<br>status=ok, tool=get_recent_transactions: 1<br>status=ok, tool=lookup_decline_code: 2 |
| Guardrail input decisions | decision=ok: 10<br>decision=injection: 1<br>decision=harmful: 1 |
| Feedback | rating=up: 1 |
| Budget used (fraction) | instance=api:8000, job=getnet-agents: 0.1672 |

## Alert rules loaded

| Alert | State |
|---|---|
| ChatErrorRateHigh | inactive |
| ChatLatencyP95High | pending |
| LLMProviderErrors | inactive |
| LLMBudgetNearlyExhausted | inactive |
| CostPerChatHigh | inactive |
| ToolFailureRateHigh | inactive |
| HandoffsWaiting | inactive |
| GuardrailBlockSpike | inactive |

## One trace (d4ff823175462ea54c2e03b19bf38008)

| Span | Duration (ms) |
|---|---|
| POST /chat | 67949 |
| POST /chat | 67884 |
| fastapi.dependencies | 29 |
| fastapi.endpoint | 67810 |
| llm.guardrail | 2015 |
| anthropic.messages.create | 1970 |
| llm.supervisor | 19990 |
| anthropic.messages.create | 18582 |
| tool.ask_knowledge | 37173 |
| agent.knowledge | 37103 |
| tool.ask_support | 24446 |
| agent.support | 24372 |
| llm.knowledge | 2378 |
| anthropic.messages.create | 2279 |
| llm.support | 2764 |
| anthropic.messages.create | 2566 |
| tool.search_kb | 4002 |
| tool.search_kb | 3923 |
| tool.get_terminal_status | 102 |
| tool.get_tickets | 943 |
| llm.support | 19320 |
| anthropic.messages.create | 17456 |
| llm.knowledge | 2615 |
| anthropic.messages.create | 2457 |
| tool.search_kb | 14417 |
| tool.search_kb | 14387 |
| llm.knowledge | 12639 |
| anthropic.messages.create | 12513 |
| llm.supervisor | 8173 |
| anthropic.messages.create | 8129 |
| fastapi.serialization | 6 |
