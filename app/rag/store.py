"""Knowledge base: chunking, lexical (BM25) and dense retrieval, fused with RRF.

Pipeline: corpus/docs/*.json snapshots -> section-aware chunks (title-prefixed) ->
BM25 index (in memory) + multilingual sentence embeddings (persisted in corpus/index) ->
hybrid search by reciprocal rank fusion. `python -m app.rag.store build` precomputes the
embeddings; the Docker build runs it so the container never needs the network.
"""

import hashlib
import json
import logging
import math
import os
import re
import sys
import threading
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

log = logging.getLogger("getnet.rag")

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "corpus" / "docs"
INDEX_DIR = ROOT / "corpus" / "index"
MODEL_DIR = Path(os.environ.get("EMBED_MODEL_DIR", ROOT / ".data" / "models"))
EMBED_MODEL = "google/embeddinggemma-300m"  # chosen on dev, see docs/adr/011
# EmbeddingGemma was trained with task prefixes for retrieval queries and documents
QUERY_PREFIX = "task: search result | query: "
PASSAGE_PREFIX = "title: none | text: "
CHUNK_CHARS = 1000
RRF_K = 60
LEXICAL_WEIGHT = 1.0  # weight of the BM25 ranking in the fusion (dense = 1.0)

Mode = Literal["lexical", "dense", "hybrid"]
# Production ranking, chosen on dev (docs/adr/011): dense ranks best on recall@5 and also
# finds the error-code articles; BM25 stays for comparison and as the fallback.
DEFAULT_MODE: Mode = "dense"

STOPWORDS = frozenset(
    (
        "a o as os de da do das dos e em no na nos nas um uma para por com como que se ao aos "
        "ou mais sua seu suas seus voce pode ser esta este isso the of and to in for on is are "
        "with how what can do does my i your it be or"
    ).split()
)


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_url: str
    title: str
    section: str
    captured_at: str
    text: str

    @property
    def indexed_text(self) -> str:
        return f"{self.title}\n{self.text}"


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


def tokenize(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return [t for t in re.findall(r"[a-z0-9]+", plain) if t not in STOPWORDS and len(t) > 1]


def split_text(text: str, size: int = CHUNK_CHARS, heading_prefix: bool = False) -> list[str]:
    """Pack paragraphs into chunks; a heading starts a new chunk when the current one is big.
    With heading_prefix, a chunk that does not start with a heading is prefixed with the last
    heading seen before it, so short passages keep their subject."""
    parts: list[str] = []
    current, heading, chunk_heading = "", "", ""

    def close() -> None:
        body = current.strip()
        if heading_prefix and chunk_heading and not body.startswith("#"):
            body = f"{chunk_heading}\n{body}"
        parts.append(body)

    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        starts_section = para.startswith("#") and len(current) > size // 3
        if current and (len(current) + len(para) > size or starts_section):
            close()
            current = ""
        if not current:
            chunk_heading = heading
        if para.startswith("#"):
            heading = para.lstrip("# ").strip()
        current += para + "\n\n"
    if current.strip():
        close()
    return parts


def load_chunks(corpus_dir: Path = CORPUS_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    seen: set[str] = set()
    for path in sorted(corpus_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for n, part in enumerate(split_text(doc["text"])):
            digest = hashlib.sha1(part.encode(), usedforsecurity=False).hexdigest()
            if digest in seen:  # identical blocks repeated across pages
                continue
            seen.add(digest)
            chunks.append(
                Chunk(
                    f"{doc['sha256'][:12]}#{n}",
                    doc["url"],
                    doc["title"],
                    doc.get("section", "unknown"),
                    doc["captured_at"],
                    part,
                )
            )
    return chunks


class BM25:
    def __init__(self, texts: list[str], k1: float = 1.4, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(t)) for t in texts]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lengths) / max(1, len(self.lengths))
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(texts)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        out = []
        for i, doc in enumerate(self.docs):
            s = 0.0
            for t in terms:
                tf = doc.get(t, 0)
                if tf:
                    norm = tf + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg)
                    s += self.idf[t] * tf * (self.k1 + 1) / norm
            out.append(s)
        return out


