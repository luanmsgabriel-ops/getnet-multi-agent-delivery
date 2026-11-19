# LLM-judge report (openai/gpt-5-mini)

Graded 40/40 runs. Judge: different model family from the generator, blind packet (no expected answer, no generator identity).

| Metric | Value |
|---|---|
| correctness (mean 1-5, n=40) | 4.85 |
| groundedness (mean 1-5, n=37) | 4.73 |
| relevance (mean 1-5, n=40) | 5.00 |
| completeness (mean 1-5, n=40) | 4.95 |
| clarity (mean 1-5, n=40) | 4.97 |
| verdict pass | 98% |
| policy violations | 0 |
| unsupported claims (total) | 23 |
| judge cost (total) | US$ 0.1072 |

## Failed verdicts

| Case | Repeat | Scores | Rationale |
|---|---|---|---|
| D29 | 1 | corr=3 grou=2 rele=5 comp=5 clar=5 | The reply is relevant, clear and complete for the user question, but several key factual claims (the explicit meaning of decline code 05, the list of common causes, and the statement that Getnet documentation does not co |
