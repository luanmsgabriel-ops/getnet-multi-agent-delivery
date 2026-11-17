"""Ingestion: crawl Getnet's public site into reviewed, hash-stamped snapshots.

    uv run --group ingest python -m app.rag.ingest            # crawl + write corpus/docs
    uv run --group ingest python -m app.rag.ingest --dry-run  # list what would be fetched

Sources: the site's XML sitemaps (help center "get-ajuda-*", product pages, blog posts),
product manuals (PDF) and the global English page. Boilerplate (menus, footers, cookie
banners) is removed by dropping lines that repeat across many pages. Snapshots are
committed, so the index builds offline and answers are reproducible.
"""

import argparse
import hashlib
import json
import re
import time
from collections import Counter
from datetime import UTC, datetime
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

import httpx2 as httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "corpus" / "docs"
USER_AGENT = "getnet-agents-demo/3.0 (knowledge-base snapshot; 1 req/s)"
SITEMAPS = [
    "https://site.getnet.com.br/page-sitemap.xml",
    "https://site.getnet.com.br/post-sitemap.xml",
]
EXTRA = [
    "https://www.getnet.net/en/",
    "https://site.getnet.com.br/wp-content/uploads/2025/09/Manul-GetSmart.pdf",
    "https://site.getnet.com.br/wp-content/uploads/2026/06/getnet_12_06-26_Manul_GetClassica_V2.pdf",
]
PRODUCT_PAGES = {
    "pix",
    "link-de-pagamento",
    "crediario",
    "todas-as-maquininhas",
    "taxas",
    "get-tap",
    "duvidas",
    "antifraude",
    "ecommerce",
    "loja-digital",
    "pagamentos-recorrentes",
    "emprestimos",
    "bandeiras",
    "getstore",
    "split-de-pagamento",
    "central-de-ajuda",
    "taxas-exclusivas-para-pj",
    "ofertas-tef-getnet",
    "aluguel",
    "vettore",
}
EXCLUDE = re.compile(
    r"sucesso|formulario|teste|copy|-old|redirect|bem-vindo|boas-vindas|"
    r"politica-de-privacidade|patrocinio|guia-digital|vivoempresas|hypera|"
    r"downloads|habilitar|dirf|emprestimo-out|nao-cliente|-\d{2}-\d{2}-\d{2}"
)


class _TextExtractor(HTMLParser):
    SKIP = frozenset(
        {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"}
    )
    BLOCK = frozenset(
        {
            "p",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "td",
            "th",
            "div",
            "section",
            "br",
            "dt",
            "dd",
            "summary",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth_skip = 0
        self.lines: list[str] = []
        self.buf: list[str] = []
        self.title = ""
        self._in_title = False
        self._heading = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self.depth_skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self._flush()
        if tag in {"h1", "h2", "h3", "h4"}:
            self._heading = "#" * int(tag[1]) + " "

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self.depth_skip:
            self.depth_skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self.depth_skip:
            self.buf.append(data)

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if text:
            self.lines.append(self._heading + text if self._heading else text)
            self._heading = ""
        self.buf = []


def html_to_text(html: str) -> tuple[str, list[str]]:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    title = re.sub("\\s*[|\\-–]\\s*Getnet.*$", "", parser.title.strip())  # noqa: RUF001
    return title, parser.lines


def pdf_to_text(data: bytes) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    lines: list[str] = []
    for page in reader.pages:
        lines += [ln.strip() for ln in (page.extract_text() or "").splitlines() if ln.strip()]
    return lines


def section_of(url: str) -> str:
    path = urlsplit(url).path.strip("/")
    first = path.split("/")[0] if path else "home"
    if url.endswith(".pdf"):
        return "manual"
    if first.startswith("get-ajuda"):
        return "help_center"
    if "getnet.net" in url:
        return "global"
    return "product" if first in PRODUCT_PAGES else "blog"


def discover(client: httpx.Client) -> list[str]:
    urls: list[str] = []
    for sitemap in SITEMAPS:
        xml = client.get(sitemap).text
        urls += re.findall(r"<loc>([^<]+)</loc>", xml)
    keep = []
    for url in urls:
        path = urlsplit(url).path.strip("/")
        first = path.split("/")[0] if path else ""
        if not path or EXCLUDE.search(path):
            continue
        is_post = len(path.split("/")) == 1 and first not in PRODUCT_PAGES
        if first.startswith("get-ajuda") or first in PRODUCT_PAGES or is_post:
            keep.append(url)
    return sorted(set(keep)) + EXTRA


def crawl(urls: list[str], client: httpx.Client, delay: float) -> list[dict[str, object]]:
    fetched: list[dict[str, object]] = []
    for i, url in enumerate(urls, 1):
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            print(f"[{i}/{len(urls)}] skip {url}: {type(exc).__name__}")
            continue
        if response.status_code != 200:
            print(f"[{i}/{len(urls)}] skip {url}: HTTP {response.status_code}")
            continue
        if url.endswith(".pdf"):
            title, lines = (
                Path(urlsplit(url).path).stem.replace("_", " "),
                pdf_to_text(response.content),
            )
        else:
            title, lines = html_to_text(response.text)
        fetched.append(
            {
                "url": str(response.url),
                "requested_url": url,
                "title": title,
                "lines": lines,
                "section": section_of(url),
            }
        )
        print(f"[{i}/{len(urls)}] ok {url} ({len(lines)} lines)")
        time.sleep(delay)
    return fetched


def remove_boilerplate(docs: list[dict[str, object]], share: float = 0.25) -> None:
    """Drop lines present in more than `share` of the HTML pages (menus, footers, banners)."""
    html_docs = [d for d in docs if d["section"] != "manual"]
    counts: Counter[str] = Counter()
    for d in html_docs:
        counts.update(set(d["lines"]))  # type: ignore[call-overload]
    limit = max(3, int(len(html_docs) * share))
    common = {line for line, n in counts.items() if n > limit}
    for d in html_docs:
        d["lines"] = [ln for ln in d["lines"] if ln not in common]  # type: ignore[attr-defined]


def write(docs: list[dict[str, object]], captured_at: str) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    manifest, seen = [], set()
    for d in docs:
        text = "\n\n".join(d["lines"]).strip()  # type: ignore[arg-type]
        sha = hashlib.sha256(text.encode()).hexdigest()
        if len(text) < 200 or d["url"] in seen or sha in seen:  # empty or duplicate pages
            continue
        seen.update({str(d["url"]), sha})
        record = {
            "url": d["url"],
            "title": d["title"] or d["url"],
            "section": d["section"],
            "captured_at": captured_at,
            "sha256": sha,
            "text": text,
        }
        (OUT / f"{sha[:16]}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        manifest.append(
            {k: record[k] for k in ("url", "title", "section", "sha256")} | {"chars": len(text)}
        )
    (OUT.parent / "manifest.json").write_text(
        json.dumps(
            {
                "captured_at": captured_at,
                "documents": len(manifest),
                "by_section": dict(Counter(m["section"] for m in manifest)),
                "items": manifest,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return len(manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    with httpx.Client(
        timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        urls = discover(client)[: args.limit]
        print(f"{len(urls)} URLs: {dict(Counter(section_of(u) for u in urls))}")
        if args.dry_run:
            print("\n".join(urls))
            return
        docs = crawl(urls, client, args.delay)
    remove_boilerplate(docs)
    n = write(docs, datetime.now(UTC).date().isoformat())
    print(f"wrote {n} documents to {OUT}")


if __name__ == "__main__":
    main()
