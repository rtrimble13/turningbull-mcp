"""GeoFRED (FRED Maps) tools: shape files, series groups, and regional data."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from turningbull_mcp.models import OptionalDate, ResponseFormat

from ..models import AggregationMethod, Units
from ._common import (
    READ_ONLY,
    get_client,
    qp,
    render_small_result,
    wrap_error,
)


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fred_get_geofred_shapes",
        annotations=READ_ONLY,
        description="Get GeoFRED shape (GeoJSON) files for a geographic region type.",
    )
    async def fred_get_geofred_shapes(
        shape: Annotated[
            str,
            Field(
                description=(
                    "Region type: bea, frb, necta, state, country, county, "
                    "censusregion, censusdivision, etc."
                )
            ),
        ],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.json,
    ) -> str:
        try:
            data = await get_client().geo_get("/shapes/file", qp(shape=shape))
            return render_small_result(data, response_format, title=f"GeoFRED shapes: {shape}", what=shape)
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_geofred_series_group",
        annotations=READ_ONLY,
        description="Get GeoFRED metadata about the geographic series group for a series_id.",
    )
    async def fred_get_geofred_series_group(
        series_id: Annotated[str, Field(description="FRED series id with regional data.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.json,
    ) -> str:
        try:
            data = await get_client().geo_get("/series/group", qp(series_id=series_id))
            return render_small_result(
                data, response_format, title=f"GeoFRED series group: {series_id}", what=series_id
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_geofred_series_data",
        annotations=READ_ONLY,
        description="Get GeoFRED regional data for a single mappable series_id.",
    )
    async def fred_get_geofred_series_data(
        series_id: Annotated[str, Field(description="FRED series id with regional data.")],
        date: Annotated[OptionalDate, Field(description="Single observation date (YYYY-MM-DD).")] = None,
        start_date: Annotated[OptionalDate, Field(description="Start date for a date range (YYYY-MM-DD).")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.json,
    ) -> str:
        try:
            data = await get_client().geo_get(
                "/series/data", qp(series_id=series_id, date=date, start_date=start_date)
            )
            return render_small_result(
                data, response_format, title=f"GeoFRED series data: {series_id}", what=series_id
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_geofred_regional_data",
        annotations=READ_ONLY,
        description="Get GeoFRED regional data for a series group, region type, and date.",
    )
    async def fred_get_geofred_regional_data(
        series_group: Annotated[str, Field(description="GeoFRED series group id (from series/group).")],
        region_type: Annotated[str, Field(description="Region type: state, county, msa, country, etc.")],
        date: Annotated[str, Field(description="Observation date (YYYY-MM-DD).")],
        season: Annotated[str, Field(description="Seasonality: SA, NSA, or SSA.")],
        units: Annotated[str, Field(description="Units of measurement for the data (e.g. Dollars).")],
        start_date: Annotated[OptionalDate, Field(description="Start date for a date range (YYYY-MM-DD).")] = None,
        transformation: Annotated[Units | None, Field(description="Value transform (lin, chg, ch1, pch, pc1, pca, cch, cca, log).")] = None,
        frequency: Annotated[str | None, Field(description="Aggregate to frequency: d, w, bw, m, q, sa, a (+ eop variants).")] = None,
        aggregation_method: Annotated[AggregationMethod | None, Field(description="avg, sum, or eop when aggregating.")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.json,
    ) -> str:
        try:
            data = await get_client().geo_get(
                "/regional/data",
                qp(
                    series_group=series_group,
                    region_type=region_type,
                    date=date,
                    season=season,
                    units=units,
                    start_date=start_date,
                    transformation=transformation,
                    frequency=frequency,
                    aggregation_method=aggregation_method,
                ),
            )
            return render_small_result(
                data, response_format, title=f"GeoFRED regional data: {series_group}", what=series_group
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)
