"""FRED series tools: metadata, observations, search, tags, updates, vintages."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from turningbull_mcp.models import OptionalDate, OutputMode, ResponseFormat

from ..models import AggregationMethod, SortOrder, Units
from ._common import (
    READ_ONLY,
    get_client,
    qp,
    render_large_result,
    render_small_result,
    wrap_error,
)


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fred_get_series",
        annotations=READ_ONLY,
        description="Get metadata for an economic data series by series_id (e.g. GNPCA).",
    )
    async def fred_get_series(
        series_id: Annotated[str, Field(description="FRED series id, e.g. GNPCA.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/series",
                qp(series_id=series_id, realtime_start=realtime_start, realtime_end=realtime_end),
            )
            return render_small_result(
                data.get("seriess", []), response_format, title=f"Series {series_id}", what=series_id
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_series_categories",
        annotations=READ_ONLY,
        description="Get the categories that an economic data series belongs to.",
    )
    async def fred_get_series_categories(
        series_id: Annotated[str, Field(description="FRED series id.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/series/categories",
                qp(series_id=series_id, realtime_start=realtime_start, realtime_end=realtime_end),
            )
            return render_large_result(
                data.get("categories", []),
                name=f"{series_id}_categories",
                mode=mode,
                fmt=response_format,
                title=f"Categories for {series_id}",
                what=series_id,
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_series_observations",
        annotations=READ_ONLY,
        description="Get the observations (data values) for an economic data series.",
    )
    async def fred_get_series_observations(
        series_id: Annotated[str, Field(description="FRED series id, e.g. GNPCA.")],
        observation_start: Annotated[OptionalDate, Field(description="First observation date (YYYY-MM-DD).")] = None,
        observation_end: Annotated[OptionalDate, Field(description="Last observation date (YYYY-MM-DD).")] = None,
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        units: Annotated[Units | None, Field(description="Value transform (lin, pch, pc1, chg, log, ...).")] = None,
        frequency: Annotated[str | None, Field(description="Aggregate to frequency: d,w,bw,m,q,sa,a (+ eop variants).")] = None,
        aggregation_method: Annotated[AggregationMethod | None, Field(description="avg, sum, or eop when aggregating.")] = None,
        output_type: Annotated[int | None, Field(description="1=obs by realtime, 2=all vintages, 3=new+revised, 4=initial release.")] = None,
        vintage_dates: Annotated[str | None, Field(description="Comma-separated vintage dates (YYYY-MM-DD).")] = None,
        limit: Annotated[int | None, Field(description="Max results (1-100000).")] = None,
        offset: Annotated[int | None, Field(description="Result offset (>=0).")] = None,
        sort_order: Annotated[SortOrder | None, Field(description="asc or desc by observation date.")] = None,
        mode: Annotated[OutputMode, Field(description="summary (write CSV/Parquet) or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/series/observations",
                qp(
                    series_id=series_id,
                    observation_start=observation_start,
                    observation_end=observation_end,
                    realtime_start=realtime_start,
                    realtime_end=realtime_end,
                    units=units,
                    frequency=frequency,
                    aggregation_method=aggregation_method,
                    output_type=output_type,
                    vintage_dates=vintage_dates,
                    limit=limit,
                    offset=offset,
                    sort_order=sort_order,
                ),
            )
            return render_large_result(
                data.get("observations", []),
                name=f"{series_id}_observations",
                mode=mode,
                fmt=response_format,
                title=f"Observations for {series_id}",
                what=series_id,
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_series_release",
        annotations=READ_ONLY,
        description="Get the release that an economic data series belongs to.",
    )
    async def fred_get_series_release(
        series_id: Annotated[str, Field(description="FRED series id.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/series/release",
                qp(series_id=series_id, realtime_start=realtime_start, realtime_end=realtime_end),
            )
            return render_small_result(
                data.get("releases", []), response_format, title=f"Release for {series_id}", what=series_id
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_search_series",
        annotations=READ_ONLY,
        description="Search for economic data series by keywords or series-id text.",
    )
    async def fred_search_series(
        search_text: Annotated[str, Field(description="Words to match against series.")],
        search_type: Annotated[str | None, Field(description="full_text (default) or series_id.")] = None,
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        limit: Annotated[int | None, Field(description="Max results (1-1000).")] = None,
        offset: Annotated[int | None, Field(description="Result offset (>=0).")] = None,
        order_by: Annotated[str | None, Field(description="Order field: search_rank, series_id, title, popularity, ...")] = None,
        sort_order: Annotated[SortOrder | None, Field(description="asc or desc.")] = None,
        filter_variable: Annotated[str | None, Field(description="Filter field: frequency, units, seasonal_adjustment.")] = None,
        filter_value: Annotated[str | None, Field(description="Value for filter_variable.")] = None,
        tag_names: Annotated[str | None, Field(description="Semicolon-delimited tags to match.")] = None,
        exclude_tag_names: Annotated[str | None, Field(description="Semicolon-delimited tags to exclude.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/series/search",
                qp(
                    search_text=search_text,
                    search_type=search_type,
                    realtime_start=realtime_start,
                    realtime_end=realtime_end,
                    limit=limit,
                    offset=offset,
                    order_by=order_by,
                    sort_order=sort_order,
                    filter_variable=filter_variable,
                    filter_value=filter_value,
                    tag_names=tag_names,
                    exclude_tag_names=exclude_tag_names,
                ),
            )
            return render_large_result(
                data.get("seriess", []),
                name="series_search",
                mode=mode,
                fmt=response_format,
                title=f"Series matching '{search_text}'",
                what=search_text,
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_series_search_tags",
        annotations=READ_ONLY,
        description="Get the FRED tags for a series search.",
    )
    async def fred_get_series_search_tags(
        series_search_text: Annotated[str, Field(description="Series search words the tags apply to.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        tag_names: Annotated[str | None, Field(description="Semicolon-delimited tags to match.")] = None,
        tag_group_id: Annotated[str | None, Field(description="Tag group id to filter by.")] = None,
        tag_search_text: Annotated[str | None, Field(description="Words to find matching tags.")] = None,
        limit: Annotated[int | None, Field(description="Max results (1-1000).")] = None,
        offset: Annotated[int | None, Field(description="Result offset (>=0).")] = None,
        order_by: Annotated[str | None, Field(description="Order field for tags.")] = None,
        sort_order: Annotated[SortOrder | None, Field(description="asc or desc.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/series/search/tags",
                qp(
                    series_search_text=series_search_text,
                    realtime_start=realtime_start,
                    realtime_end=realtime_end,
                    tag_names=tag_names,
                    tag_group_id=tag_group_id,
                    tag_search_text=tag_search_text,
                    limit=limit,
                    offset=offset,
                    order_by=order_by,
                    sort_order=sort_order,
                ),
            )
            return render_large_result(
                data.get("tags", []),
                name="series_search_tags",
                mode=mode,
                fmt=response_format,
                title=f"Tags for search '{series_search_text}'",
                what=series_search_text,
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_series_search_related_tags",
        annotations=READ_ONLY,
        description="Get tags related to a set of tags for a series search.",
    )
    async def fred_get_series_search_related_tags(
        series_search_text: Annotated[str, Field(description="Series search words the tags apply to.")],
        tag_names: Annotated[str, Field(description="Semicolon-delimited tags to find related tags for.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        exclude_tag_names: Annotated[str | None, Field(description="Semicolon-delimited tags to exclude.")] = None,
        tag_group_id: Annotated[str | None, Field(description="Tag group id to filter by.")] = None,
        tag_search_text: Annotated[str | None, Field(description="Words to find matching tags.")] = None,
        limit: Annotated[int | None, Field(description="Max results (1-1000).")] = None,
        offset: Annotated[int | None, Field(description="Result offset (>=0).")] = None,
        order_by: Annotated[str | None, Field(description="Order field for tags.")] = None,
        sort_order: Annotated[SortOrder | None, Field(description="asc or desc.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/series/search/related_tags",
                qp(
                    series_search_text=series_search_text,
                    tag_names=tag_names,
                    realtime_start=realtime_start,
                    realtime_end=realtime_end,
                    exclude_tag_names=exclude_tag_names,
                    tag_group_id=tag_group_id,
                    tag_search_text=tag_search_text,
                    limit=limit,
                    offset=offset,
                    order_by=order_by,
                    sort_order=sort_order,
                ),
            )
            return render_large_result(
                data.get("tags", []),
                name="series_search_related_tags",
                mode=mode,
                fmt=response_format,
                title=f"Related tags for search '{series_search_text}'",
                what=tag_names,
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_series_tags",
        annotations=READ_ONLY,
        description="Get the FRED tags for an economic data series.",
    )
    async def fred_get_series_tags(
        series_id: Annotated[str, Field(description="FRED series id.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        order_by: Annotated[str | None, Field(description="Order field for tags.")] = None,
        sort_order: Annotated[SortOrder | None, Field(description="asc or desc.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/series/tags",
                qp(
                    series_id=series_id,
                    realtime_start=realtime_start,
                    realtime_end=realtime_end,
                    order_by=order_by,
                    sort_order=sort_order,
                ),
            )
            return render_large_result(
                data.get("tags", []),
                name=f"{series_id}_tags",
                mode=mode,
                fmt=response_format,
                title=f"Tags for {series_id}",
                what=series_id,
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_series_updates",
        annotations=READ_ONLY,
        description="Get economic data series sorted by when their observations were updated.",
    )
    async def fred_get_series_updates(
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        filter_value: Annotated[str | None, Field(description="Geographic filter: macro, regional, or all.")] = None,
        start_time: Annotated[str | None, Field(description="Start time YYYYMMDDHhmm (UTC).")] = None,
        end_time: Annotated[str | None, Field(description="End time YYYYMMDDHhmm (UTC).")] = None,
        limit: Annotated[int | None, Field(description="Max results (1-1000).")] = None,
        offset: Annotated[int | None, Field(description="Result offset (>=0).")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/series/updates",
                qp(
                    realtime_start=realtime_start,
                    realtime_end=realtime_end,
                    filter_value=filter_value,
                    start_time=start_time,
                    end_time=end_time,
                    limit=limit,
                    offset=offset,
                ),
            )
            return render_large_result(
                data.get("seriess", []),
                name="series_updates",
                mode=mode,
                fmt=response_format,
                title="Recently updated series",
                what="series updates",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_series_vintagedates",
        annotations=READ_ONLY,
        description="Get the dates in history when a series' data values were revised or released.",
    )
    async def fred_get_series_vintagedates(
        series_id: Annotated[str, Field(description="FRED series id.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        limit: Annotated[int | None, Field(description="Max results (1-10000).")] = None,
        offset: Annotated[int | None, Field(description="Result offset (>=0).")] = None,
        sort_order: Annotated[SortOrder | None, Field(description="asc or desc.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/series/vintagedates",
                qp(
                    series_id=series_id,
                    realtime_start=realtime_start,
                    realtime_end=realtime_end,
                    limit=limit,
                    offset=offset,
                    sort_order=sort_order,
                ),
            )
            vintages = data.get("vintage_dates", [])
            rows = [{"vintage_date": v} for v in vintages]
            return render_large_result(
                rows,
                name=f"{series_id}_vintagedates",
                mode=mode,
                fmt=response_format,
                title=f"Vintage dates for {series_id}",
                what=series_id,
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)
