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

# Back-compat re-exports: POPULAR_SERIES used to live here. It now lives in
# bls_mcp.catalog.popular; we re-export so callers (and tests) don't break.
from .catalog.popular import POPULAR_SERIES  # noqa: F401
from .catalog.surveys import Survey  # noqa: F401

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
