"""PO-specific Pydantic models and enums.

Generic types (response format, output mode) are re-exported from
:mod:`turningbull_mcp.models` so tool modules can pull everything from a
single import.

Key types
---------

``DataInput`` is a discriminated union (``kind: "inline" | "path"``):

- ``AssetDataInline``: full assets.json-shaped payload (assets, covariance,
  optional market/benchmark weights, risk-free rate). Materialized to
  ``$PO_OUTPUT_DIR/tmp/data_<hash>.json`` before the `po` CLI is invoked.
  Identical payloads dedup by content hash.
- ``DataPathInput``: absolute path to an existing JSON/CSV on disk.

``OptimizationParams`` and ``BlackLittermanParams`` map 1:1 onto the
fields the `po` CLI reads from its params JSON. They serialize via
:func:`materialize_params` into ``$PO_OUTPUT_DIR/params/<hash>.json``.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from turningbull_mcp.models import (  # noqa: F401  (re-exports)
    OptionalDate,
    OutputMode,
    RequiredDate,
    ResponseFormat,
)

from .output import content_hash, params_dir, tmp_dir


# ---------- enums ---------------------------------------------------------


class Shrinkage(str, Enum):
    """Covariance shrinkage estimator for ``--returns`` mode."""

    none = "none"
    linear = "linear"
    ledoit_wolf = "ledoit-wolf"
    oas = "oas"


class OutputFormat(str, Enum):
    """`po` ``-f`` value. JSON is the connector default for single
    portfolios; CSV is used for frontiers."""

    console = "console"
    json = "json"
    csv = "csv"


class ConstructionMethod(str, Enum):
    """Methods understood by :func:`po_construct_portfolio` and
    :func:`po_compare_methods`."""

    mvo = "mvo"
    max_sharpe = "max_sharpe"
    min_variance = "min_variance"
    target_vol = "target_vol"
    target_return = "target_return"
    risk_parity = "risk_parity"
    hrp = "hrp"
    equal_weight = "equal_weight"
    inverse_variance = "inverse_variance"
    inverse_volatility = "inverse_volatility"
    max_diversification = "max_diversification"


class AttributionMode(str, Enum):
    brinson_fachler = "brinson_fachler"
    brinson_hood_beebower = "brinson_hood_beebower"


# ---------- path validators ----------------------------------------------


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
    Field(description="Absolute path to an assets.json or returns CSV file."),
]

ReturnsCsvPath = Annotated[
    Path,
    BeforeValidator(_validate_existing_path),
    Field(description="Absolute path to a periodic-returns CSV (rows = periods, columns = tickers)."),
]


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
            "Falls back to a content hash of the inputs if unset."
        ),
    ),
]


# ---------- domain models ------------------------------------------------


class Asset(BaseModel):
    """A single asset entry inside :class:`AssetDataInline`.

    Only ``ticker`` is required by the `po` CLI; the other fields are
    optional metadata it surfaces in the output (sector caps depend on
    ``sector`` when a group constraint references it by name).
    """

    model_config = ConfigDict(extra="allow")

    ticker: str
    name: str | None = None
    expected_return: float | None = None
    market_cap: float | None = None
    sector: str | None = None
    currency: str | None = None


class GroupCap(BaseModel):
    """A linear group constraint on the optimization.

    Either provide ``members`` (a list of tickers) and the connector
    converts them to indicator coefficients, or provide ``coefficients``
    directly for arbitrary linear-combination caps (e.g. factor neutrality).
    """

    description: str | None = None
    members: list[str] | None = None
    coefficients: list[float] | None = None
    lower: float | None = None
    upper: float | None = None


class AssetDataInline(BaseModel):
    """Inline ``assets.json`` payload. Materialized to
    ``$PO_OUTPUT_DIR/tmp/`` before `po` is invoked.
    """

    model_config = ConfigDict(extra="allow")

    kind: Literal["inline"] = "inline"
    assets: list[Asset]
    covariance: list[list[float]]
    market_weights: list[float] | None = None
    benchmark_weights: list[float] | None = None
    risk_free_rate: float | None = None


class DataPathInput(BaseModel):
    """Reference to an existing assets.json (or returns CSV) on disk."""

    kind: Literal["path"] = "path"
    path: Annotated[Path, BeforeValidator(_validate_existing_path)]


DataInput = Annotated[
    AssetDataInline | DataPathInput,
    Field(
        discriminator="kind",
        description=(
            "Either inline assets data (`kind: \"inline\"`) or a path "
            "to an existing JSON/CSV file (`kind: \"path\"`)."
        ),
    ),
]


class OptimizationParams(BaseModel):
    """MVO-style constraints accepted by `po mvo`, `po frontier`, etc.

    All fields are optional and only emitted into the params JSON when set.
    Bounds may be a per-ticker dict, a scalar applied to every asset, or a
    list aligned with the assets list.
    """

    model_config = ConfigDict(extra="allow")

    risk_aversion: float | None = None
    frontier_points: int | None = None
    lower_bounds: dict[str, float] | list[float] | float | None = None
    upper_bounds: dict[str, float] | list[float] | float | None = None
    budget: float | None = None
    current_weights: dict[str, float] | list[float] | None = None
    turnover_penalty: float | None = None
    tracking_error_limit: float | None = None
    gross_exposure_limit: float | None = None
    groups: list[GroupCap] | None = None
    fixed_weights: dict[str, float] | None = None
    forbidden: list[str] | None = None


class View(BaseModel):
    """A single Black-Litterman view.

    ``pick_vector`` is either a per-ticker mapping (preferred — order-
    independent) or a dense list aligned with the assets list. Confidence
    is on a 0..1 scale in Idzorek mode.
    """

    description: str | None = None
    pick_vector: dict[str, float] | list[float]
    expected_return: float
    confidence: float | None = None


class BlackLittermanParams(BaseModel):
    """BL-specific params payload."""

    model_config = ConfigDict(extra="allow")

    tau: float = 0.05
    risk_aversion: float = 2.5
    confidence_mode: Literal["idzorek", "omega-direct"] = "idzorek"
    views: list[View]


# ---------- materialization helpers --------------------------------------


def _canonical_json(payload: Any) -> str:
    """Stable serialization for content hashing.

    Sorts keys and omits whitespace so identical payloads hash identically
    regardless of insertion order.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def materialize_data(data: AssetDataInline | DataPathInput | dict[str, Any]) -> Path:
    """Return a filesystem path to the data, writing a content-addressed
    tmp file if the input is inline.

    Idempotent: identical payloads reuse the same tmp file on subsequent
    calls. Atomic write via a sibling ``.tmp`` rename so concurrent writers
    don't see a half-written file.
    """
    if isinstance(data, DataPathInput):
        return Path(data.path)
    if isinstance(data, dict):
        # Allow plain dicts from tool callers; validate light shape.
        if data.get("kind") == "path":
            return Path(data["path"]).expanduser().resolve()
        payload: dict[str, Any] = {k: v for k, v in data.items() if k != "kind"}
    else:  # AssetDataInline
        payload = data.model_dump(mode="json", exclude={"kind"})
    canonical = _canonical_json(payload)
    fname = f"data_{content_hash(canonical)}.json"
    target = tmp_dir() / fname
    if target.exists():
        return target
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    tmp_path.write_text(canonical, encoding="utf-8")
    tmp_path.replace(target)
    return target


