# Dataset exposure log

Which evaluation sets were seen, and what was tuned on them. A set marked **holdout** is run
once for the reported number and never used to choose prompts, parameters or models.

| Set | Type | Source (author) | Used for tuning? | Runs |
|---|---|---|---|---|
| `original.jsonl` | answer | challenge statement (Getnet) | yes (dev) | 2026-11-17: 10x3 real run (F2) |
| `retrieval_dev.jsonl` | retrieval | help-center article titles (Getnet site) | yes: chunk size, RRF weights, embedding model | 2026-11-17 sweep |
| `retrieval_xling.jsonl` | retrieval | 10 English questions (written by us) | yes: choice of hybrid over lexical | 2026-11-17 |
| `retrieval_holdout.jsonl` | retrieval | official FAQ questions, `/duvidas` page (Getnet site) | **no** | 2026-11-17 17:5x UTC, once, after all retrieval choices were fixed |
| `adversarial.jsonl` | guardrail | 60 attacks + 60 benign look-alikes (written by us) | **no**: classifier prompt written before the first run, unchanged after | 2026-11-17 18:28 UTC, once |
| `dev.jsonl`, `multi_turn.jsonl`, `handoff.jsonl` | answer | written by us | yes: three fixes after the first full run (reply language in context, output redaction scope, honest answer at the per-turn cost cap) | 2026-11-17 21:11 UTC (before fixes) and 21:35 UTC (dev and original after fixes) |
| `holdout_answers.jsonl` | answer | 20 official FAQ questions with the official answer (Getnet site) | **no** | 2026-11-17 21:21 UTC, once. Five of six judge failures were "not found in the knowledge base"; that weakness is documented, not tuned on this set. |
| `retrieval_holdout_v2.jsonl` | retrieval | 121 Q&A pairs written inside help-center and product pages (Getnet site) | **no** | 2026-11-18, once, after the RAG changes below were fixed on dev |
| `holdout_answers_v2.jsonl` | answer | 20 of those pairs with the official answer | **no** | 2026-11-18 21:09 UTC, once |
| `retrieval_holdout_v3.jsonl` | retrieval | 261 Q&A pairs written inside blog posts and manuals (Getnet site), sources never used before | **no** | frozen 2026-11-19 before any v4 retrieval change (sha256 `9c58f1e3107e5d2e…`, LF); not run yet |
| `holdout_answers_v3.jsonl` | answer | 60 of those pairs about products and payments (fixed keyword rule `PRODUCT_TERMS`), with the official answer | **no** | frozen 2026-11-19 (sha256 `a4873f7af82115c7…`, LF); not run yet |

## Retrieval decisions made on dev (before the holdout run)

- Chunk size 1000 chars, section-aware: 600 and 1500 tested, no gain.
- Embeddings `paraphrase-multilingual-MiniLM-L12-v2`: `potion-multilingual-128M` tested, worse.
- Hybrid RRF with equal weights: on Portuguese titles it ties lexical (R@5 0.63 vs 0.66).
  On English questions against the Portuguese corpus it is clearly better (R@5 0.90 vs 0.60),
  which is the challenge's setting.

## Judge packet fix (harness, not system)

The first judge pass truncated evidence to 2,500 characters and did not show that a handoff had been created, so it marked supported claims as invented. The packet now rebuilds the full retrieved passages (retrieval is deterministic), maps `[S#]` to URLs and shows the handoff action. All runs were re-judged with the same packet.

## Judge rubric alignment (2026-11-18)

A first calibration attempt used labels that the returned file itself marks as AI-generated ("Avaliação assistida por IA"), so they are **not** recorded as human labels. Comparing them with the judge (54% agreement) exposed three harness issues: the labelling PDF truncated evidence, the human instructions were stricter than the judge's pass rule, and the judge did not know the assistant's scope (it failed correct refusals). The judge rubric now states the scope and how to weigh minor versus important unsupported content. Humans and the judge receive the same rule and identical evidence. All final runs were re-judged with this rubric.


## RAG changes after the first holdouts (2026-11-18)

The first retrieval and answer holdouts became dev sets once used. Q&A-aware chunking was tried on them and on the original dev sets, and reverted (no gain). Retrieving 8 passages instead of 5 and the figure check were kept. Fresh holdouts were then built from Q&A inside help and product pages and run once.

## v4 retrieval work (2026-11-19)

All earlier retrieval and answer holdouts (`retrieval_holdout`, `retrieval_holdout_v2`, `holdout_answers`, `holdout_answers_v2`) are now **dev** sets. The reranker, the context prefix and the query-rewrite ablation are chosen on them. The v3 holdouts above were committed before any of that code existed and are run once at the end.
