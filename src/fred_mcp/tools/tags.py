"""FRED tag tools: all tags, related tags, and series matching tags."""

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
    wrap_error,
)


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fred_get_tags",
        annotations=READ_ONLY,
        description="Get FRED tags, optionally searching or filtering by name/group.",
    )
    async def fred_get_tags(
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        tag_names: Annotated[str | None, Field(description="Semicolon-delimited tag names to get.")] = None,
        tag_group_id: Annotated[str | None, Field(description="Tag group id: freq, gen, geo, geot, rls, seas, src.")] = None,
        search_text: Annotated[str | None, Field(description="Words to find matching tags.")] = None,
        limit: Annotated[int | None, Field(description="Max results (1-1000).")] = None,
        offset: Annotated[int | None, Field(description="Result offset (>=0).")] = None,
        order_by: Annotated[str | None, Field(description="Order field: series_count, popularity, created, name, group_id.")] = None,
        sort_order: Annotated[SortOrder | None, Field(description="asc or desc.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/tags",
                qp(
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
                name="tags",
                mode=mode,
                fmt=response_format,
                title="FRED tags",
                what="tags",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_related_tags",
        annotations=READ_ONLY,
        description="Get tags related to a set of tags across all of FRED.",
    )
    async def fred_get_related_tags(
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
                "/related_tags",
                qp(
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
                name="related_tags",
                mode=mode,
                fmt=response_format,
                title="Related tags",
                what=tag_names,
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_tags_series",
        annotations=READ_ONLY,
        description="Get the economic data series matching a set of tags.",
    )
    async def fred_get_tags_series(
        tag_names: Annotated[str, Field(description="Semicolon-delimited tags series must match.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        exclude_tag_names: Annotated[str | None, Field(description="Semicolon-delimited tags to exclude.")] = None,
        limit: Annotated[int | None, Field(description="Max results (1-1000).")] = None,
        offset: Annotated[int | None, Field(description="Result offset (>=0).")] = None,
        order_by: Annotated[str | None, Field(description="Order field, e.g. series_id, popularity.")] = None,
        sort_order: Annotated[SortOrder | None, Field(description="asc or desc.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/tags/series",
                qp(
                    tag_names=tag_names,
                    realtime_start=realtime_start,
                    realtime_end=realtime_end,
                    exclude_tag_names=exclude_tag_names,
                    limit=limit,
                    offset=offset,
                    order_by=order_by,
                    sort_order=sort_order,
                ),
            )
            return render_large_result(
                data.get("seriess", []),
                name="tags_series",
                mode=mode,
                fmt=response_format,
                title=f"Series matching tags '{tag_names}'",
                what=tag_names,
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)
