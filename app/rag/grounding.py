"""Figure check: numbers the merchant would rely on must appear in the retrieved evidence.

Only figures with a unit are checked (percentages, R$ amounts, installments, day/hour/month
counts, D+N), because those are the claims that cause harm when invented (fees, limits,
deadlines). Bare numbers, dates and times are ignored.

Numbers are compared as values, not strings: evidence mixes Brazilian text (1.234,56) and
JSON (1234.56, 6.372), and an answer may round (R$ 6,37 for 6.3702). A separator followed by
exactly three digits is ambiguous (thousands or decimals), so both readings are kept.
"""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

_FIGURE = re.compile(
    r"(?i)(?:R\$\s*(\d[\d.]*(?:,\d+)?)"  # R$ 1.234,56
    r"|(\d+(?:[.,]\d+)?)\s*%"  # 3,15%
    r"|\b(\d+)\s*x\b"  # 48x
    r"|\bD\s*\+\s*(\d+)"  # D+30
    r"|\b(\d+(?:[.,]\d+)?)\s*(?:vezes|parcelas|dias(?:\s+úteis)?|horas|meses|business days|days"
    r"|hours|months|installments))"
)
_NUMBER = re.compile(r"\d[\d.,]*\d|\d")


def _readings(token: str) -> set[Decimal]:
    """Every plausible value of a number written with '.' and/or ',' separators."""
    token = token.strip(".,")
    candidates: set[str] = set()
    if "," in token and "." in token:
        decimal_sep = "," if token.rfind(",") > token.rfind(".") else "."
        thousands = "." if decimal_sep == "," else ","
        candidates.add(token.replace(thousands, "").replace(decimal_sep, "."))
    elif "," in token or "." in token:
        sep = "," if "," in token else "."
        parts = token.split(sep)
        if len(parts) == 2:
            candidates.add(f"{parts[0]}.{parts[1]}")  # decimal
        if all(len(p) == 3 for p in parts[1:]):
            candidates.add("".join(parts))  # thousands
    else:
        candidates.add(token)
    values: set[Decimal] = set()
    for c in candidates:
        try:
            values.add(Decimal(c))
        except InvalidOperation:
            continue
    return values


def _places(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def _supported(figure: str, evidence_values: set[Decimal]) -> bool:
    for value in _readings(figure):
        places = _places(value)
        for known in evidence_values:
            if known == value:
                return True
            # A rounded figure (R$ 6,37 for 6.3702) is supported; whole numbers must be exact.
            if places > 0 and round(known, places) == value:
                return True
    return False


def unsupported_figures(answer: str, evidence: list[str]) -> list[str]:
    """Figures in the answer whose number does not occur anywhere in the evidence."""
    corpus = unicodedata.normalize("NFKC", " ".join(evidence))
    evidence_values: set[Decimal] = set()
    for token in _NUMBER.findall(corpus):
        evidence_values |= _readings(token)
    missing: list[str] = []
    for match in _FIGURE.finditer(answer):
        number = next(g for g in match.groups() if g)
        if not _supported(number, evidence_values):
            figure = match.group(0).strip()
            if figure not in missing:
                missing.append(figure)
    return missing
