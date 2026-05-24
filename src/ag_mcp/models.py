"""AG-specific Pydantic models and enums.

Generic types (response format, output mode) are re-exported from
:mod:`turningbull_mcp.models` so tool modules can pull everything from a
single import.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from turningbull_mcp.models import (  # noqa: F401  (re-exports)
    OptionalDate,
    OutputMode,
    RequiredDate,
    ResponseFormat,
)


# ---------- enums ---------------------------------------------------------


class SelectionCriterion(str, Enum):
    """`ag select` criterion. ``CV`` (cross-validation) is slow; default to BIC."""

    BIC = "BIC"
    AIC = "AIC"
    AICc = "AICc"
    CV = "CV"


class InnovationDist(str, Enum):
    """`ag fit` innovation distribution.

    ``gaussian`` is the default but can understate tail risk on real returns;
    when the CLI's report flags Student-t as a better fit, ``ag_fit``
    surfaces that recommendation in the response.
    """

    gaussian = "gaussian"
    student_t = "student_t"


class ReturnType(str, Enum):
    """How ``ag_prepare_returns`` / ``ag_load_series`` derives the series.

    - ``log``    — ln(p_t / p_{t-1}); the analytic default for prices.
    - ``simple`` — (p_t - p_{t-1}) / p_{t-1}.
    - ``none``   — pass through. Use for already-stationary series like
      BLS YoY percent changes or BEA growth rates.
    """

    log = "log"
    simple = "simple"
    none = "none"


class Frequency(str, Enum):
    """Cadence inferred from input dates; drives the annualization factor."""

    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    quarterly = "quarterly"
    annual = "annual"
    unknown = "unknown"


def annualization_factor_for(freq: Frequency) -> int | None:
    """Trading-day annualization factor per :class:`Frequency`."""
    return {
        Frequency.daily: 252,
        Frequency.weekly: 52,
        Frequency.monthly: 12,
        Frequency.quarterly: 4,
        Frequency.annual: 1,
        Frequency.unknown: None,
    }[freq]


# ---------- spec validators ----------------------------------------------


def _validate_arima(value: tuple[int, int, int] | list[int] | str) -> tuple[int, int, int]:
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        raise ValueError(f"arima must be a 3-tuple/list/comma-string, got {type(value).__name__}")
    if len(parts) != 3:
        raise ValueError(f"arima must have 3 elements (p,d,q); got {parts!r}")
    try:
        p, d, q = (int(x) for x in parts)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"arima elements must be integers: {value!r}") from exc
    if p < 0 or d < 0 or q < 0:
        raise ValueError(f"arima orders must be >= 0: ({p},{d},{q})")
    if d > 2:
        raise ValueError(f"arima d must be <= 2; got d={d}")
    return (p, d, q)


def _validate_garch(value: tuple[int, int] | list[int] | str) -> tuple[int, int]:
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        raise ValueError(f"garch must be a 2-tuple/list/comma-string, got {type(value).__name__}")
    if len(parts) != 2:
        raise ValueError(f"garch must have 2 elements (p,q); got {parts!r}")
    try:
        p, q = (int(x) for x in parts)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"garch elements must be integers: {value!r}") from exc
    if p < 0 or q < 0:
        raise ValueError(f"garch orders must be >= 0: ({p},{q})")
    return (p, q)


ArimaOrder = Annotated[
    tuple[int, int, int],
    BeforeValidator(_validate_arima),
    Field(
        description=(
            "ARIMA (p,d,q) order as a 3-element list or comma-string. "
            "Example: [1,0,1] or '1,0,1'."
        )
    ),
]

GarchOrder = Annotated[
    tuple[int, int],
    BeforeValidator(_validate_garch),
    Field(
        description=(
            "GARCH (p,q) order as a 2-element list or comma-string. "
            "Example: [1,1] or '1,1'."
        )
    ),
]


# ---------- path validators ---------------------------------------------


def _validate_existing_path(value: str | Path) -> Path:
    p = Path(str(value)).expanduser()
    if not p.exists():
        raise ValueError(f"path does not exist: {p}")
    if not p.is_file():
        raise ValueError(f"path is not a regular file: {p}")
    return p.resolve()


DataPath = Annotated[
    Path,
    BeforeValidator(_validate_existing_path),
    Field(description="Absolute path to a returns/data CSV usable as `ag fit -d`."),
]

ModelPath = Annotated[
    Path,
    BeforeValidator(_validate_existing_path),
    Field(description="Absolute path to a saved model JSON written by `ag fit`/`ag select`."),
]


SYMBOL_RE = re.compile(r"^[\^A-Za-z0-9.\-]{1,16}$")
SERIES_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{2,40}$")


def _normalize_label(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    keep = "-_.,()^"
    return "".join(c if c.isalnum() or c in keep else "_" for c in s)


Label = Annotated[
    str | None,
    BeforeValidator(_normalize_label),
    Field(
        default=None,
        description=(
            "Optional human-readable stem used in artifact filenames. "
            "Falls back to symbol/series-id or a hash of inputs if unset."
        ),
    ),
]


# Source identifier for ``ag_load_series``.
LoadSeriesSource = Literal["fmp_prices", "bls_series", "bea_series"]
