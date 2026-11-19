# Embedding sweep on dev sets (2026-11-19 11:02 UTC)

| Model | Set | Mode | n | R@5 | R@10 | MRR@10 |
|---|---|---|---:|---:|---:|---:|
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | dev | dense | 68 | 0.53 | 0.57 | 0.42 |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | dev | hybrid | 68 | 0.63 | 0.74 | 0.49 |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | holdout | dense | 102 | 0.39 | 0.51 | 0.32 |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | holdout | hybrid | 102 | 0.58 | 0.70 | 0.51 |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | holdout_v2 | dense | 121 | 0.40 | 0.55 | 0.30 |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | holdout_v2 | hybrid | 121 | 0.63 | 0.73 | 0.44 |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | xling | dense | 10 | 0.80 | 0.90 | 0.66 |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | xling | hybrid | 10 | 0.90 | 0.90 | 0.57 |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | query embedding | 15 ms | | | | |
| intfloat/multilingual-e5-large | dev | dense | 68 | 0.75 | 0.82 | 0.64 |
| intfloat/multilingual-e5-large | dev | hybrid | 68 | 0.76 | 0.82 | 0.58 |
| intfloat/multilingual-e5-large | holdout | dense | 102 | 0.78 | 0.85 | 0.67 |
| intfloat/multilingual-e5-large | holdout | hybrid | 102 | 0.73 | 0.79 | 0.61 |
| intfloat/multilingual-e5-large | holdout_v2 | dense | 121 | 0.75 | 0.79 | 0.54 |
| intfloat/multilingual-e5-large | holdout_v2 | hybrid | 121 | 0.74 | 0.82 | 0.60 |
| intfloat/multilingual-e5-large | xling | dense | 10 | 0.90 | 0.90 | 0.80 |
| intfloat/multilingual-e5-large | xling | hybrid | 10 | 0.90 | 0.90 | 0.68 |
| intfloat/multilingual-e5-large | query embedding | 159 ms | | | | |
| google/embeddinggemma-300m | dev | dense | 68 | 0.87 | 0.90 | 0.69 |
| google/embeddinggemma-300m | dev | hybrid | 68 | 0.74 | 0.81 | 0.57 |
| google/embeddinggemma-300m | holdout | dense | 102 | 0.75 | 0.80 | 0.63 |
| google/embeddinggemma-300m | holdout | hybrid | 102 | 0.72 | 0.77 | 0.58 |
| google/embeddinggemma-300m | holdout_v2 | dense | 121 | 0.77 | 0.80 | 0.60 |
| google/embeddinggemma-300m | holdout_v2 | hybrid | 121 | 0.76 | 0.82 | 0.58 |
| google/embeddinggemma-300m | xling | dense | 10 | 1.00 | 1.00 | 0.80 |
| google/embeddinggemma-300m | xling | hybrid | 10 | 0.90 | 0.90 | 0.65 |
| google/embeddinggemma-300m | query embedding | 48 ms | | | | |
