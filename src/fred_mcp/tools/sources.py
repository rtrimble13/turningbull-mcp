"""FRED source tools: all sources, a single source, and a source's releases."""

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
        name="fred_get_sources",
        annotations=READ_ONLY,
        description="Get all sources of economic data on FRED.",
    )
    async def fred_get_sources(
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        limit: Annotated[int | None, Field(description="Max results (1-1000).")] = None,
        offset: Annotated[int | None, Field(description="Result offset (>=0).")] = None,
        order_by: Annotated[str | None, Field(description="Order field: source_id, name, realtime_start, realtime_end.")] = None,
        sort_order: Annotated[SortOrder | None, Field(description="asc or desc.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/sources",
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
                data.get("sources", []),
                name="sources",
                mode=mode,
                fmt=response_format,
                title="All sources",
                what="sources",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_source",
        annotations=READ_ONLY,
        description="Get a single source of economic data by source_id.",
    )
    async def fred_get_source(
        source_id: Annotated[int, Field(description="FRED source id.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/source",
                qp(source_id=source_id, realtime_start=realtime_start, realtime_end=realtime_end),
            )
            return render_small_result(
                data.get("sources", []), response_format, title=f"Source {source_id}", what=str(source_id)
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_source_releases",
        annotations=READ_ONLY,
        description="Get the releases for a source of economic data.",
    )
    async def fred_get_source_releases(
        source_id: Annotated[int, Field(description="FRED source id.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        limit: Annotated[int | None, Field(description="Max results (1-1000).")] = None,
        offset: Annotated[int | None, Field(description="Result offset (>=0).")] = None,
        order_by: Annotated[str | None, Field(description="Order field: release_id, name, ...")] = None,
        sort_order: Annotated[SortOrder | None, Field(description="asc or desc.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/source/releases",
                qp(
                    source_id=source_id,
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
                name=f"source_{source_id}_releases",
                mode=mode,
                fmt=response_format,
                title=f"Releases for source {source_id}",
                what=str(source_id),
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)
