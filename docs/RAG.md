# RAG pipeline

```text
ingest (crawler) -> snapshots (JSON, hash) -> chunks -> BM25 + embeddings -> RRF -> Knowledge Agent -> cited answer
```

| Stage | Implementation | Why |
|---|---|---|
| Ingestion | `app/rag/ingest.py`: the site's XML sitemaps (help center, product pages, blog), product manuals (PDF) and the global English page. 1 request/s, generic user agent. Lines repeated across many pages (menus, footers, banners) are dropped. | Official content only, reproducible. |
| Storage | `corpus/docs/*.json` (`url, title, section, captured_at, sha256, text`) plus `corpus/manifest.json`, committed to git. | The index builds offline. Each fact can be traced to a URL, a date and a hash. |
| Chunking | Paragraph packing up to 1,000 characters, starting a new chunk at headings. The title is prefixed for indexing. Identical blocks are deduplicated. | 600 and 1,500 characters were tested on dev with no gain. |
| Retrieval | BM25 (in memory) and `paraphrase-multilingual-MiniLM-L12-v2` embeddings (local ONNX, built into the image), fused by reciprocal rank (k=60). | No API cost and no network at runtime. Hybrid matters for English questions over Portuguese content (below). |
| Generation | The Knowledge Agent (Claude) answers only from retrieved passages and cites `[S#]`. It reports `not_found` when they do not cover the question, and the supervisor can then try web search. | Answers are generated from retrieval. No answer text is hand-written in the repo. |

Current corpus (2026-11-17): **171 documents** (68 help center, 9 product, 91 blog, 2 manuals, 1 global) and **1,058 chunks**. The two PDF manuals come from the 2026-11-07 capture, because the PDF host returned HTTP 403 on 2026-11-17.

## Measured retrieval

Queries come from Getnet's own site, except `xling`. While measuring, the query text is removed from the index. Full protocol: `evals/retrieval.py`; exposure log: `evals/EXPOSURE.md`.

| Set | Queries | Mode | Recall@1 | Recall@5 | Recall@10 | MRR@10 |
|---|---:|---|---:|---:|---:|---:|
| dev: help-center titles | 68 | lexical | 0.37 | 0.66 | 0.78 | 0.50 |
| | | dense | 0.34 | 0.53 | 0.57 | 0.42 |
| | | hybrid | 0.38 | 0.63 | 0.74 | 0.49 |
| xling: English questions (ours) | 10 | lexical | 0.30 | 0.60 | 0.60 | 0.42 |
| | | dense | 0.50 | 0.80 | 0.90 | 0.66 |
| | | hybrid | 0.30 | **0.90** | 0.90 | 0.57 |
| **holdout: official FAQ** (run once) | 102 | lexical | 0.37 | 0.59 | 0.66 | 0.47 |
| | | dense | 0.25 | 0.39 | 0.51 | 0.32 |
| | | hybrid | **0.44** | 0.58 | **0.70** | **0.51** |

How to read these numbers:
- Hybrid is the default. It ties lexical on Portuguese queries and is clearly better when the merchant writes in English.
- Holdout recall@5 is 0.58. The FAQ answers are short paragraphs inside a single 46,000-character page, and the measurement strips the question text, so this is a strict, lower-bound setting.
- In the end-to-end eval, the agent can reformulate its query and fall back to web search. It needed web search in 1 of the 10 challenge questions, down from about 11 per 10 with the earlier 13-page knowledge base.
