# ADR 003: Hybrid retrieval with local multilingual embeddings

**Context.** The knowledge base is Portuguese; the challenge questions are English. Hosted embedding APIs add cost, a key and a network dependency at query time.
**Decision.** BM25 plus `paraphrase-multilingual-MiniLM-L12-v2` (local ONNX, baked into the image), fused by reciprocal rank. Snapshots are committed with URL, date and SHA-256.
**Alternatives.** Lexical only (6/10 English questions found vs 9/10 hybrid). A larger embedding model (the image would grow by 1-2 GB for a gain we could not show on dev).
**Consequences.** No API cost or network for retrieval. Holdout recall@5 is 0.58 on the strict official-FAQ protocol (`docs/RAG.md`). The model takes about 0.6 GB of RAM, loaded once at startup (see ADR 007).
