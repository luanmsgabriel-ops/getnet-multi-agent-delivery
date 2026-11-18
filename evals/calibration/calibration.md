# Judge calibration

Generated 2026-11-18 18:10 UTC from 30 answers labelled by a person without seeing the judge's grades.

| Metric | Value |
|---|---|
| Verdict agreement (pass/fail) | 87% |
| Cohen's kappa (verdict) | 0.44 |
| Correctness within 1 point | 87% (n=30) |

| Case | Human | Judge |
|---|---|---|
| O08#3 | fail | pass |
| O05#3 | fail | pass |
| D22#3 | fail | pass |
| F05#1 | fail | pass |

Before the judge packet stated the authenticated merchant, agreement was 73% (kappa 0.17); the judge failed correct refusals of another merchant's data. That fix was made after seeing these labels. The remaining disagreements are all cases where the judge passed and the human failed (the judge is more lenient), so judge pass rates are an upper bound.
