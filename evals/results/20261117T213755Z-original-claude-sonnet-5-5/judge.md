# LLM-judge report (openai/gpt-5-mini)

Graded 30/30 runs. Judge: different model family from the generator, blind packet (no expected answer, no generator identity).

| Metric | Value |
|---|---|
| correctness (mean 1-5, n=30) | 4.83 |
| groundedness (mean 1-5, n=30) | 4.60 |
| relevance (mean 1-5, n=30) | 5.00 |
| completeness (mean 1-5, n=30) | 5.00 |
| clarity (mean 1-5, n=30) | 5.00 |
| verdict pass | 97% |
| policy violations | 0 |
| unsupported claims (total) | 15 |
| judge cost (total) | US$ 0.0907 |

## Failed verdicts

| Case | Repeat | Scores | Rationale |
|---|---|---|---|
| O03 | 1 | corr=3 grou=4 rele=5 comp=5 clar=5 | The reply mostly matches the provided data (approved total, debit payment date/net, pix none, settlement account, declined amount, receivables schedule and installment net values). However it contains incorrect or incons |
