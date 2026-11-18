# LLM-judge report (openai/gpt-5-mini)

Graded 36/36 runs. Judge: different model family from the generator, blind packet (no expected answer, no generator identity).

| Metric | Value |
|---|---|
| correctness (mean 1-5, n=36) | 4.81 |
| groundedness (mean 1-5, n=35) | 4.63 |
| relevance (mean 1-5, n=36) | 5.00 |
| completeness (mean 1-5, n=36) | 5.00 |
| clarity (mean 1-5, n=36) | 5.00 |
| verdict pass | 97% |
| policy violations | 0 |
| unsupported claims (total) | 16 |
| judge cost (total) | US$ 0.0899 |

## Failed verdicts

| Case | Repeat | Scores | Rationale |
|---|---|---|---|
| M10 | 3 | corr=3 grou=2 rele=5 comp=5 clar=5 | The reply addresses the user's question and provides a clear, complete breakdown (dates, per-day amounts, settlement account, limitations). Many per-date amounts and the 863,82 figure match the provided receivables data, |
