"""BLS post-fetch analytics: panel alignment, transforms, deflation.

Pure pandas helpers + MCP tool wrappers that fetch via the existing
primitives and apply econometric transforms.
"""

from __future__ import annotations

import math
from typing import Annotated, Any, Literal

import pandas as pd
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..models import (
    OutputMode,
    ResponseFormat,
    SeriesID,
    SeriesIDList,
)
from ..transform import reshape_series
from ._common import (
    READ_ONLY,
    render_large_result,
    render_small_result,
    wrap_error,
)
from .series import _fetch_all_series


# ---------------------------------------------------------------------------
# Pure helpers (no HTTP, no MCP) — easy to unit-test.
# ---------------------------------------------------------------------------


def reshaped_to_long(reshaped: list[dict[str, Any]]) -> pd.DataFrame:
    """Flatten a list of reshape_series outputs into a long-form DataFrame."""
    rows: list[dict[str, Any]] = []
    for series in reshaped:
        sid = series.get("series_id")
        for obs in series.get("observations") or []:
            rows.append({
                "series_id": sid,
                "date": obs.get("date"),
                "value": obs.get("value"),
            })
    if not rows:
        return pd.DataFrame(columns=["series_id", "date", "value"])
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["series_id", "date"]).reset_index(drop=True)


