"""FMP-specific Pydantic models and enums.

Generic types (dates, response format, output mode) are re-exported from
:mod:`turningbull_mcp.models` so tool modules can pull everything from a
single import.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated

from pydantic import BeforeValidator, Field

from turningbull_mcp.models import (  # noqa: F401  (re-exports)
    OptionalDate,
    RequiredDate,
    ResponseFormat,
    OutputMode,
)

SYMBOL_RE = re.compile(r"^[\^A-Z0-9.\-]{1,16}$")


def _normalize_symbol(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("symbol must be a string")
    s = value.strip().upper()
    if not SYMBOL_RE.match(s):
        raise ValueError(
            f"invalid symbol {value!r}: must match {SYMBOL_RE.pattern}"
        )
    return s


def _normalize_symbol_list(value: str | list[str]) -> str:
    if isinstance(value, list):
        items = value
    else:
        items = [p for p in str(value).split(",") if p.strip()]
    if not items:
        raise ValueError("symbol list cannot be empty")
    normalized = [_normalize_symbol(s) for s in items]
    return ",".join(normalized)


Symbol = Annotated[
    str,
    BeforeValidator(_normalize_symbol),
    Field(description="Single ticker symbol, e.g. AAPL or ^GSPC."),
]

SymbolList = Annotated[
    str,
    BeforeValidator(_normalize_symbol_list),
    Field(description="Comma-separated tickers or list, e.g. AAPL,MSFT."),
]


def _normalize_optional_symbol_list(value: str | list[str] | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return _normalize_symbol_list(value)


OptionalSymbolList = Annotated[
    str | None,
    BeforeValidator(_normalize_optional_symbol_list),
    Field(default=None, description="Comma-separated tickers; omit for global feed."),
]


class Period(str, Enum):
    annual = "annual"
    quarter = "quarter"
    q1 = "Q1"
    q2 = "Q2"
    q3 = "Q3"
    q4 = "Q4"


class Interval(str, Enum):
    one_min = "1min"
    five_min = "5min"
    fifteen_min = "15min"
    thirty_min = "30min"
    one_hour = "1hour"
    four_hour = "4hour"


class IndexName(str, Enum):
    sp500 = "sp500"
    nasdaq = "nasdaq"
    dowjones = "dowjones"


class SearchMode(str, Enum):
    name = "name"
    symbol = "symbol"


ECONOMIC_INDICATORS: tuple[str, ...] = (
    "GDP",
    "realGDP",
    "nominalPotentialGDP",
    "realGDPPerCapita",
    "federalFunds",
    "CPI",
    "inflationRate",
    "inflation",
    "retailSales",
    "consumerSentiment",
    "durableGoods",
    "unemploymentRate",
    "totalNonfarmPayroll",
    "initialClaims",
    "industrialProductionTotalIndex",
    "newPrivatelyOwnedHousingUnitsStartedTotalUnits",
    "totalVehicleSales",
    "retailMoneyFunds",
    "smoothedUSRecessionProbabilities",
    "30YearFixedRateMortgageAverage",
    "15YearFixedRateMortgageAverage",
)
