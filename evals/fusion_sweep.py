"""Tune the hybrid fusion weight and test the heading prefix on the DEV sets (never holdout_v3).

    uv run python -m evals.fusion_sweep

Uses the production embedder (app.rag.store.EMBED_MODEL). For each dev set, compares dense only
and hybrid with lexical weights 0.25 / 0.5 / 1.0, with and without the heading prefix on chunks.
"""

from datetime import UTC, datetime
from typing import Any

import numpy as np

from app.rag.store import EMBED_MODEL, Chunk, Embedder, Retriever, split_text
from evals.retrieval import ROOT, is_relevant, load_docs, norm
from evals.retrieval_sweep import DEV_SPLITS, items_for

WEIGHTS = (0.25, 0.5, 1.0)


def chunks_for(docs: list[dict[str, Any]], queries: list[str], prefix: bool) -> list[Chunk]:
    banned = {norm(q) for q in queries}
    out: list[Chunk] = []
    for d in docs:
        title = "" if norm(d["title"]) in banned else d["title"]
        kept = [ln for ln in d["text"].split("\n") if norm(ln.lstrip("# ")) not in banned]
        for n, part in enumerate(split_text("\n".join(kept), heading_prefix=prefix)):
            out.append(
                Chunk(
                    f"{d['sha256'][:12]}#{n}", d["url"], title, d["section"], d["captured_at"], part
                )
            )
    return out


def main() -> None:
    docs = load_docs()
    emb = Embedder()
    cache: dict[str, np.ndarray] = {}

    def vectors(texts: list[str]) -> np.ndarray:
        todo = [t for t in dict.fromkeys(texts) if t not in cache]
        if todo:
            for t, v in zip(todo, emb.embed_passages(todo), strict=True):
                cache[t] = v
        return np.stack([cache[t] for t in texts])

    rows = []
    for split in DEV_SPLITS:
        items = items_for(split, docs)
        queries = [] if split == "xling" else [i["query"] for i in items]
        for prefix in (False, True):
            chunks = chunks_for(docs, queries, prefix)
            vecs = vectors([c.indexed_text for c in chunks])
            configs = [("dense", 1.0)] + [("hybrid", w) for w in WEIGHTS]
            for mode, w in configs:
                ret = Retriever(chunks, emb, vecs, lexical_weight=w)
                ranks = []
                for it in items:
                    hits = ret.search(it["query"], k=10, mode=mode)  # type: ignore[arg-type]
                    ranks.append(
                        next((r for r, h in enumerate(hits, 1) if is_relevant(it, h.chunk)), None)
                    )
                n = len(ranks)
                label = "dense" if mode == "dense" else f"hybrid w_lex={w}"
                rows.append(
                    (
                        split,
                        "yes" if prefix else "no",
                        label,
                        n,
                        sum(1 for r in ranks if r and r <= 5) / n,
                        sum(1 for r in ranks if r) / n,
                        sum(1 / r for r in ranks if r) / n,
                    )
                )
        print(f"{split}: done", flush=True)
    lines = [
        f"# Fusion and heading-prefix sweep on dev ({EMBED_MODEL}, "
        f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC)",
        "",
        "| Set | Heading prefix | Ranking | n | R@5 | R@10 | MRR@10 |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    lines += [
        f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]:.2f} | {r[5]:.2f} | {r[6]:.2f} |"
        for r in rows
    ]
    # mean over the three Portuguese dev sets (xling has only 10 queries)
    lines += ["", "Mean R@5 over dev, holdout and holdout_v2:", ""]
    for prefix in ("no", "yes"):
        for label in ["dense"] + [f"hybrid w_lex={w}" for w in WEIGHTS]:
            vals = [r[4] for r in rows if r[1] == prefix and r[2] == label and r[0] != "xling"]
            lines.append(f"- prefix={prefix}, {label}: {sum(vals) / len(vals):.3f}")
    report = "\n".join(lines) + "\n"
    out = ROOT / "results" / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-retrieval-fusion-sweep"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