def pivot_to_panel(long_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot long-form (series_id, date, value) into a date-indexed wide frame."""
    if long_df.empty:
        return pd.DataFrame()
    wide = long_df.pivot(index="date", columns="series_id", values="value")
    wide.columns.name = None
    return wide.sort_index()


def yoy(df: pd.DataFrame, periods: int = 12) -> pd.DataFrame:
    """Year-on-year percent change at the given lag (default 12 months)."""
    return df.pct_change(periods=periods) * 100.0


def mom_annualized(df: pd.DataFrame) -> pd.DataFrame:
    """Month-on-month change annualized as a percent.

    ``((value_t / value_{t-1}) ** 12 - 1) * 100`` — the standard inflation
    'MoM at annual rate' presentation.
    """
    growth = df / df.shift(1)
    return (growth ** 12 - 1.0) * 100.0


def log_diff(df: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    """100 * (log(x_t) - log(x_{t-periods})) — continuous-time growth rate."""
    logged = df.where(df > 0).apply(lambda s: s.map(lambda v: math.log(v) if pd.notna(v) and v > 0 else None))
    return (logged - logged.shift(periods)) * 100.0


def index_to_base(df: pd.DataFrame, base_period: str | None = None) -> pd.DataFrame:
    """Rebase each column so the value at ``base_period`` (or the first non-NaN row) equals 100.

    ``base_period`` is an ISO date string. If unset, uses the first row per
    column that has a non-null value.
    """
    out = df.copy()
    for col in out.columns:
        col_series = out[col]
        if base_period is not None:
            base_dt = pd.to_datetime(base_period)
            if base_dt in col_series.index:
                base_val = col_series.loc[base_dt]
            else:
                # Snap to the nearest date <= base_period that has a value.
                eligible = col_series.loc[col_series.index <= base_dt].dropna()
                base_val = eligible.iloc[-1] if not eligible.empty else None
        else:
            non_null = col_series.dropna()
            base_val = non_null.iloc[0] if not non_null.empty else None
        if base_val is None or not isinstance(base_val, (int, float)) or base_val == 0:
            continue
        out[col] = col_series / base_val * 100.0
    return out


def deflate(
    nominal: pd.Series, deflator: pd.Series, *, base_period: str | None = None
) -> pd.DataFrame:
    """Real = nominal / (deflator / deflator_at_base) * 100.

    Returns a DataFrame with ``nominal``, ``deflator``, ``real``,
    ``real_yoy_pct``, ``nominal_yoy_pct``. Both inputs should be
    date-indexed Series; they're aligned on their shared index.
    """
    df = pd.concat({"nominal": nominal, "deflator": deflator}, axis=1).sort_index()
    if base_period is not None:
        base_dt = pd.to_datetime(base_period)
        eligible = df.loc[df.index <= base_dt, "deflator"].dropna()
        base_val = eligible.iloc[-1] if not eligible.empty else df["deflator"].dropna().iloc[0]
    else:
        non_null = df["deflator"].dropna()
        base_val = non_null.iloc[0] if not non_null.empty else None
    if base_val is None or base_val == 0:
        df["real"] = pd.NA
    else:
        df["real"] = df["nominal"] / (df["deflator"] / base_val)
    df["nominal_yoy_pct"] = df["nominal"].pct_change(periods=12) * 100.0
    df["real_yoy_pct"] = df["real"].pct_change(periods=12) * 100.0
    return df


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


TransformKind = Literal[
    "yoy", "mom", "mom_annualized", "log_diff", "level", "index"
]


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="bls_compose_panel",
        annotations=READ_ONLY,
        description=(
            "Fetch multiple BLS series and return them as a date-aligned "
            "panel (wide DataFrame: rows = dates, columns = series IDs). "
            "Use mode='summary' (default) to write CSV+Parquet to "
            "$BLS_OUTPUT_DIR and return a digest; 'inline' to return rows "
            "directly (capped). Use this whenever you want to compare or "
            "regress series against each other."
        ),
    )
    async def bls_compose_panel(
        series_ids: Annotated[
            SeriesIDList,
            Field(description="BLS series IDs (list or comma-separated)."),
        ],
        start_year: Annotated[
            int | None,
            Field(default=None, ge=1900, le=2100, description="Earliest year (YYYY)."),
        ] = None,
        end_year: Annotated[
            int | None,
            Field(default=None, ge=1900, le=2100, description="Latest year (YYYY)."),
        ] = None,
        include_calculations: Annotated[
            bool,
            Field(description="If true, BLS calculations are fetched (kept in metadata)."),
        ] = False,
        mode: Annotated[
            OutputMode,
            Field(description="summary (default — writes CSV+Parquet) or inline."),
        ] = OutputMode.summary,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            raw = await _fetch_all_series(
                series_ids,
                start_year=start_year,
                end_year=end_year,
                include_calculations=include_calculations,
                include_annual_average=False,
                include_catalog=False,
            )
            reshaped = [reshape_series(s, expose_metadata=False) for s in raw]
            long_df = reshaped_to_long(reshaped)
            wide = pivot_to_panel(long_df)
            # Convert to row-records suitable for the dataset writer.
            wide_reset = wide.reset_index()
            wide_reset["date"] = wide_reset["date"].dt.strftime("%Y-%m-%d")
            rows = wide_reset.to_dict(orient="records")
            fname = f"bls_panel_{'_'.join(series_ids)[:60]}"
            return render_large_result(
                rows,
                name=fname,
                mode=mode,
                fmt=response_format,
                title=f"BLS panel ({len(series_ids)} series, {len(rows)} dates)",
                what=", ".join(series_ids),
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bls_transform_series",
        annotations=READ_ONLY,
        description=(
            "Apply a common econometric transform to a single BLS series. "
            "Transforms: yoy (12-period % change), mom (1-period % change), "
            "mom_annualized (1-period % at annual rate), log_diff (continuous "
            "growth), level (raw values), index (rebase to 100 at "
            "base_period). Returns [{date, value, transformed}]."
        ),
    )
    async def bls_transform_series(
        series_id: Annotated[
            SeriesID,
            Field(description="A single BLS series ID."),
        ],
        transform: Annotated[
            TransformKind,
            Field(description="One of: yoy, mom, mom_annualized, log_diff, level, index."),
        ],
        start_year: Annotated[
            int | None,
            Field(default=None, ge=1900, le=2100),
        ] = None,
        end_year: Annotated[
            int | None,
            Field(default=None, ge=1900, le=2100),
        ] = None,
        base_period: Annotated[
            str | None,
            Field(
                default=None,
                description="ISO date for the 'index' transform; the value at this date is set to 100.",
            ),
        ] = None,
        mode: Annotated[
            OutputMode,
            Field(description="inline (default) or summary."),
        ] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            raw = await _fetch_all_series(
                [series_id],
                start_year=start_year,
                end_year=end_year,
                include_calculations=False,
                include_annual_average=False,
                include_catalog=False,
            )
            reshaped = [reshape_series(s, expose_metadata=False) for s in raw]
            long_df = reshaped_to_long(reshaped)
            if long_df.empty:
                return render_small_result(
                    [], response_format,
                    title=f"Transform {transform}: {series_id}",
                    what=series_id,
                )
            wide = pivot_to_panel(long_df)
            if transform == "yoy":
                tdf = yoy(wide, periods=12)
            elif transform == "mom":
                tdf = wide.pct_change(periods=1) * 100.0
            elif transform == "mom_annualized":
                tdf = mom_annualized(wide)
            elif transform == "log_diff":
                tdf = log_diff(wide, periods=1)
            elif transform == "level":
                tdf = wide
            elif transform == "index":
                tdf = index_to_base(wide, base_period=base_period)
            else:
                raise ValueError(f"unknown transform: {transform!r}")

            merged = wide.join(tdf, lsuffix="_value", rsuffix="_transformed")
            merged = merged.reset_index()
            rows: list[dict[str, Any]] = []
            for _, r in merged.iterrows():
                rows.append({
                    "date": r["date"].strftime("%Y-%m-%d"),
                    "value": (
                        float(r[f"{series_id}_value"])
                        if pd.notna(r[f"{series_id}_value"]) else None
                    ),
                    "transformed": (
                        float(r[f"{series_id}_transformed"])
                        if pd.notna(r[f"{series_id}_transformed"]) else None
                    ),
                })
            return render_large_result(
                rows,
                name=f"bls_transform_{series_id}_{transform}",
                mode=mode,
                fmt=response_format,
                title=f"{series_id} — {transform} ({len(rows)} rows)",
                what=series_id,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bls_deflate_series",
        annotations=READ_ONLY,
        description=(
            "Compute real (CPI-deflated) values for a nominal BLS series. "
            "Defaults: deflator = CUSR0000SA0 (CPI-U All items, SA). Returns "
            "[{date, nominal, deflator, real, nominal_yoy_pct, real_yoy_pct}]. "
            "Use base_period to anchor the deflator ratio at a specific date."
        ),
    )
    async def bls_deflate_series(
        nominal_series_id: Annotated[
            SeriesID,
            Field(description="The nominal series to deflate (e.g. CES0500000003 AHE)."),
        ],
        deflator_series_id: Annotated[
            SeriesID,
            Field(description="The price index to deflate by (defaults to headline CPI SA)."),
        ] = "CUSR0000SA0",
        start_year: Annotated[
            int | None,
            Field(default=None, ge=1900, le=2100),
        ] = None,
        end_year: Annotated[
            int | None,
            Field(default=None, ge=1900, le=2100),
        ] = None,
        base_period: Annotated[
            str | None,
            Field(
                default=None,
                description="ISO date for the deflator base. Defaults to the first overlapping observation.",
            ),
        ] = None,
        mode: Annotated[
            OutputMode,
            Field(description="inline (default) or summary."),
        ] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            raw = await _fetch_all_series(
                [nominal_series_id, deflator_series_id],
                start_year=start_year,
                end_year=end_year,
                include_calculations=False,
                include_annual_average=False,
                include_catalog=False,
            )
            reshaped = [reshape_series(s, expose_metadata=False) for s in raw]
            long_df = reshaped_to_long(reshaped)
            wide = pivot_to_panel(long_df)
            if nominal_series_id not in wide.columns or deflator_series_id not in wide.columns:
                raise ValueError(
                    "BLS did not return data for one of the requested series; "
                    "check series IDs and date range."
                )
            df = deflate(
                wide[nominal_series_id],
                wide[deflator_series_id],
                base_period=base_period,
            )
            df_reset = df.reset_index()
            df_reset["date"] = df_reset["date"].dt.strftime("%Y-%m-%d")
            rows = df_reset.to_dict(orient="records")
            # Convert NaN -> None for clean JSON.
            for r in rows:
                for k, v in list(r.items()):
                    if isinstance(v, float) and pd.isna(v):
                        r[k] = None
            return render_large_result(
                rows,
                name=f"bls_deflate_{nominal_series_id}_{deflator_series_id}",
                mode=mode,
                fmt=response_format,
                title=f"Real {nominal_series_id} (deflated by {deflator_series_id})",
                what=nominal_series_id,
            )
        except Exception as exc:
            return wrap_error(exc)