def materialize_params(
    params: OptimizationParams | BlackLittermanParams | dict[str, Any] | None,
    *,
    kind: Literal["mvo", "bl"],
) -> Path | None:
    """Write a params payload to ``$PO_OUTPUT_DIR/params/`` if non-empty.

    ``kind="mvo"`` wraps the payload under a top-level ``"mvo"`` key (which
    is what `po mvo`/`frontier`/`min-variance`/`max-sharpe`/`target-*`
    expect); ``kind="bl"`` wraps it under ``"black_litterman"``.

    Returns ``None`` when ``params`` is ``None`` (the CLI subcommands all
    accept omitting ``-p`` entirely).
    """
    if params is None:
        return None
    if isinstance(params, BaseModel):
        payload = params.model_dump(mode="json", exclude_none=True)
    else:
        payload = {k: v for k, v in params.items() if v is not None}
    if not payload:
        return None
    wrapper_key = "mvo" if kind == "mvo" else "black_litterman"
    wrapped = {wrapper_key: payload}
    canonical = _canonical_json(wrapped)
    fname = f"params_{kind}_{content_hash(canonical)}.json"
    target = params_dir() / fname
    if target.exists():
        return target
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    tmp_path.write_text(canonical, encoding="utf-8")
    tmp_path.replace(target)
    return target
