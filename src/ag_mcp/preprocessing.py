"""Returns preprocessing and CSV-shaping helpers.

The C++ engine fits ARIMA-GARCH models on (approximately) stationary
series. This module owns the conversion from a raw price CSV (FMP) or a
raw level/index series (BLS/BEA) into the single-column CSV that
``ag fit -d`` expects.

Conventions baked in here:

* **Log returns by default** for prices: ``ln(p_t / p_{t-1})``. They're
  symmetric, additive across time, and the standard input for GARCH
  modelling. ``simple`` (``(p_t - p_{t-1}) / p_{t-1}``) is offered as an
  alternative; ``none`` is a pass-through for already-stationary series
  like BLS YoY series or BEA growth rates.
* **Output column name** is ``return`` for log/simple, ``value`` for none.
  Either way the CSV has exactly one column header on the first line so
  ``ag fit -d`` reads it cleanly.
* **Date column** is preserved on input but stripped on output (the
  engine doesn't care about timestamps).
* **Annualization factor** is inferred from observed date cadence when
  the caller doesn't supply one (daily=252, weekly=52, monthly=12,
  quarterly=4, annual=1).

All stats (mean, stdev, skewness, kurtosis, etc.) are computed via
pandas for numerical stability.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from .errors import AGError
from .models import Frequency, annualization_factor_for


# ---------- result type ---------------------------------------------------


@dataclass
class ReturnsMetadata:
    """Returned by :func:`prices_to_returns` and :func:`series_to_returns`.

    Holds the path to the written CSV and a quant-readable summary of the
    derived series (range, sample stats, inferred cadence).
    """

    returns_csv_path: str
    input_rows: int
    output_rows: int
    return_type: str
    value_column: str
    date_range: dict[str, str | None]
    frequency: str
    annualization_factor: int | None
    summary_stats: dict[str, float | None]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------- price -> returns ---------------------------------------------


def prices_to_returns(
    prices_csv: Path,
    *,
    output_csv: Path,
    return_type: Literal["log", "simple", "none"] = "log",
    price_column: str = "close",
    date_column: str | None = "date",
    annualization_factor: int | None = None,
) -> ReturnsMetadata:
    """Convert a prices CSV into a one-column returns CSV usable by `ag fit`.

    - ``log``    → ``ln(p_t / p_{t-1})``
    - ``simple`` → ``(p_t - p_{t-1}) / p_{t-1}``
    - ``none``   → pass ``price_column`` through unchanged. Use this when
      the input is already a stationary series (e.g. BLS YoY series).
    """
    df = _read_csv(prices_csv)
    if price_column not in df.columns:
        # Forgiving fallback: try the most common alternatives.
        for alt in ("close", "adjClose", "adj_close", "Close", "price", "value"):
            if alt in df.columns:
                price_column = alt
                break
        else:
            raise AGError(
                f"price column {price_column!r} not found in {prices_csv}. "
                f"Available columns: {list(df.columns)!r}."
            )

    if date_column and date_column in df.columns:
        df = df.sort_values(date_column).reset_index(drop=True)

    prices = pd.to_numeric(df[price_column], errors="coerce")
    if prices.dropna().empty:
        raise AGError(
            f"price column {price_column!r} contains no numeric values in {prices_csv}."
        )

    series, value_col = _compute_series(prices, return_type)
    series = series.dropna()
    if series.empty:
        raise AGError(
            f"{return_type} returns produced an empty series. "
            "Need at least 2 valid price observations."
        )

    _write_single_column_csv(output_csv, series, value_col)

    freq = _infer_frequency(df.get(date_column) if date_column else None)
    af = annualization_factor or annualization_factor_for(freq)

    return ReturnsMetadata(
        returns_csv_path=str(output_csv),
        input_rows=int(len(df)),
        output_rows=int(len(series)),
        return_type=return_type,
        value_column=value_col,
        date_range=_date_range(df.get(date_column) if date_column else None),
        frequency=freq.value,
        annualization_factor=af,
        summary_stats=_summary_stats(series, annualization_factor=af),
    )


# ---------- single-series helpers (BLS/BEA / pre-stationary input) -------


def series_to_returns(
    values: list[dict[str, Any]] | list[float],
    *,
    output_csv: Path,
    return_type: Literal["log", "simple", "none"] = "none",
    value_key: str = "value",
    date_key: str | None = "date",
    annualization_factor: int | None = None,
) -> ReturnsMetadata:
    """Persist a BLS/BEA-style series into the returns CSV format.

    Accepts either ``[{date, value, ...}, ...]`` or a bare list of floats.
    With ``return_type="none"`` (the default for macro series) the values
    are passed through; otherwise log/simple returns are computed off them
    as if they were prices.
    """
    if not values:
        raise AGError("series_to_returns received an empty values list.")

    if isinstance(values[0], dict):
        df = pd.DataFrame(values)
        if value_key not in df.columns:
            raise AGError(
                f"value key {value_key!r} not found in series. "
                f"Available keys: {list(df.columns)!r}."
            )
        if date_key and date_key in df.columns:
            df = df.sort_values(date_key).reset_index(drop=True)
        numeric = pd.to_numeric(df[value_key], errors="coerce")
        date_series = df.get(date_key) if date_key else None
    else:
        df = pd.DataFrame({value_key: values})
        numeric = pd.to_numeric(df[value_key], errors="coerce")
        date_series = None

    series, value_col = _compute_series(numeric, return_type)
    series = series.dropna()
    if series.empty:
        raise AGError(
            f"{return_type} transform produced an empty series. "
            "Need at least 2 valid observations."
        )
    _write_single_column_csv(output_csv, series, value_col)
    freq = _infer_frequency(date_series)
    af = annualization_factor or annualization_factor_for(freq)
    return ReturnsMetadata(
        returns_csv_path=str(output_csv),
        input_rows=int(len(df)),
        output_rows=int(len(series)),
        return_type=return_type,
        value_column=value_col,
        date_range=_date_range(date_series),
        frequency=freq.value,
        annualization_factor=af,
        summary_stats=_summary_stats(series, annualization_factor=af),
    )


def write_series_csv(
    values: list[float] | list[dict[str, Any]],
    output_csv: Path,
    *,
    value_key: str = "value",
) -> Path:
    """Persist ``values`` as a single-column CSV (``value`` header).

    Convenience for direct ``[{date, value}]`` lists from BLS/BEA tools.
    No transformation is applied — callers needing log/simple returns
    should call :func:`series_to_returns` instead.
    """
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    if not values:
        raise AGError("write_series_csv received an empty values list.")
    if isinstance(values[0], dict):
        df = pd.DataFrame(values)
        if value_key not in df.columns:
            raise AGError(
                f"value key {value_key!r} not found in series. "
                f"Available keys: {list(df.columns)!r}."
            )
        series = pd.to_numeric(df[value_key], errors="coerce").dropna()
    else:
        series = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    _write_single_column_csv(output_csv, series, "value")
    return output_csv


# ---------- internals ----------------------------------------------------


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001 — pandas can raise many things
        raise AGError(f"Could not read CSV at {path}: {exc}") from exc


def _compute_series(
    prices: pd.Series, return_type: str
) -> tuple[pd.Series, str]:
    import numpy as np

    if return_type == "log":
        series = np.log(prices / prices.shift(1))
        return series, "return"
    if return_type == "simple":
        series = (prices - prices.shift(1)) / prices.shift(1)
        return series, "return"
    if return_type == "none":
        return prices, "value"
    raise AGError(
        f"return_type must be one of log/simple/none; got {return_type!r}."
    )


def _write_single_column_csv(
    output_csv: Path, series: pd.Series, value_col: str
) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    series.to_frame(name=value_col).to_csv(output_csv, index=False)


def _date_range(date_series: pd.Series | None) -> dict[str, str | None]:
    if date_series is None or len(date_series) == 0:
        return {"start": None, "end": None}
    dates = pd.to_datetime(date_series, errors="coerce").dropna()
    if dates.empty:
        return {"start": None, "end": None}
    return {"start": str(dates.min().date()), "end": str(dates.max().date())}


def _infer_frequency(date_series: pd.Series | None) -> Frequency:
    """Heuristic cadence detection from the median spacing of valid dates."""
    if date_series is None or len(date_series) < 2:
        return Frequency.unknown
    dates = pd.to_datetime(date_series, errors="coerce").dropna().sort_values()
    if len(dates) < 2:
        return Frequency.unknown
    median_days = (dates.diff().dropna().dt.days.median()) or 0
    if median_days <= 0:
        return Frequency.unknown
    if median_days <= 4:
        return Frequency.daily
    if median_days <= 10:
        return Frequency.weekly
    if median_days <= 45:
        return Frequency.monthly
    if median_days <= 120:
        return Frequency.quarterly
    return Frequency.annual


def _summary_stats(
    series: pd.Series, *, annualization_factor: int | None
) -> dict[str, float | None]:
    """Compute the stats every composite tool needs at a glance."""
    s = series.astype(float)
    mean = float(s.mean()) if len(s) else None
    stdev = float(s.std(ddof=1)) if len(s) > 1 else None
    skew = float(s.skew()) if len(s) > 2 else None
    kurt = float(s.kurtosis()) if len(s) > 3 else None  # pandas returns excess kurtosis
    annualized = (
        stdev * (annualization_factor ** 0.5)
        if stdev is not None and annualization_factor
        else None
    )
    return {
        "mean": mean,
        "stdev": stdev,
        "annualized_stdev": annualized,
        "skewness": skew,
        "excess_kurtosis": kurt,
        "min": float(s.min()) if len(s) else None,
        "max": float(s.max()) if len(s) else None,
    }
