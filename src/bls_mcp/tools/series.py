"""BLS time series tools.

All four tools wrap the same upstream endpoint
(`/publicAPI/v{1,2}/timeseries/data/`); the BLSClient picks v1 vs v2 based on
whether ``BLS_API_KEY`` is set.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import V2_MAX_SERIES_PER_REQUEST, V2_MAX_YEAR_SPAN, get_client
from ..models import (
    POPULAR_SERIES,
    OutputMode,
    ResponseFormat,
    SeriesID,
    SeriesIDList,
)
from ..transform import (
    CALCULATION_PERIODS,
    filter_calculation_periods,
    reshape_series,
)
from ._common import (
    READ_ONLY,
    render_large_result,
    render_small_result,
    wrap_error,
)


def _chunked(seq: list[str], size: int) -> list[list[str]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def _year_windows(
    start_year: int | None, end_year: int | None, max_span: int
) -> list[tuple[int | None, int | None]]:
    """Split a year range into windows <= ``max_span`` years (inclusive).

    If either bound is unset, returns a single ``(start, end)`` tuple and
    lets the API apply its default depth.
    """
    if start_year is None or end_year is None or end_year - start_year + 1 <= max_span:
        return [(start_year, end_year)]
    windows: list[tuple[int | None, int | None]] = []
    cursor = start_year
    while cursor <= end_year:
        chunk_end = min(cursor + max_span - 1, end_year)
        windows.append((cursor, chunk_end))
        cursor = chunk_end + 1
    return windows


async def _fetch_all_series(
    series_ids: list[str],
    *,
    start_year: int | None,
    end_year: int | None,
    include_calculations: bool,
    include_annual_average: bool,
    include_catalog: bool,
    include_aspects: bool = False,
) -> list[dict[str, Any]]:
    """Run all required chunked fetches and merge into one ``Results.series`` list.

    Chunking happens along two axes: series IDs (50/request for v2) and year
    windows (20/request for v2). Observations from multiple year windows are
    merged on ``seriesID`` so the caller sees one entry per series.
    """
    client = get_client()
    by_id: dict[str, dict[str, Any]] = {}

    id_batches = _chunked(series_ids, V2_MAX_SERIES_PER_REQUEST)
    year_batches = _year_windows(start_year, end_year, V2_MAX_YEAR_SPAN)

    for id_batch in id_batches:
        for sy, ey in year_batches:
            raw = await client.fetch(
                id_batch,
                start_year=sy,
                end_year=ey,
                catalog=include_catalog,
                calculations=include_calculations,
                annual_average=include_annual_average,
                aspects=include_aspects,
            )
            for s in raw:
                sid = s.get("seriesID")
                if not sid:
                    continue
                existing = by_id.get(sid)
                if existing is None:
                    by_id[sid] = {
                        "seriesID": sid,
                        "catalog": s.get("catalog"),
                        "data": list(s.get("data") or []),
                    }
                    continue
                if not existing.get("catalog") and s.get("catalog"):
                    existing["catalog"] = s["catalog"]
                existing["data"].extend(s.get("data") or [])

    # Preserve the caller's input order; backfill any IDs the API didn't return
    # so the caller never sees a silently-dropped series.
    out: list[dict[str, Any]] = []
    for sid in series_ids:
        out.append(by_id.get(sid, {"seriesID": sid, "data": []}))
    return out


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="bls_get_series",
        annotations=READ_ONLY,
        description=(
            "Fetch one or more BLS time series (CPI, unemployment, payrolls, "
            "PPI, productivity, etc.). This is the workhorse tool. Pass series "
            "IDs as a list or a comma-separated string; the server chunks them "
            "into batches of 50 and splits year ranges longer than 20 years. "
            "When BLS_API_KEY is not set the server falls back to v1 (single-"
            "series GETs, 10-year cap, no calculations/catalog).\n\n"
            "Returns a list of "
            "{series_id, title, units, seasonal_adjustment, observations: "
            "[{date, year, period, period_name, value, footnotes, "
            "net_change_1m, pct_change_1m, pct_change_12m}]}. "
            "Observations are sorted oldest -> newest. Use "
            "`list_popular_series` to discover common series IDs."
        ),
    )
    async def bls_get_series(
        series_ids: Annotated[
            SeriesIDList,
            Field(
                description=(
                    "BLS series IDs. Either a list (e.g. "
                    "['CUUR0000SA0','LNS14000000']) or a comma-separated "
                    "string ('CUUR0000SA0,LNS14000000')."
                )
            ),
        ],
        start_year: Annotated[
            int | None,
            Field(
                default=None,
                ge=1900,
                le=2100,
                description="Earliest year to include (YYYY). Omit for BLS default depth.",
            ),
        ] = None,
        end_year: Annotated[
            int | None,
            Field(
                default=None,
                ge=1900,
                le=2100,
                description="Latest year to include (YYYY). Omit for the most recent data.",
            ),
        ] = None,
        include_calculations: Annotated[
            bool,
            Field(
                description=(
                    "If true, ask BLS for net/percent change calculations "
                    "(populates net_change_1m, pct_change_1m, pct_change_12m). "
                    "Requires v2 (a BLS_API_KEY)."
                )
            ),
        ] = False,
        include_annual_average: Annotated[
            bool,
            Field(
                description=(
                    "If true, include the annual-average observation (period "
                    "M13) for each year in monthly series. Requires v2."
                )
            ),
        ] = False,
        include_catalog: Annotated[
            bool,
            Field(
                description=(
                    "If true, ask BLS for the series catalog metadata "
                    "(populates title, units, seasonal_adjustment, and the "
                    "metadata block: survey, area, item, industry, etc.). "
                    "Requires v2."
                )
            ),
        ] = False,
        include_aspects: Annotated[
            bool,
            Field(
                description=(
                    "If true, ask BLS for per-observation aspect metadata "
                    "(survey-specific; e.g. data quality flags). Surfaced "
                    "under each observation's `aspects` field. Requires v2."
                )
            ),
        ] = False,
        calculation_periods: Annotated[
            list[int] | None,
            Field(
                default=None,
                description=(
                    "Restrict calculation columns to these periods (months). "
                    "Allowed values: 1, 3, 6, 12. Default keeps all four. "
                    "Only meaningful when include_calculations=true."
                ),
            ),
        ] = None,
        expose_metadata: Annotated[
            bool,
            Field(
                description=(
                    "If true (default), include the full catalog metadata "
                    "block (survey, area, item, industry, periodicity, etc.) "
                    "alongside the legacy top-level title/units/SA fields. "
                    "Set to false to save tokens on high-cardinality calls."
                )
            ),
        ] = True,
        mode: Annotated[
            OutputMode,
            Field(
                description=(
                    "inline (default) returns the reshaped series in the "
                    "response; summary writes the observations to CSV+Parquet "
                    "under $BLS_OUTPUT_DIR and returns a digest."
                )
            ),
        ] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            if calculation_periods is not None:
                invalid = [p for p in calculation_periods if p not in CALCULATION_PERIODS]
                if invalid:
                    raise ValueError(
                        f"calculation_periods values {invalid} not in "
                        f"{list(CALCULATION_PERIODS)}"
                    )
            raw_series = await _fetch_all_series(
                series_ids,
                start_year=start_year,
                end_year=end_year,
                include_calculations=include_calculations,
                include_annual_average=include_annual_average,
                include_catalog=include_catalog,
                include_aspects=include_aspects,
            )
            reshaped = [
                reshape_series(s, expose_metadata=expose_metadata) for s in raw_series
            ]
            if calculation_periods is not None:
                for series in reshaped:
                    series["observations"] = filter_calculation_periods(
                        series["observations"], calculation_periods
                    )

            if mode == OutputMode.summary:
                # Flatten observations into a long-form table for CSV/Parquet.
                rows: list[dict] = []
                for series in reshaped:
                    sid = series["series_id"]
                    title = series.get("title")
                    for obs in series["observations"]:
                        rows.append({"series_id": sid, "title": title, **obs})
                fname = f"bls_series_{'_'.join(series_ids)[:60]}"
                return render_large_result(
                    rows,
                    name=fname,
                    mode=mode,
                    fmt=response_format,
                    title=f"BLS series ({len(reshaped)})",
                    what=", ".join(series_ids),
                )

            return render_small_result(
                reshaped,
                response_format,
                title=f"BLS series ({len(reshaped)})",
                what=", ".join(series_ids),
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bls_get_latest_observation",
        annotations=READ_ONLY,
        description=(
            "Convenience wrapper that returns just the most recent observation "
            "for a single series, plus the 12-month percent change when v2 is "
            "available. Use this for one-shot questions like 'what's the "
            "latest CPI reading?'. Returns "
            "{series_id, title, date, value, pct_change_12m}."
        ),
    )
    async def bls_get_latest_observation(
        series_id: Annotated[
            SeriesID,
            Field(description="A single BLS series ID, e.g. CUUR0000SA0."),
        ],
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            want_extras = client.using_v2
            raw_series = await client.fetch(
                [series_id],
                catalog=want_extras,
                calculations=want_extras,
            )
            if not raw_series:
                return render_small_result(
                    None,
                    response_format,
                    title=f"Latest observation: {series_id}",
                    what=series_id,
                )
            shaped = reshape_series(raw_series[0])
            observations = shaped.get("observations") or []
            if not observations:
                return render_small_result(
                    None,
                    response_format,
                    title=f"Latest observation: {series_id}",
                    what=series_id,
                )
            latest = observations[-1]
            payload = {
                "series_id": shaped["series_id"],
                "title": shaped.get("title"),
                "date": latest["date"],
                "value": latest["value"],
                "pct_change_12m": latest.get("pct_change_12m"),
            }
            return render_small_result(
                payload,
                response_format,
                title=f"Latest observation: {series_id}",
                what=series_id,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bls_get_latest_observations",
        annotations=READ_ONLY,
        description=(
            "Fetch the most recent observation for many series in a single "
            "v2 call (no year bounds; BLS returns the most-recent period for "
            "each). Use this when you only need the latest reading for "
            "several series at once — much cheaper than calling "
            "bls_get_series for full history. Returns a list of "
            "{series_id, title, date, value, net_change_1m, pct_change_1m, "
            "pct_change_12m}."
        ),
    )
    async def bls_get_latest_observations(
        series_ids: Annotated[
            SeriesIDList,
            Field(
                description=(
                    "BLS series IDs (list or comma-separated string)."
                )
            ),
        ],
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            want_extras = client.using_v2
            raw_series = await _fetch_all_series(
                series_ids,
                start_year=None,
                end_year=None,
                include_calculations=want_extras,
                include_annual_average=False,
                include_catalog=want_extras,
            )
            payload: list[dict[str, Any]] = []
            for s in raw_series:
                shaped = reshape_series(s, expose_metadata=False)
                observations = shaped.get("observations") or []
                if not observations:
                    payload.append(
                        {
                            "series_id": shaped["series_id"],
                            "title": shaped.get("title"),
                            "date": None,
                            "value": None,
                            "net_change_1m": None,
                            "pct_change_1m": None,
                            "pct_change_12m": None,
                        }
                    )
                    continue
                latest = observations[-1]
                payload.append(
                    {
                        "series_id": shaped["series_id"],
                        "title": shaped.get("title"),
                        "date": latest["date"],
                        "value": latest["value"],
                        "net_change_1m": latest.get("net_change_1m"),
                        "pct_change_1m": latest.get("pct_change_1m"),
                        "pct_change_12m": latest.get("pct_change_12m"),
                    }
                )
            return render_small_result(
                payload,
                response_format,
                title=f"Latest observations ({len(payload)})",
                what=", ".join(series_ids),
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bls_list_popular_series",
        annotations=READ_ONLY,
        description=(
            "Return a curated catalog of common BLS series IDs grouped by "
            "category (Prices, Labor, Productivity). Use this to discover the "
            "right series ID before calling `bls_get_series`. Returns a dict "
            "of category -> list of {id, title, units, frequency, "
            "seasonal_adjustment, notes}."
        ),
    )
    async def bls_list_popular_series(
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        return render_small_result(
            POPULAR_SERIES,
            response_format,
            title="Popular BLS series",
            what="popular series",
        )

    @mcp.tool(
        name="bls_get_series_metadata",
        annotations=READ_ONLY,
        description=(
            "Return the catalog metadata for a single BLS series — title, "
            "units, seasonal adjustment, area, item, etc. Useful when the "
            "user asks 'what is series X'. Requires v2 (a BLS_API_KEY); "
            "without one this raises a clear error."
        ),
    )
    async def bls_get_series_metadata(
        series_id: Annotated[
            SeriesID,
            Field(description="A single BLS series ID, e.g. CUUR0000SA0."),
        ],
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            if not client.using_v2:
                return wrap_error(
                    Exception(
                        "Series metadata requires the BLS v2 endpoint. Set "
                        "BLS_API_KEY and restart the server."
                    )
                )
            raw_series = await client.fetch(
                [series_id],
                catalog=True,
                start_year=None,
                end_year=None,
            )
            if not raw_series:
                return render_small_result(
                    None,
                    response_format,
                    title=f"Series metadata: {series_id}",
                    what=series_id,
                )
            catalog = raw_series[0].get("catalog")
            if not catalog:
                return wrap_error(
                    Exception(
                        f"BLS returned no catalog block for {series_id}. The "
                        "series may not have catalog data available."
                    )
                )
            return render_small_result(
                {"series_id": series_id, **catalog},
                response_format,
                title=f"Series metadata: {series_id}",
                what=series_id,
            )
        except Exception as exc:
            return wrap_error(exc)
