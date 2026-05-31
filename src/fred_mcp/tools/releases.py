"""FRED release tools: releases, dates, series, sources, tags, and tables."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from turningbull_mcp.models import OptionalDate, OutputMode, ResponseFormat

from ..models import SortOrder
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
        name="fred_get_releases",
        annotations=READ_ONLY,
        description="Get all releases of economic data published on FRED.",
    )
    async def fred_get_releases(
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        limit: Annotated[int | None, Field(description="Max results (1-1000).")] = None,
        offset: Annotated[int | None, Field(description="Result offset (>=0).")] = None,
        order_by: Annotated[str | None, Field(description="Order field: release_id, name, press_release, realtime_start, realtime_end.")] = None,
        sort_order: Annotated[SortOrder | None, Field(description="asc or desc.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/releases",
                qp(
                    realtime_start=realtime_start,
                    realtime_end=realtime_end,
                    limit=limit,
                    offset=offset,
                    order_by=order_by,
                    sort_order=sort_order,
                ),
            )
            return render_large_result(
                data.get("releases", []),
                name="releases",
                mode=mode,
                fmt=response_format,
                title="All releases",
                what="releases",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_releases_dates",
        annotations=READ_ONLY,
        description="Get release dates for all releases of economic data.",
    )
    async def fred_get_releases_dates(
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        limit: Annotated[int | None, Field(description="Max results (1-1000).")] = None,
        offset: Annotated[int | None, Field(description="Result offset (>=0).")] = None,
        order_by: Annotated[str | None, Field(description="Order field: release_date, release_id, release_name.")] = None,
        sort_order: Annotated[SortOrder | None, Field(description="asc or desc.")] = None,
        include_release_dates_with_no_data: Annotated[bool | None, Field(description="Include release dates with no data.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/releases/dates",
                qp(
                    realtime_start=realtime_start,
                    realtime_end=realtime_end,
                    limit=limit,
                    offset=offset,
                    order_by=order_by,
                    sort_order=sort_order,
                    include_release_dates_with_no_data=include_release_dates_with_no_data,
                ),
            )
            return render_large_result(
                data.get("release_dates", []),
                name="releases_dates",
                mode=mode,
                fmt=response_format,
                title="All release dates",
                what="release dates",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_release",
        annotations=READ_ONLY,
        description="Get a single release of economic data by release_id.",
    )
    async def fred_get_release(
        release_id: Annotated[int, Field(description="FRED release id.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/release",
                qp(release_id=release_id, realtime_start=realtime_start, realtime_end=realtime_end),
            )
            return render_small_result(
                data.get("releases", []),
                response_format,
                title=f"Release {release_id}",
                what=str(release_id),
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_release_dates",
        annotations=READ_ONLY,
        description="Get the release dates for a single release of economic data.",
    )
    async def fred_get_release_dates(
        release_id: Annotated[int, Field(description="FRED release id.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        limit: Annotated[int | None, Field(description="Max results (1-10000).")] = None,
        offset: Annotated[int | None, Field(description="Result offset (>=0).")] = None,
        sort_order: Annotated[SortOrder | None, Field(description="asc or desc.")] = None,
        include_release_dates_with_no_data: Annotated[bool | None, Field(description="Include release dates with no data.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/release/dates",
                qp(
                    release_id=release_id,
                    realtime_start=realtime_start,
                    realtime_end=realtime_end,
                    limit=limit,
                    offset=offset,
                    sort_order=sort_order,
                    include_release_dates_with_no_data=include_release_dates_with_no_data,
                ),
            )
            return render_large_result(
                data.get("release_dates", []),
                name=f"release_{release_id}_dates",
                mode=mode,
                fmt=response_format,
                title=f"Release dates for release {release_id}",
                what=str(release_id),
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_release_series",
        annotations=READ_ONLY,
        description="Get the economic data series on a release.",
    )
    async def fred_get_release_series(
        release_id: Annotated[int, Field(description="FRED release id.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        limit: Annotated[int | None, Field(description="Max results (1-1000).")] = None,
        offset: Annotated[int | None, Field(description="Result offset (>=0).")] = None,
        order_by: Annotated[str | None, Field(description="Order field, e.g. series_id, popularity.")] = None,
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
                "/release/series",
                qp(
                    release_id=release_id,
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
                name=f"release_{release_id}_series",
                mode=mode,
                fmt=response_format,
                title=f"Series on release {release_id}",
                what=str(release_id),
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_release_sources",
        annotations=READ_ONLY,
        description="Get the sources for a release of economic data.",
    )
    async def fred_get_release_sources(
        release_id: Annotated[int, Field(description="FRED release id.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/release/sources",
                qp(release_id=release_id, realtime_start=realtime_start, realtime_end=realtime_end),
            )
            return render_large_result(
                data.get("sources", []),
                name=f"release_{release_id}_sources",
                mode=mode,
                fmt=response_format,
                title=f"Sources for release {release_id}",
                what=str(release_id),
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_release_tags",
        annotations=READ_ONLY,
        description="Get the FRED tags for a release.",
    )
    async def fred_get_release_tags(
        release_id: Annotated[int, Field(description="FRED release id.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        tag_names: Annotated[str | None, Field(description="Semicolon-delimited tags to match.")] = None,
        tag_group_id: Annotated[str | None, Field(description="Tag group id: freq, gen, geo, geot, rls, seas, src.")] = None,
        search_text: Annotated[str | None, Field(description="Words to find matching tags.")] = None,
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
                "/release/tags",
                qp(
                    release_id=release_id,
                    realtime_start=realtime_start,
                    realtime_end=realtime_end,
                    tag_names=tag_names,
                    tag_group_id=tag_group_id,
                    search_text=search_text,
                    limit=limit,
                    offset=offset,
                    order_by=order_by,
                    sort_order=sort_order,
                ),
            )
            return render_large_result(
                data.get("tags", []),
                name=f"release_{release_id}_tags",
                mode=mode,
                fmt=response_format,
                title=f"Tags for release {release_id}",
                what=str(release_id),
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_release_related_tags",
        annotations=READ_ONLY,
        description="Get tags related to a set of tags within a release.",
    )
    async def fred_get_release_related_tags(
        release_id: Annotated[int, Field(description="FRED release id.")],
        tag_names: Annotated[str, Field(description="Semicolon-delimited tags to find related tags for.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        exclude_tag_names: Annotated[str | None, Field(description="Semicolon-delimited tags to exclude.")] = None,
        tag_group_id: Annotated[str | None, Field(description="Tag group id to filter by.")] = None,
        search_text: Annotated[str | None, Field(description="Words to find matching tags.")] = None,
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
                "/release/related_tags",
                qp(
                    release_id=release_id,
                    tag_names=tag_names,
                    realtime_start=realtime_start,
                    realtime_end=realtime_end,
                    exclude_tag_names=exclude_tag_names,
                    tag_group_id=tag_group_id,
                    search_text=search_text,
                    limit=limit,
                    offset=offset,
                    order_by=order_by,
                    sort_order=sort_order,
                ),
            )
            return render_large_result(
                data.get("tags", []),
                name=f"release_{release_id}_related_tags",
                mode=mode,
                fmt=response_format,
                title=f"Related tags for release {release_id}",
                what=tag_names,
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_release_tables",
        annotations=READ_ONLY,
        description="Get the release table tree for a given release (and optional element).",
    )
    async def fred_get_release_tables(
        release_id: Annotated[int, Field(description="FRED release id.")],
        element_id: Annotated[int | None, Field(description="Optional element id to root the table tree.")] = None,
        include_observation_values: Annotated[bool | None, Field(description="Include observation values in the tree.")] = None,
        observation_date: Annotated[OptionalDate, Field(description="Observation date for values (YYYY-MM-DD).")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/release/tables",
                qp(
                    release_id=release_id,
                    element_id=element_id,
                    include_observation_values=include_observation_values,
                    observation_date=observation_date,
                ),
            )
            return render_small_result(
                data,
                response_format,
                title=f"Release {release_id} tables",
                what=str(release_id),
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)
