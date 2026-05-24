"""BEA-specific models and shared enums.

Generic types (response format, output mode) are re-exported from
:mod:`turningbull_mcp.models` so tool modules can pull everything from a
single import.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated

from pydantic import BeforeValidator, Field

from turningbull_mcp.models import (  # noqa: F401  (re-exports)
    OutputMode,
    ResponseFormat,
)


# BEA "Frequency" parameter. Not every dataset accepts every value (e.g.
# NIPA M is available for some tables only); we let BEA decide and surface
# its error message rather than gating client-side.
class Frequency(str, Enum):
    A = "A"
    Q = "Q"
    M = "M"


# Valid BEA dataset names (from GetDataSetList). Used to type the
# `dataset` argument of generic / discovery tools. Lowercase mirrors how
# we'd want to write them in code; serialized form preserves BEA's casing.
class BEADataset(str, Enum):
    NIPA = "NIPA"
    NIUnderlyingDetail = "NIUnderlyingDetail"
    MNE = "MNE"
    FixedAssets = "FixedAssets"
    ITA = "ITA"
    IIP = "IIP"
    InputOutput = "InputOutput"
    IntlServTrade = "IntlServTrade"
    IntlServSTA = "IntlServSTA"
    GDPbyIndustry = "GDPbyIndustry"
    Regional = "Regional"
    UnderlyingGDPbyIndustry = "UnderlyingGDPbyIndustry"
    APIDatasetMetaData = "APIDatasetMetaData"


# BEA "Year" parameter accepts: a single 4-digit year, a comma-separated
# list, "ALL", "LAST5", "LAST10", or "X" (NIPA "all years" alias).
YEAR_TOKEN_RE = re.compile(r"^(\d{4}|ALL|LAST5|LAST10|X)$", re.IGNORECASE)


def _normalize_year_spec(value: str | int | list[str | int] | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
    else:
        parts = [p.strip() for p in str(value).split(",") if p.strip()]
    if not parts:
        return None
    normalized: list[str] = []
    for p in parts:
        up = p.upper()
        if not YEAR_TOKEN_RE.match(up):
            raise ValueError(
                f"invalid BEA year token {p!r}: expected YYYY, ALL, LAST5, "
                "LAST10, X, or a comma-separated list."
            )
        normalized.append(up if up in {"ALL", "LAST5", "LAST10", "X"} else p)
    return ",".join(normalized)


YearSpec = Annotated[
    str,
    BeforeValidator(_normalize_year_spec),
    Field(
        description=(
            "BEA Year parameter: a 4-digit year (2024), a comma-separated "
            "list (2022,2023,2024), or one of the special tokens ALL, LAST5, "
            "LAST10, X."
        )
    ),
]

OptionalYearSpec = Annotated[
    str | None,
    BeforeValidator(_normalize_year_spec),
    Field(
        default=None,
        description=(
            "Optional BEA Year parameter. Same syntax as YearSpec. Defaults "
            "to LAST5 in most typed tools."
        ),
    ),
]


# BEA TableName / TableID. TableName is alphanumeric (e.g. T20305, FAAt101,
# SAGDP1, CAINC4); TableID is an integer (GDPbyIndustry, InputOutput).
TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{1,32}$")


def _normalize_table_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("table_name must be a string")
    s = value.strip()
    if not TABLE_NAME_RE.match(s):
        raise ValueError(
            f"invalid BEA TableName {value!r}: must match {TABLE_NAME_RE.pattern}"
        )
    return s


TableName = Annotated[
    str,
    BeforeValidator(_normalize_table_name),
    Field(description="BEA TableName, e.g. T20305 (NIPA), CAINC4 (Regional)."),
]


# GeoFips is a 5-digit FIPS code OR one of BEA's special tokens.
GEOFIPS_SPECIALS = {
    "STATE",
    "COUNTY",
    "MSA",
    "MIC",
    "CSA",
    "PORT",
    "DIV",
    "NSA",
}
GEOFIPS_FIPS_RE = re.compile(r"^\d{2,5}$")


def _normalize_geofips(value: str | int | list[str | int]) -> str:
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
    else:
        parts = [p.strip() for p in str(value).split(",") if p.strip()]
    if not parts:
        raise ValueError("geo_fips cannot be empty")
    out: list[str] = []
    for p in parts:
        up = p.upper()
        if up in GEOFIPS_SPECIALS:
            out.append(up)
        elif GEOFIPS_FIPS_RE.match(p):
            out.append(p)
        else:
            raise ValueError(
                f"invalid GeoFips {p!r}: expected 2-5 digit FIPS code, a "
                f"comma-list of FIPS codes, or one of {sorted(GEOFIPS_SPECIALS)}."
            )
    return ",".join(out)


GeoFips = Annotated[
    str,
    BeforeValidator(_normalize_geofips),
    Field(
        description=(
            "Geographic identifier: 2-5 digit FIPS code (e.g. 06000 for "
            "California, 01001 for Autauga County, AL), a comma-list of "
            "FIPS codes, or a token like STATE/COUNTY/MSA/CSA."
        )
    ),
]
