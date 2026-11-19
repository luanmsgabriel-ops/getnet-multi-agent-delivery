"""Retrieval evaluation on official Getnet questions (no LLM, no cost).

Query sets are extracted from the site itself, not written by us:
  dev     - help-center article titles; relevant = any chunk of that article.
  xling   - 10 English questions (written by us, dev only) against the Portuguese corpus;
            relevant = a chunk whose URL contains the expected slug. Index is not stripped.
  holdout - questions of the official FAQ page (/duvidas); relevant = the chunk holding the
            start of the official answer. Used once for the reported number (EXPOSURE.md).

Anti-leakage: while measuring, the query text is removed from the index (article titles are
blanked and FAQ question lines deleted), so a hit means the *answer* was found from the
question's meaning, not from the question being copied in the page.

    uv run python -m evals.retrieval --split dev
    uv run python -m evals.retrieval --split holdout
"""

import argparse
import itertools
import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.rag.store import CORPUS_DIR, Chunk, Embedder, Retriever, split_text

ROOT = Path(__file__).resolve().parent
FAQ_URL = "https://site.getnet.com.br/duvidas/"
MODES = ("lexical", "dense", "hybrid")


def norm(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def load_docs() -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CORPUS_DIR.glob("*.json"))]


def faq_pairs(text: str) -> list[dict[str, str]]:
    lines = [ln.lstrip("# ").strip() for ln in text.split("\n") if ln.strip()]
    pairs, i = [], 0
    while i < len(lines):
        if lines[i].endswith("?"):
            question = lines[i]
            j = i + 1
            while j < len(lines) and norm(lines[j]) == norm(question):
                j += 1
            answer = []
            while j < len(lines) and not lines[j].endswith("?"):
                answer.append(lines[j])
                j += 1
            if len(" ".join(answer)) >= 40:
                pairs.append({"query": question, "answer": " ".join(answer)})
            i = j
        else:
            i += 1
    seen, unique = set(), []
    for p in pairs:
        if norm(p["query"]) not in seen:
            seen.add(norm(p["query"]))
            unique.append(p)
    return unique


def build_sets(docs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    dev = [
        {"query": d["title"], "relevant_url": d["url"]}
        for d in docs
        if d["section"] == "help_center" and len(norm(d["title"]).split()) >= 3
    ]
    faq = next(d for d in docs if d["url"] == FAQ_URL)
    holdout = [
        {"query": p["query"], "answer_prefix": norm(p["answer"])[:50]}
        for p in faq_pairs(faq["text"])
    ]
    return {
        "dev": dev,
        "holdout": holdout,
        "holdout_v2": inpage_pairs(docs),
        "holdout_v3": inpage_pairs(docs, ("blog", "manual")),
    }


SKIP_QUESTIONS = ("dúvidas", "duvidas", "pronto", "já conhece", "ja conhece")


def inpage_pairs(
    docs: list[dict[str, Any]], sections: tuple[str, ...] = ("help_center", "product")
) -> list[dict[str, Any]]:
    """Official Q&A written inside pages of the given sections (never the /duvidas FAQ).
    holdout_v2 = help-center and product pages (built after holdout 1 was consumed).
    holdout_v3 = blog posts and manuals (built after holdout 2 was consumed, frozen before
    the v4 retrieval changes; see EXPOSURE.md)."""
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d in docs:
        if d["section"] not in sections or d["url"] == FAQ_URL:
            continue
        lines = [ln.lstrip("# ").strip() for ln in d["text"].split("\n") if ln.strip()]
        for line, answer in itertools.pairwise(lines):
            if not (line.endswith("?") and 15 < len(line) < 160 and len(answer) > 60):
                continue
            if answer.endswith("?") or norm(line) == norm(d["title"]) or norm(line) in seen:
                continue
            if line.lower().startswith(SKIP_QUESTIONS):
                continue
            seen.add(norm(line))
            items.append(
                {"query": line, "answer_prefix": norm(answer)[:50], "source_url": d["url"]}
            )
    return items


def stripped_chunks(docs: list[dict[str, Any]], queries: list[str]) -> list[Chunk]:
    """Chunks with the query strings removed (titles blanked, question lines deleted)."""
    banned = {norm(q) for q in queries}
    chunks: list[Chunk] = []
    for d in docs:
        title = "" if norm(d["title"]) in banned else d["title"]
        kept = [ln for ln in d["text"].split("\n") if norm(ln.lstrip("# ")) not in banned]
        for n, part in enumerate(split_text("\n".join(kept))):
            chunks.append(
                Chunk(
                    f"{d['sha256'][:12]}#{n}", d["url"], title, d["section"], d["captured_at"], part
                )
            )
    return chunks


def is_relevant(item: dict[str, Any], chunk: Chunk) -> bool:
    if "relevant_url_contains" in item:
        return bool(item["relevant_url_contains"] in chunk.doc_url)
    if "relevant_url" in item:
        return bool(chunk.doc_url == item["relevant_url"])
    return bool(item["answer_prefix"][:40] in norm(chunk.text))


def evaluate(split: str) -> str:
    docs = load_docs()
    dataset = ROOT / "datasets" / f"retrieval_{split}.jsonl"
    if split == "xling":
        lines = dataset.read_text(encoding="utf-8").splitlines()
        items = [json.loads(line) for line in lines if line]
        chunks = stripped_chunks(docs, [])
    else:
        items = build_sets(docs)[split]
        dataset.write_text(
            "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8"
        )
        chunks = stripped_chunks(docs, [i["query"] for i in items])
    embedder = Embedder()
    retriever = Retriever(chunks, embedder, embedder.embed([c.indexed_text for c in chunks]))
    rows = []
    for mode in MODES:
        ranks = []
        for item in items:
            hits = retriever.search(item["query"], k=10, mode=mode)  # type: ignore[arg-type]
            rank = next((r for r, h in enumerate(hits, 1) if is_relevant(item, h.chunk)), None)
            ranks.append(rank)
        n = len(ranks)
        rows.append(
            {
                "mode": mode,
                "recall@1": sum(1 for r in ranks if r and r <= 1) / n,
                "recall@5": sum(1 for r in ranks if r and r <= 5) / n,
                "recall@10": sum(1 for r in ranks if r) / n,
                "mrr@10": sum(1 / r for r in ranks if r) / n,
            }
        )
    lines = [
        f"# Retrieval: `{split}` ({len(items)} queries, {len(chunks)} chunks)",
        "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC. Query text removed from the "
        "index while measuring.",
        "",
        "| Mode | Recall@1 | Recall@5 | Recall@10 | MRR@10 |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['mode']} | {r['recall@1']:.2f} | {r['recall@5']:.2f} | "
        f"{r['recall@10']:.2f} | {r['mrr@10']:.2f} |"
        for r in rows
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split", choices=["dev", "xling", "holdout", "holdout_v2", "holdout_v3"], default="dev"
    )
    args = parser.parse_args()
    report = evaluate(args.split)
    out = ROOT / "results" / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-retrieval-{args.split}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
