"""BLS-specific models and the curated popular-series catalog.

Generic types (response format, output mode) are re-exported from
:mod:`turningbull_mcp.models` so tool modules can pull everything from a
single import.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BeforeValidator, Field

from turningbull_mcp.models import (  # noqa: F401  (re-exports)
    OutputMode,
    ResponseFormat,
)

# BLS series IDs are alphanumeric, typically 8–20 chars (e.g. CUUR0000SA0,
# LNS14000000, CES0000000001). The regex is permissive to accommodate the
# full BLS namespace.
SERIES_ID_RE = re.compile(r"^[A-Z0-9]{3,30}$")


def _normalize_series_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("series_id must be a string")
    s = value.strip().upper()
    if not SERIES_ID_RE.match(s):
        raise ValueError(
            f"invalid BLS series_id {value!r}: must match {SERIES_ID_RE.pattern}"
        )
    return s


def _normalize_series_id_list(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        items = value
    else:
        items = [p for p in str(value).split(",") if p.strip()]
    if not items:
        raise ValueError("series_id list cannot be empty")
    return [_normalize_series_id(s) for s in items]


SeriesID = Annotated[
    str,
    BeforeValidator(_normalize_series_id),
    Field(description="BLS series ID, e.g. CUUR0000SA0 (CPI-U all items)."),
]

SeriesIDList = Annotated[
    list[str],
    BeforeValidator(_normalize_series_id_list),
    Field(description="One or more BLS series IDs (list or comma-separated string)."),
]


# Curated catalog of popular BLS series. Each entry is the public shape
# returned by `list_popular_series`. Kept here so the data is testable in
# isolation from the tool wrapper.
POPULAR_SERIES: dict[str, list[dict[str, str]]] = {
    "Prices": [
        {
            "id": "CUUR0000SA0",
            "title": "Consumer Price Index for All Urban Consumers (CPI-U): All items",
            "units": "Index 1982-84=100",
            "frequency": "monthly",
            "seasonal_adjustment": "not seasonally adjusted",
            "notes": "Headline CPI. Use CUSR0000SA0 for the seasonally-adjusted variant.",
        },
        {
            "id": "CUUR0000SA0L1E",
            "title": "CPI-U: All items less food and energy (Core CPI)",
            "units": "Index 1982-84=100",
            "frequency": "monthly",
            "seasonal_adjustment": "not seasonally adjusted",
            "notes": "Core CPI excludes volatile food and energy components.",
        },
        {
            "id": "CWUR0000SA0",
            "title": "CPI for Urban Wage Earners and Clerical Workers (CPI-W): All items",
            "units": "Index 1982-84=100",
            "frequency": "monthly",
            "seasonal_adjustment": "not seasonally adjusted",
            "notes": "Basis for Social Security COLA.",
        },
        {
            "id": "WPSFD4",
            "title": "Producer Price Index by Commodity: Final demand",
            "units": "Index Nov 2009=100",
            "frequency": "monthly",
            "seasonal_adjustment": "not seasonally adjusted",
            "notes": "Headline PPI final demand.",
        },
    ],
    "Labor": [
        {
            "id": "LNS14000000",
            "title": "Unemployment Rate (U-3)",
            "units": "Percent",
            "frequency": "monthly",
            "seasonal_adjustment": "seasonally adjusted",
            "notes": "Headline unemployment rate, 16 years and over.",
        },
        {
            "id": "LNS13327709",
            "title": "Total unemployed plus marginally attached plus part-time for economic reasons (U-6)",
            "units": "Percent",
            "frequency": "monthly",
            "seasonal_adjustment": "seasonally adjusted",
            "notes": "Broadest BLS measure of labor underutilization.",
        },
        {
            "id": "LNS11300000",
            "title": "Labor Force Participation Rate",
            "units": "Percent",
            "frequency": "monthly",
            "seasonal_adjustment": "seasonally adjusted",
            "notes": "Civilian labor force as a share of the civilian noninstitutional population.",
        },
        {
            "id": "CES0000000001",
            "title": "Total nonfarm employment, All employees",
            "units": "Thousands of persons",
            "frequency": "monthly",
            "seasonal_adjustment": "seasonally adjusted",
            "notes": "Headline payrolls from the Current Employment Statistics (establishment) survey.",
        },
        {
            "id": "CES0500000003",
            "title": "Total private average hourly earnings of all employees",
            "units": "Dollars per hour",
            "frequency": "monthly",
            "seasonal_adjustment": "seasonally adjusted",
            "notes": "Wage growth proxy from the CES survey.",
        },
    ],
    "Productivity": [
        {
            "id": "PRS85006092",
            "title": "Nonfarm business sector: Labor productivity (output per hour)",
            "units": "Percent change from previous quarter at annual rate",
            "frequency": "quarterly",
            "seasonal_adjustment": "seasonally adjusted",
            "notes": "BLS Productivity & Costs release.",
        },
    ],
}
