"""Domain-specific Pydantic types and enums for the FRED connector."""

from __future__ import annotations

from enum import Enum

from turningbull_mcp.models import (  # noqa: F401  re-export for tools
    OptionalDate,
    OutputMode,
    RequiredDate,
    ResponseFormat,
)


class SortOrder(str, Enum):
    """Sort direction for paginated FRED list endpoints."""

    asc = "asc"
    desc = "desc"


class Units(str, Enum):
    """Data value transformation for series observations.

    lin=levels, chg=change, ch1=change from year ago, pch=percent change,
    pc1=percent change from year ago, pca=compounded annual rate of change,
    cch=continuously compounded rate of change, cca=continuously compounded
    annual rate of change, log=natural log.
    """

    lin = "lin"
    chg = "chg"
    ch1 = "ch1"
    pch = "pch"
    pc1 = "pc1"
    pca = "pca"
    cch = "cch"
    cca = "cca"
    log = "log"


class AggregationMethod(str, Enum):
    """Aggregation method used when a lower observation frequency is requested."""

    avg = "avg"
    sum = "sum"
    eop = "eop"
