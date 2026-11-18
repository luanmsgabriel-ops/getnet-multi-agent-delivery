"""Figure check: numbers the merchant would rely on must appear in the retrieved evidence.

Only figures with a unit are checked (percentages, R$ amounts, installments, day/hour/month
counts, D+N), because those are the claims that cause harm when invented (fees, limits,
deadlines). Bare numbers, dates and times are ignored.
"""

import re
import unicodedata

_FIGURE = re.compile(
    r"(?i)(?:R\$\s*(\d[\d.]*(?:,\d+)?)"  # R$ 1.234,56
    r"|(\d+(?:[.,]\d+)?)\s*%"  # 3,15%
    r"|\b(\d+)\s*x\b"  # 48x
    r"|\bD\s*\+\s*(\d+)"  # D+30
    r"|\b(\d+(?:[.,]\d+)?)\s*(?:vezes|parcelas|dias(?:\s+úteis)?|horas|meses|business days|days"
    r"|hours|months|installments))"
)


def _digits(value: str) -> str:
    """Canonical form for comparison: 1.234,56 -> 1234,56 ; 3.15 -> 3,15."""
    value = value.strip().replace(" ", "")
    if "," in value:
        return value.replace(".", "")
    if value.count(".") == 1 and len(value.split(".")[1]) <= 2:
        return value.replace(".", ",")
    return value.replace(".", "")


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", text).replace(".", ",")


def unsupported_figures(answer: str, evidence: list[str]) -> list[str]:
    """Figures in the answer whose number does not occur anywhere in the evidence."""
    corpus = _plain(" ".join(evidence))
    missing: list[str] = []
    for match in _FIGURE.finditer(answer):
        number = next(g for g in match.groups() if g)
        canonical = _digits(number)
        if not re.search(rf"(?<![\d,]){re.escape(canonical)}(?![\d])", corpus):
            figure = match.group(0).strip()
            if figure not in missing:
                missing.append(figure)
    return missing
