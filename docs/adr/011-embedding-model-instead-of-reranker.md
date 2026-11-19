# ADR 011: A stronger embedding model instead of a reranker; dense ranking by default

**Context.** v3 retrieval (MiniLM embeddings + BM25, equal-weight RRF) reached recall@5 of about 0.6 on both official holdouts. The evaluator's path to 9.5 was a multilingual cross-encoder reranker with recall@5 above 0.8.

**What was measured** (dev sets only; the v3 holdouts were frozen first, `evals/EXPOSURE.md`):

| Option | Result | Verdict |
|---|---|---|
| Cross-encoder `BAAI/bge-reranker-v2-m3` (int8) | about 50 s to rerank 30 passages on the project's CPU | rejected: unusable per query |
| Cross-encoder `jina-reranker-v2-base-multilingual` | about 15 s for 30 passages, 10 s for 20 | rejected |
| Embeddings `multilingual-e5-large` | dense recall@5: titles 0.75, FAQ 0.78, in-page Q&A 0.75, English 0.90; 159 ms per query; 2.2 GB | close second |
| **Embeddings `google/embeddinggemma-300m`** | dense recall@5: titles 0.87, FAQ 0.75, in-page Q&A 0.77, English 1.00; 48 ms per query; 1.2 GB | **chosen** (decision log) |
| Fusion weight on BM25 (0.25 / 0.5 / 1.0) with EmbeddingGemma | mean recall@5 0.771 / 0.752 / 0.737 against 0.794 for dense only | dense by default |
| Heading prefix on each chunk | 0.794 with and without | not adopted |
| Error-code articles (13 codes such as `ADQ 1-18`, `S-2074`) | 13/13 in the top 5 for dense and for every hybrid weight | dense does not lose exact codes |

**Decision.** Index with `google/embeddinggemma-300m` using its retrieval prefixes, and rank by dense similarity (`DEFAULT_MODE = "dense"`). BM25 stays in the code for comparison in the reports and as the automatic fallback when the embedding model is not available.

**Alternatives.**
- A reranker served by an API: adds a paid dependency and a network hop to every search.
- A GPU host for the cross-encoder: out of scope for a CPU container.
- e5-large: MIT license, slightly lower on dev, 3× slower per query and twice the size.

**Consequences.**
- Recall rose on every dev set, and each query costs about 50 ms.
- The image grows by about 1 GB, so the container memory limit goes from 1.5 to 2.5 GB.
- The index build takes longer (it runs once, at image build).
- The EmbeddingGemma license is Google's Gemma Terms of Use: commercial use is allowed under a prohibited-use policy. A production deployment should confirm that with legal; e5-large (MIT) is the fallback.
- Two negative results are documented: CPU cross-encoders and the heading prefix.
