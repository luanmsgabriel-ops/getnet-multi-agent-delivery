"""Model prices in USD per million tokens (Anthropic first-party API, checked 2026-11-17).

Cache writes are billed at 1.25x input and cache reads at the listed rate.
Unknown models are priced as the most expensive known model (conservative).
"""

from dataclasses import dataclass

PRICES_CHECKED_AT = "2026-11-17"
WEB_SEARCH_USD_PER_CALL = 0.01  # confirm on the pricing page before large runs


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float

    @property
    def cache_write(self) -> float:
        return self.input * 1.25


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(4.00, 20.00, 0.20),
    "claude-sonnet-5-5": Price(2.00, 10.00, 0.10),
    "claude-haiku-5-5": Price(0.10, 0.50, 0.01),
}
_FALLBACK = max(PRICES.values(), key=lambda p: p.output)


def cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    web_searches: int = 0,
) -> float:
    price = next((p for name, p in PRICES.items() if model.startswith(name)), _FALLBACK)
    tokens = (
        input_tokens * price.input
        + output_tokens * price.output
        + cache_read_tokens * price.cache_read
        + cache_write_tokens * price.cache_write
    )
    return tokens / 1_000_000 + web_searches * WEB_SEARCH_USD_PER_CALL
