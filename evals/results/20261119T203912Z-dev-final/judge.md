# LLM-judge report (openai/gpt-5-mini)

Graded 40/40 runs. Judge: different model family from the generator, blind packet (no expected answer, no generator identity).

| Metric | Value |
|---|---|
| correctness (mean 1-5, n=40) | 4.67 |
| groundedness (mean 1-5, n=36) | 4.56 |
| relevance (mean 1-5, n=40) | 5.00 |
| completeness (mean 1-5, n=40) | 5.00 |
| clarity (mean 1-5, n=40) | 5.00 |
| verdict pass | 98% |
| policy violations | 0 |
| unsupported claims (total) | 23 |
| judge cost (total) | US$ 0.1067 |

## Failed verdicts

| Case | Repeat | Scores | Rationale |
|---|---|---|---|
| D29 | 1 | corr=3 grou=3 rele=5 comp=5 clar=5 | The assistant answered the user's question directly, gave clear, practical next steps, and offered to check the merchant's transactions (relevant and complete). However, the core factual statement that code 05 means a ge |
