"""Public data tools: weather forecast (Open-Meteo) and reference FX rate (BCB PTAX)."""

import datetime as dt
from datetime import timedelta
from typing import Any

from pydantic import Field

from app.agents.base import Source, ToolContext, ToolInput, ToolResult
from app.tools.http import UpstreamError, get_json

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
PTAX_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
)

# WMO weather interpretation codes (subset used by Open-Meteo)
WMO = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "rime fog",
    51: "light drizzle",
    53: "drizzle",
    55: "dense drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    80: "rain showers",
    81: "heavy rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with heavy hail",
}


class WeatherInput(ToolInput):
    city: str = Field(description="City name, optionally with state/country, e.g. 'Porto Alegre'.")
    date: dt.date = Field(description="Forecast day, YYYY-MM-DD (today up to 15 days ahead).")


def get_weather(ctx: ToolContext, args: WeatherInput) -> ToolResult:
    today = ctx.now.date()
    if not today <= args.date <= today + timedelta(days=15):
        return ToolResult.fail("invalid_argument", "Forecasts cover today up to 15 days ahead.")
    try:
        geo = get_json(GEOCODE_URL, {"name": args.city, "count": 1, "language": "pt"})
        places = geo.get("results") or []
        if not places:
            return ToolResult(
                status="not_found", data={"message": f"City '{args.city}' not found."}
            )
        place = places[0]
        forecast = get_json(
            FORECAST_URL,
            {
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                "precipitation_sum,weather_code,wind_speed_10m_max",
                "timezone": place.get("timezone", "America/Sao_Paulo"),
                "start_date": args.date.isoformat(),
                "end_date": args.date.isoformat(),
            },
        )
    except UpstreamError as exc:
        return ToolResult.fail(exc.code, str(exc), retryable=exc.code != "invalid_argument")
    daily: dict[str, list[Any]] = forecast.get("daily") or {}
    if not daily.get("time"):
        return ToolResult(status="not_found", data={"message": "No forecast for that day."})
    code = daily["weather_code"][0]
    return ToolResult(
        status="ok",
        data={
            "city": place["name"],
            "region": place.get("admin1"),
            "country": place.get("country"),
            "date": daily["time"][0],
            "summary": WMO.get(code, f"weather code {code}"),
            "temp_min_c": daily["temperature_2m_min"][0],
            "temp_max_c": daily["temperature_2m_max"][0],
            "precipitation_probability_pct": daily["precipitation_probability_max"][0],
            "precipitation_mm": daily["precipitation_sum"][0],
            "wind_max_kmh": daily["wind_speed_10m_max"][0],
        },
        sources=[
            Source(
                title="Open-Meteo forecast API",
                url="https://open-meteo.com/",
                retrieved_at=ctx.now.isoformat(timespec="minutes"),
            )
        ],
    )


class FxInput(ToolInput):
    currency: str = Field(description="ISO currency code against BRL, e.g. EUR, USD, GBP.")
    date: dt.date | None = Field(description="Reference day YYYY-MM-DD, or null for the latest.")


def get_exchange_rate(ctx: ToolContext, args: FxInput) -> ToolResult:
    currency = args.currency.strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        return ToolResult.fail("invalid_argument", "Use a 3-letter ISO code such as EUR.")
    end = args.date or ctx.now.date()
    start = end - timedelta(days=7)  # covers weekends and holidays
    try:
        payload = get_json(
            PTAX_URL,
            {
                "@moeda": f"'{currency}'",
                "@dataInicial": f"'{start:%m-%d-%Y}'",
                "@dataFinalCotacao": f"'{end:%m-%d-%Y}'",
                "$format": "json",
            },
        )
    except UpstreamError as exc:
        return ToolResult.fail(exc.code, str(exc), retryable=exc.code != "invalid_argument")
    quotes = payload.get("value") or []
    if not quotes:
        return ToolResult(
            status="not_found", data={"message": f"No PTAX quote for {currency} up to {end}."}
        )
    closing = [q for q in quotes if "Fechamento" in str(q.get("tipoBoletim"))]
    quote = (closing or quotes)[-1]
    quoted_day = str(quote["dataHoraCotacao"])[:10]
    return ToolResult(
        status="ok",
        data={
            "currency": currency,
            "against": "BRL",
            "buy_brl": quote["cotacaoCompra"],
            "sell_brl": quote["cotacaoVenda"],
            "bulletin": quote.get("tipoBoletim"),
            "quoted_at": quote["dataHoraCotacao"],
            "is_requested_day": quoted_day == end.isoformat(),
            "note": "PTAX is the Central Bank reference rate, not the rate applied by card "
            "machines (DCC) or banks.",
        },
        sources=[
            Source(
                title="Banco Central do Brasil - PTAX",
                url="https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes",
                retrieved_at=ctx.now.isoformat(timespec="minutes"),
            )
        ],
    )
