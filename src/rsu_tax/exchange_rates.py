"""Fetch USD→EUR exchange rates from the Frankfurter API (ECB data)."""

from __future__ import annotations

from datetime import date, timedelta

import httpx

_FRANKFURTER_BASE = "https://api.frankfurter.app"
_RATE_SANITY_MIN = 0.60
_RATE_SANITY_MAX = 1.15


def _shift_date(d: date, days: int) -> date:
    return d + timedelta(days=days)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


async def fetch_rates(start: str, end: str) -> dict[str, float]:
    """
    Fetch daily USD→EUR rates for [start, end] from Frankfurter API.
    Returns a dict mapping 'YYYY-MM-DD' → rate (1 USD = X EUR).
    """
    url = f"{_FRANKFURTER_BASE}/{start}..{end}?from=USD&to=EUR"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    data = resp.json()
    return {
        day: rate_obj["EUR"]
        for day, rate_obj in data.get("rates", {}).items()
    }


async def rates_for_dates(dates: list[str]) -> dict[str, float]:
    """
    Fetch rates for all given dates, extending the range by ±5 days to
    cover weekends and public holidays.
    """
    if not dates:
        return {}

    sorted_dates = sorted(dates)
    start = _shift_date(_parse_date(sorted_dates[0]), -5).isoformat()
    end = _shift_date(_parse_date(sorted_dates[-1]), 5).isoformat()

    return await fetch_rates(start, end)


def find_rate(date_str: str, rates: dict[str, float]) -> float | None:
    """
    Look up the exchange rate for a date.
    Falls back up to 7 days earlier (to handle weekends / public holidays).
    """
    result = find_rate_with_date(date_str, rates)
    return result[0] if result else None


def find_rate_with_date(
    date_str: str, rates: dict[str, float]
) -> tuple[float, str] | None:
    """
    Look up the exchange rate for a date, also returning the actual ECB publication date.
    Falls back up to 7 days earlier (to handle weekends / public holidays).
    Returns (rate, effective_date) or None.
    """
    if date_str in rates:
        return rates[date_str], date_str

    d = _parse_date(date_str)
    for i in range(1, 8):
        prev = _shift_date(d, -i).isoformat()
        if prev in rates:
            return rates[prev], prev

    return None