class Embedder:
    def __init__(self, model: str = EMBED_MODEL, cache_dir: Path = MODEL_DIR) -> None:
        from fastembed import TextEmbedding

        self.name = model
        # One ONNX thread per query: many small queries from concurrent chats beat one fast one.
        self._model = TextEmbedding(model_name=model, cache_dir=str(cache_dir), threads=1)

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.array(list(self._model.embed(texts, batch_size=16)), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.maximum(norms, 1e-12)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self.embed([PASSAGE_PREFIX + t for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        vector: np.ndarray = self.embed([QUERY_PREFIX + text])[0]
        return vector


def corpus_fingerprint(chunks: list[Chunk]) -> str:
    h = hashlib.sha256()
    for c in chunks:
        h.update(c.id.encode())
        h.update(c.text.encode())
    return h.hexdigest()[:16]


def build_embeddings(chunks: list[Chunk], embedder: Embedder, index_dir: Path = INDEX_DIR) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    vectors = embedder.embed_passages([c.indexed_text for c in chunks])
    np.save(index_dir / "embeddings.npy", vectors)
    (index_dir / "meta.json").write_text(
        json.dumps(
            {
                "model": embedder.name,
                "fingerprint": corpus_fingerprint(chunks),
                "chunks": len(chunks),
                "dim": int(vectors.shape[1]),
            }
        ),
        encoding="utf-8",
    )


def load_embeddings(chunks: list[Chunk], index_dir: Path = INDEX_DIR) -> np.ndarray | None:
    meta_path = index_dir / "meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("fingerprint") != corpus_fingerprint(chunks) or meta.get("model") != EMBED_MODEL:
        log.warning("embedding index is stale; run `python -m app.rag.store build`")
        return None
    vectors: np.ndarray = np.load(index_dir / "embeddings.npy")
    return vectors


class Retriever:
    def __init__(
        self,
        chunks: list[Chunk],
        embedder: Embedder | None = None,
        embeddings: np.ndarray | None = None,
        lexical_weight: float = LEXICAL_WEIGHT,
    ) -> None:
        self.chunks = chunks
        self.lexical_weight = lexical_weight
        self.bm25 = BM25([c.indexed_text for c in chunks])
        self.embedder = embedder
        self.embeddings = embeddings

    @property
    def dense_ready(self) -> bool:
        return self.embedder is not None and self.embeddings is not None

    def _rank_lexical(self, query: str, depth: int) -> list[tuple[int, float]]:
        scores = self.bm25.scores(query)
        ranked = sorted(((i, s) for i, s in enumerate(scores) if s > 0), key=lambda x: -x[1])
        return ranked[:depth]

    def _rank_dense(self, query: str, depth: int) -> list[tuple[int, float]]:
        assert self.embedder is not None and self.embeddings is not None
        sims = self.embeddings @ self.embedder.embed_query(query)
        top = np.argsort(-sims)[:depth]
        return [(int(i), float(sims[i])) for i in top]

    def search(self, query: str, k: int = 5, mode: Mode = DEFAULT_MODE) -> list[Hit]:
        if mode != "lexical" and not self.dense_ready:
            mode = "lexical"
        if mode == "lexical":
            ranked = self._rank_lexical(query, k)
        elif mode == "dense":
            ranked = self._rank_dense(query, k)
        else:
            fused: dict[int, float] = {}
            weighted = (
                (self.lexical_weight, self._rank_lexical(query, 50)),
                (1.0, self._rank_dense(query, 50)),
            )
            for weight, ranking in weighted:
                for rank, (i, _) in enumerate(ranking):
                    fused[i] = fused.get(i, 0.0) + weight / (RRF_K + rank + 1)
            ranked = sorted(fused.items(), key=lambda x: -x[1])[:k]
        return [Hit(self.chunks[i], score) for i, score in ranked]


_LOAD_LOCK = threading.Lock()
_RETRIEVER: Retriever | None = None


def default_retriever() -> Retriever:
    """Process-wide retriever, loaded once. The lock matters: the embedding model takes
    ~0.6 GB and tens of seconds to load, and concurrent first requests must not each load it."""
    global _RETRIEVER
    if _RETRIEVER is None:
        with _LOAD_LOCK:
            if _RETRIEVER is None:
                _RETRIEVER = _load()
    return _RETRIEVER


def retriever_loaded() -> bool:
    return _RETRIEVER is not None


def _load() -> Retriever:
    chunks = load_chunks()
    embeddings = load_embeddings(chunks)
    embedder: Embedder | None = None
    if embeddings is not None:
        try:
            embedder = Embedder()
        except Exception as exc:  # model unavailable: degrade to lexical, loudly
            log.warning("embedding model unavailable (%s); using lexical retrieval", exc)
            embeddings = None
    else:
        log.warning("no embedding index; using lexical retrieval")
    return Retriever(chunks, embedder, embeddings)


def main(argv: list[str]) -> int:
    if argv[:1] != ["build"]:
        print("usage: python -m app.rag.store build")
        return 2
    chunks = load_chunks()
    build_embeddings(chunks, Embedder())
    print(f"embedded {len(chunks)} chunks with {EMBED_MODEL}")
    return 0


def describe() -> dict[str, Any]:
    r = default_retriever()
    return {"chunks": len(r.chunks), "dense": r.dense_ready, "model": EMBED_MODEL}


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
