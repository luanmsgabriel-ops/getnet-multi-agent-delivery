# LLM-judge report (openai/gpt-5-mini)

Graded 20/20 runs. Judge: different model family from the generator, blind packet (no expected answer, no generator identity).

| Metric | Value |
|---|---|
| correctness (mean 1-5, n=20) | 4.25 |
| groundedness (mean 1-5, n=18) | 4.44 |
| relevance (mean 1-5, n=20) | 4.85 |
| completeness (mean 1-5, n=20) | 4.25 |
| clarity (mean 1-5, n=20) | 4.95 |
| verdict pass | 80% |
| policy violations | 0 |
| unsupported claims (total) | 12 |
| judge cost (total) | US$ 0.0522 |

## Failed verdicts

| Case | Repeat | Scores | Rationale |
|---|---|---|---|
| F02 | 1 | corr=2 grou=5 rele=5 comp=3 clar=5 | The assistant correctly listed payment methods supported by Get Smart (QR Code, PIX, debit/credit, aproximação) which are supported by the provided evidence, and the response is clear and relevant. However, the main ques |
| F04 | 1 | corr=1 grou=1 rele=5 comp=2 clar=5 | The assistant's main factual claim (that no limit exists) is contradicted by the official reference answer which states the commercial condition contemplates up to 3 technologies and specifies a monthly fee (R$69,90) per |
| F09 | 1 | corr=3 grou=None rele=5 comp=2 clar=5 | The assistant's response is relevant and clear and appropriately asks for clarification about which program/vacancy/campaign the user means. However it does not answer the user's question. The official reference states t |
| F18 | 1 | corr=2 grou=2 rele=3 comp=2 clar=5 | The assistant's response is clear and offers reasonable next steps (contact support, suggest payment link), but it incorrectly states that there is no official step-by-step for 'venda digitada.' The official reference an |
