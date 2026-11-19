# Judge calibration v4

Generated 2026-11-19 14:34 UTC. Labels: `labels_v4.csv` (rater 1, 70 items) and `labels_v4_second_rater.csv` (rater 2, the 50 measurement items). Both raters are people, labelled independently, without the judge's grades or each other's labels, and without AI help (stated by the author). The measurement half was never used to tune the judge. 95% intervals: bootstrap, 2,000 resamples.

| Pair | n | Agreement | Cohen's kappa (95% CI) | Gwet's AC1 (95% CI) | Fails (a / b) |
|---|---:|---:|---:|---:|---:|
| Judge vs rater 1 (measurement) | 50 | 98% | 0.85 (0.00 to 1.00) | 0.98 (0.92 to 1.00) | 3 / 4 |
| Judge vs rater 2 (measurement) | 50 | 100% | 1.00 (1.00 to 1.00) | 1.00 (1.00 to 1.00) | 3 / 3 |
| Rater 1 vs rater 2 (measurement) | 50 | 98% | 0.85 (0.00 to 1.00) | 0.98 (0.92 to 1.00) | 4 / 3 |
| Judge vs rater 1 (tuning half) | 20 | 95% | 0.00 (0.00 to 0.00) | 0.95 (0.83 to 0.95) | 1 / 0 |

Disagreements:

- item 29 (D06, measure): judge pass, rater 1 fail, rater 2 pass — rater 1: R$ 1 por link é condição do pacote da migração.
- item 70 (H59, tune): judge fail, rater 1 pass — rater 1: Faltou contexto de turismo, sem tratar 2025 como atual.
