# Fusion and heading-prefix sweep on dev (google/embeddinggemma-300m, 2026-11-19 11:36 UTC)

| Set | Heading prefix | Ranking | n | R@5 | R@10 | MRR@10 |
|---|---|---|---:|---:|---:|---:|
| dev | no | dense | 68 | 0.87 | 0.90 | 0.69 |
| dev | no | hybrid w_lex=0.25 | 68 | 0.78 | 0.91 | 0.66 |
| dev | no | hybrid w_lex=0.5 | 68 | 0.75 | 0.85 | 0.62 |
| dev | no | hybrid w_lex=1.0 | 68 | 0.74 | 0.81 | 0.57 |
| dev | yes | dense | 68 | 0.87 | 0.90 | 0.69 |
| dev | yes | hybrid w_lex=0.25 | 68 | 0.79 | 0.91 | 0.66 |
| dev | yes | hybrid w_lex=0.5 | 68 | 0.78 | 0.85 | 0.64 |
| dev | yes | hybrid w_lex=1.0 | 68 | 0.75 | 0.81 | 0.59 |
| holdout | no | dense | 102 | 0.75 | 0.80 | 0.63 |
| holdout | no | hybrid w_lex=0.25 | 102 | 0.76 | 0.83 | 0.63 |
| holdout | no | hybrid w_lex=0.5 | 102 | 0.75 | 0.80 | 0.63 |
| holdout | no | hybrid w_lex=1.0 | 102 | 0.72 | 0.77 | 0.58 |
| holdout | yes | dense | 102 | 0.75 | 0.79 | 0.64 |
| holdout | yes | hybrid w_lex=0.25 | 102 | 0.74 | 0.82 | 0.62 |
| holdout | yes | hybrid w_lex=0.5 | 102 | 0.74 | 0.79 | 0.63 |
| holdout | yes | hybrid w_lex=1.0 | 102 | 0.72 | 0.77 | 0.60 |
| holdout_v2 | no | dense | 121 | 0.77 | 0.80 | 0.60 |
| holdout_v2 | no | hybrid w_lex=0.25 | 121 | 0.77 | 0.85 | 0.59 |
| holdout_v2 | no | hybrid w_lex=0.5 | 121 | 0.76 | 0.84 | 0.59 |
| holdout_v2 | no | hybrid w_lex=1.0 | 121 | 0.76 | 0.82 | 0.58 |
| holdout_v2 | yes | dense | 121 | 0.77 | 0.80 | 0.60 |
| holdout_v2 | yes | hybrid w_lex=0.25 | 121 | 0.77 | 0.83 | 0.59 |
| holdout_v2 | yes | hybrid w_lex=0.5 | 121 | 0.75 | 0.83 | 0.58 |
| holdout_v2 | yes | hybrid w_lex=1.0 | 121 | 0.74 | 0.81 | 0.57 |
| xling | no | dense | 10 | 1.00 | 1.00 | 0.80 |
| xling | no | hybrid w_lex=0.25 | 10 | 1.00 | 1.00 | 0.75 |
| xling | no | hybrid w_lex=0.5 | 10 | 0.90 | 1.00 | 0.76 |
| xling | no | hybrid w_lex=1.0 | 10 | 0.90 | 0.90 | 0.65 |
| xling | yes | dense | 10 | 1.00 | 1.00 | 0.80 |
| xling | yes | hybrid w_lex=0.25 | 10 | 1.00 | 1.00 | 0.80 |
| xling | yes | hybrid w_lex=0.5 | 10 | 0.90 | 1.00 | 0.76 |
| xling | yes | hybrid w_lex=1.0 | 10 | 0.90 | 0.90 | 0.70 |

Mean R@5 over dev, holdout and holdout_v2:

- prefix=no, dense: 0.794
- prefix=no, hybrid w_lex=0.25: 0.771
- prefix=no, hybrid w_lex=0.5: 0.752
- prefix=no, hybrid w_lex=1.0: 0.737
- prefix=yes, dense: 0.794
- prefix=yes, hybrid w_lex=0.25: 0.766
- prefix=yes, hybrid w_lex=0.5: 0.756
- prefix=yes, hybrid w_lex=1.0: 0.736
