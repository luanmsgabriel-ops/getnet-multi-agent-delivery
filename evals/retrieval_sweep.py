"""Embedding-model sweep on the retrieval DEV sets only (never holdout_v3).

    uv run python -m evals.retrieval_sweep intfloat/multilingual-e5-large google/embeddinggemma-300m

Dev sets: help-center titles, the 10 English questions, and the two consumed holdouts (official
FAQ and in-page Q&A). Reports hybrid and dense recall@5/@10 and MRR@10 per model, plus the time
to embed one query. Query text is removed from the index while measuring, as in evals.retrieval.
"""

import json
import sys
import time
from datetime import UTC, datetime
from typing import Any

import numpy as np

from app.rag.store import MODEL_DIR, Retriever
from evals.retrieval import ROOT, build_sets, is_relevant, load_docs, stripped_chunks

# query / passage prefixes each model was trained with
PREFIX = {
    "intfloat/multilingual-e5-large": ("query: ", "passage: "),
    "google/embeddinggemma-300m": ("task: search result | query: ", "title: none | text: "),
    "Qwen/Qwen3-Embedding-0.6B-Q": (
        "Instruct: Given a merchant question, retrieve passages that answer it\nQuery: ",
        "",
    ),
}
DEV_SPLITS = ("dev", "holdout", "holdout_v2", "xling")


class PrefixedEmbedder:
    def __init__(self, name: str) -> None:
        from fastembed import TextEmbedding

        self.name = name
        self.q, self.p = PREFIX.get(name, ("", ""))
        self.model = TextEmbedding(model_name=name, cache_dir=str(MODEL_DIR), threads=4)
        self.cache: dict[str, np.ndarray] = {}

    def _embed(self, texts: list[str]) -> np.ndarray:
        v = np.array(list(self.model.embed(texts, batch_size=16)), dtype=np.float32)
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)

    def passages(self, texts: list[str]) -> np.ndarray:
        todo = [t for t in dict.fromkeys(texts) if t not in self.cache]
        if todo:
            for t, v in zip(todo, self._embed([self.p + t for t in todo]), strict=True):
                self.cache[t] = v
        return np.stack([self.cache[t] for t in texts])

    def embed_query(self, text: str) -> np.ndarray:  # Retriever calls this
        return self._embed([self.q + text])[0]


def items_for(split: str, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if split == "xling":
        path = ROOT / "datasets" / "retrieval_xling.jsonl"
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
    return build_sets(docs)[split]


def main(models: list[str]) -> None:
    docs = load_docs()
    rows = []
    for name in models:
        t0 = time.time()
        emb = PrefixedEmbedder(name)
        for split in DEV_SPLITS:
            items = items_for(split, docs)
            chunks = stripped_chunks(docs, [] if split == "xling" else [i["query"] for i in items])
            ret = Retriever(chunks, emb, emb.passages([c.indexed_text for c in chunks]))  # type: ignore[arg-type]
            for mode in ("dense", "hybrid"):
                ranks = []
                for it in items:
                    hits = ret.search(it["query"], k=10, mode=mode)  # type: ignore[arg-type]
                    ranks.append(
                        next((r for r, h in enumerate(hits, 1) if is_relevant(it, h.chunk)), None)
                    )
                n = len(ranks)
                rows.append(
                    (
                        name,
                        split,
                        mode,
                        n,
                        sum(1 for r in ranks if r and r <= 5) / n,
                        sum(1 for r in ranks if r) / n,
                        sum(1 / r for r in ranks if r) / n,
                    )
                )
        q0 = time.time()
        for _ in range(5):
            emb.embed_query("Como antecipar minhas vendas no app da Getnet?")
        rows.append((name, "query_ms", f"{(time.time() - q0) / 5 * 1000:.0f}", 0, 0, 0, 0))
        print(f"{name}: done in {time.time() - t0:.0f}s", flush=True)
    lines = [
        f"# Embedding sweep on dev sets ({datetime.now(UTC):%Y-%m-%d %H:%M} UTC)",
        "",
        "| Model | Set | Mode | n | R@5 | R@10 | MRR@10 |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        if r[1] == "query_ms":
            lines.append(f"| {r[0]} | query embedding | {r[2]} ms | | | | |")
        else:
            lines.append(
                f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]:.2f} | {r[5]:.2f} | {r[6]:.2f} |"
            )
    report = "\n".join(lines) + "\n"
    out = ROOT / "results" / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-retrieval-embedding-sweep"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main(sys.argv[1:])
