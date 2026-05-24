"""Curated composite BLS dashboards.

These tools compose the primitives in ``series.py`` and ``analytics.py`` to
return a single payload tailored to a common macro question. Each tool
makes exactly one v2 HTTP call.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

import pandas as pd
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..models import ResponseFormat
from ..transform import reshape_series
from ._common import READ_ONLY, render_small_result, wrap_error
from .analytics import (
    deflate,
    mom_annualized,
    pivot_to_panel,
    reshaped_to_long,
    yoy,
)
from .series import _fetch_all_series

# ---------------------------------------------------------------------------
# Series IDs used by the composites
# ---------------------------------------------------------------------------

INFLATION_SA = {
    "headline":             "CUSR0000SA0",
    "core":                 "CUSR0000SA0L1E",
    "food":                 "CUSR0000SAF1",
    "energy":               "CUSR0000SA0E",
    "shelter":              "CUSR0000SAH1",
    "services_less_energy": "CUSR0000SASLE",
}

INFLATION_NSA = {
    "headline":             "CUUR0000SA0",
    "core":                 "CUUR0000SA0L1E",
    "food":                 "CUUR0000SAF1",
    "energy":               "CUUR0000SA0E",
    "shelter":              "CUUR0000SAH1",
    "services_less_energy": "CUUR0000SASLE",
}

LABOR_SERIES = {
    "u3_unemployment_rate": "LNS14000000",
    "u6_unemployment_rate": "LNS13327709",
    "labor_force_participation_rate": "LNS11300000",
    "employment_population_ratio":    "LNS12300000",
    "nonfarm_payrolls":               "CES0000000001",
    "average_hourly_earnings":        "CES0500000003",
    "average_weekly_hours":           "CES0500000002",
}

JOLTS_SERIES = {
    "job_openings_rate": "JTS000000000000000JOR",
    "quits_rate":        "JTS000000000000000QUR",
}


def _start_year_for_lookback(months_back: int) -> int:
    """Pick a start year that comfortably covers the requested lookback.

    We pad with two extra years so YoY (12-month lag) calculations have
    enough history to populate the requested window.
    """
    today = pd.Timestamp.today()
    return int(today.year) - max(2, (months_back // 12) + 2)


def _tail(df: pd.DataFrame, months_back: int) -> pd.DataFrame:
    return df.tail(months_back)


def _series_summary(
    name: str,
    series_id: str,
    values: pd.Series,
    yoy_series: pd.Series,
    mom_ann: pd.Series,
    months_back: int,
) -> dict[str, Any]:
    history_idx = values.tail(months_back).index
    return {
        "name": name,
        "series_id": series_id,
        "latest_date": (
            values.dropna().index[-1].strftime("%Y-%m-%d")
            if not values.dropna().empty else None
        ),
        "latest_value": (
            float(values.dropna().iloc[-1])
            if not values.dropna().empty else None
        ),
        "yoy_pct": (
            float(yoy_series.dropna().iloc[-1])
            if not yoy_series.dropna().empty else None
        ),
        "mom_annualized_pct": (
            float(mom_ann.dropna().iloc[-1])
            if not mom_ann.dropna().empty else None
        ),
        "history": [
            {
                "date": d.strftime("%Y-%m-%d"),
                "value": (float(values.loc[d]) if pd.notna(values.loc[d]) else None),
                "yoy_pct": (
                    float(yoy_series.loc[d]) if d in yoy_series.index and pd.notna(yoy_series.loc[d])
                    else None
                ),
                "mom_annualized_pct": (
                    float(mom_ann.loc[d]) if d in mom_ann.index and pd.notna(mom_ann.loc[d])
                    else None
                ),
            }
            for d in history_idx
        ],
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="bls_inflation_snapshot",
        annotations=READ_ONLY,
        description=(
            "One-call inflation dashboard: headline CPI, core CPI, food, "
            "energy, shelter, and services-less-energy. For each component "
            "returns latest value, latest 12-month %, latest MoM annualized "
            "%, and a history window. Uses seasonally-adjusted CPI by "
            "default. Returns a structured dict — easy for a model to "
            "narrate."
        ),
    )
    async def bls_inflation_snapshot(
        months_back: Annotated[
            int,
            Field(default=12, ge=1, le=120, description="Length of history window per component."),
        ] = 12,
        seasonal: Annotated[
            Literal["SA", "NSA"],
            Field(default="SA", description="'SA' (default — clean MoM) or 'NSA'."),
        ] = "SA",
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            series_map = INFLATION_SA if seasonal == "SA" else INFLATION_NSA
            series_ids = list(series_map.values())
            raw = await _fetch_all_series(
                series_ids,
                start_year=_start_year_for_lookback(months_back),
                end_year=None,
                include_calculations=False,
                include_annual_average=False,
                include_catalog=False,
            )
            reshaped = [reshape_series(s, expose_metadata=False) for s in raw]
            wide = pivot_to_panel(reshaped_to_long(reshaped))
            yoy_df = yoy(wide, periods=12)
            mom_ann_df = mom_annualized(wide)

            payload: dict[str, Any] = {
                "as_of": (
                    wide.dropna(how="all").index[-1].strftime("%Y-%m-%d")
                    if not wide.empty else None
                ),
                "seasonal": seasonal,
                "components": {},
            }
            for name, sid in series_map.items():
                if sid not in wide.columns:
                    continue
                payload["components"][name] = _series_summary(
                    name, sid, wide[sid], yoy_df[sid], mom_ann_df[sid], months_back
                )
            return render_small_result(
                payload,
                response_format,
                title="BLS inflation snapshot",
                what="inflation",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bls_labor_market_snapshot",
        annotations=READ_ONLY,
        description=(
            "One-call labor-market dashboard: U-3, U-6, LFPR, employment-"
            "population ratio, nonfarm payrolls, AHE, AWH, and optional "
            "JOLTS openings/quits rates. Returns latest readings, 1-month "
            "change, 12-month change, plus a 3-month average change in "
            "nonfarm payrolls (a common trend gauge)."
        ),
    )
    async def bls_labor_market_snapshot(
        months_back: Annotated[
            int,
            Field(default=12, ge=1, le=120),
        ] = 12,
        include_jolts: Annotated[
            bool,
            Field(default=True, description="Include JOLTS openings + quits rates."),
        ] = True,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            series_map = dict(LABOR_SERIES)
            if include_jolts:
                series_map.update(JOLTS_SERIES)
            series_ids = list(series_map.values())
            raw = await _fetch_all_series(
                series_ids,
                start_year=_start_year_for_lookback(months_back),
                end_year=None,
                include_calculations=False,
                include_annual_average=False,
                include_catalog=False,
            )
            reshaped = [reshape_series(s, expose_metadata=False) for s in raw]
            wide = pivot_to_panel(reshaped_to_long(reshaped))
            yoy_df = yoy(wide, periods=12)
            mom_df = wide.pct_change(periods=1) * 100.0

            components: dict[str, Any] = {}
            for name, sid in series_map.items():
                if sid not in wide.columns:
                    continue
                s = wide[sid]
                m = mom_df[sid]
                y = yoy_df[sid]
                # For payrolls, also report level changes (not just pct).
                level_diff = s.diff()
                components[name] = {
                    "name": name,
                    "series_id": sid,
                    "latest_date": (
                        s.dropna().index[-1].strftime("%Y-%m-%d") if not s.dropna().empty else None
                    ),
                    "latest_value": (
                        float(s.dropna().iloc[-1]) if not s.dropna().empty else None
                    ),
                    "change_1m": (
                        float(level_diff.dropna().iloc[-1])
                        if not level_diff.dropna().empty else None
                    ),
                    "pct_change_1m": (
                        float(m.dropna().iloc[-1]) if not m.dropna().empty else None
                    ),
                    "pct_change_12m": (
                        float(y.dropna().iloc[-1]) if not y.dropna().empty else None
                    ),
                    "history": [
                        {
                            "date": d.strftime("%Y-%m-%d"),
                            "value": (float(s.loc[d]) if pd.notna(s.loc[d]) else None),
                            "change_1m": (
                                float(level_diff.loc[d])
                                if d in level_diff.index and pd.notna(level_diff.loc[d])
                                else None
                            ),
                        }
                        for d in s.tail(months_back).index
                    ],
                }

            # Extra: payrolls 3m avg level change.
            payrolls = wide.get(LABOR_SERIES["nonfarm_payrolls"])
            if payrolls is not None:
                payrolls_diff = payrolls.diff().tail(3)
                payrolls_3m = float(payrolls_diff.mean()) if not payrolls_diff.empty else None
            else:
                payrolls_3m = None

            payload = {
                "as_of": (
                    wide.dropna(how="all").index[-1].strftime("%Y-%m-%d")
                    if not wide.empty else None
                ),
                "payrolls_3m_avg_change": payrolls_3m,
                "components": components,
            }
            return render_small_result(
                payload,
                response_format,
                title="BLS labor market snapshot",
                what="labor market",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bls_real_wages",
        annotations=READ_ONLY,
        description=(
            "Real (CPI-deflated) wage growth. Defaults: nominal = "
            "CES0500000003 (AHE, all employees, total private, SA); "
            "deflator = CUSR0000SA0 (CPI-U All items, SA). Returns a "
            "history of {date, nominal_wage, cpi, real_wage_index, "
            "nominal_yoy_pct, real_yoy_pct}. The real_wage_index is "
            "rebased so it starts at 100 at the earliest date in the "
            "lookback window."
        ),
    )
    async def bls_real_wages(
        months_back: Annotated[
            int,
            Field(default=24, ge=1, le=240),
        ] = 24,
        wage_series_id: Annotated[
            str,
            Field(default="CES0500000003", description="Nominal wage series."),
        ] = "CES0500000003",
        cpi_series_id: Annotated[
            str,
            Field(default="CUSR0000SA0", description="CPI deflator series."),
        ] = "CUSR0000SA0",
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            raw = await _fetch_all_series(
                [wage_series_id, cpi_series_id],
                start_year=_start_year_for_lookback(months_back),
                end_year=None,
                include_calculations=False,
                include_annual_average=False,
                include_catalog=False,
            )
            reshaped = [reshape_series(s, expose_metadata=False) for s in raw]
            wide = pivot_to_panel(reshaped_to_long(reshaped))
            if wage_series_id not in wide.columns or cpi_series_id not in wide.columns:
                raise ValueError(
                    "BLS did not return data for one of the requested series; "
                    "check series IDs."
                )
            # Trim to the overlap so the index starts at 100 at the first row.
            overlap = wide[[wage_series_id, cpi_series_id]].dropna()
            if overlap.empty:
                raise ValueError("No overlapping observations between wage and CPI series.")
            tail = overlap.tail(months_back + 12)  # extra 12 rows so YoY has history
            df = deflate(
                tail[wage_series_id],
                tail[cpi_series_id],
                base_period=tail.index[0].strftime("%Y-%m-%d"),
            )
            df["real_wage_index"] = df["real"] / df["real"].dropna().iloc[0] * 100.0
            df = df.tail(months_back)
            df_reset = df.reset_index()
            df_reset["date"] = df_reset["date"].dt.strftime("%Y-%m-%d")
            rows: list[dict[str, Any]] = []
            for _, r in df_reset.iterrows():
                rows.append({
                    "date": r["date"],
                    "nominal_wage": (float(r["nominal"]) if pd.notna(r["nominal"]) else None),
                    "cpi": (float(r["deflator"]) if pd.notna(r["deflator"]) else None),
                    "real_wage_index": (
                        float(r["real_wage_index"]) if pd.notna(r["real_wage_index"]) else None
                    ),
                    "nominal_yoy_pct": (
                        float(r["nominal_yoy_pct"]) if pd.notna(r["nominal_yoy_pct"]) else None
                    ),
                    "real_yoy_pct": (
                        float(r["real_yoy_pct"]) if pd.notna(r["real_yoy_pct"]) else None
                    ),
                })
            payload = {
                "wage_series_id": wage_series_id,
                "cpi_series_id": cpi_series_id,
                "as_of": rows[-1]["date"] if rows else None,
                "latest_real_yoy_pct": rows[-1]["real_yoy_pct"] if rows else None,
                "latest_nominal_yoy_pct": rows[-1]["nominal_yoy_pct"] if rows else None,
                "history": rows,
            }
            return render_small_result(
                payload,
                response_format,
                title="Real wage growth",
                what="real wages",
            )
        except Exception as exc:
            return wrap_error(exc)
