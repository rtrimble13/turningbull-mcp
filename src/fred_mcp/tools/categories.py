"""FRED category tools: lookups, children, related, series, and tags."""

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
        name="fred_get_category",
        annotations=READ_ONLY,
        description="Get a single FRED category by its numeric category_id (0 is the root).",
    )
    async def fred_get_category(
        category_id: Annotated[int, Field(description="FRED category id (root is 0).")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get("/category", qp(category_id=category_id))
            return render_small_result(
                data.get("categories", []),
                response_format,
                title=f"Category {category_id}",
                what=str(category_id),
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_category_children",
        annotations=READ_ONLY,
        description="Get the child categories for a parent FRED category.",
    )
    async def fred_get_category_children(
        category_id: Annotated[int, Field(description="Parent FRED category id.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/category/children",
                qp(category_id=category_id, realtime_start=realtime_start, realtime_end=realtime_end),
            )
            return render_large_result(
                data.get("categories", []),
                name=f"category_{category_id}_children",
                mode=mode,
                fmt=response_format,
                title=f"Children of category {category_id}",
                what=str(category_id),
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_category_related",
        annotations=READ_ONLY,
        description="Get the related categories for a FRED category.",
    )
    async def fred_get_category_related(
        category_id: Annotated[int, Field(description="FRED category id.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get(
                "/category/related",
                qp(category_id=category_id, realtime_start=realtime_start, realtime_end=realtime_end),
            )
            return render_large_result(
                data.get("categories", []),
                name=f"category_{category_id}_related",
                mode=mode,
                fmt=response_format,
                title=f"Related to category {category_id}",
                what=str(category_id),
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_category_series",
        annotations=READ_ONLY,
        description="Get the economic data series in a FRED category.",
    )
    async def fred_get_category_series(
        category_id: Annotated[int, Field(description="FRED category id.")],
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
                "/category/series",
                qp(
                    category_id=category_id,
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
                name=f"category_{category_id}_series",
                mode=mode,
                fmt=response_format,
                title=f"Series in category {category_id}",
                what=str(category_id),
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_category_tags",
        annotations=READ_ONLY,
        description="Get the FRED tags assigned to series in a category.",
    )
    async def fred_get_category_tags(
        category_id: Annotated[int, Field(description="FRED category id.")],
        realtime_start: Annotated[OptionalDate, Field(description="Realtime start (YYYY-MM-DD).")] = None,
        realtime_end: Annotated[OptionalDate, Field(description="Realtime end (YYYY-MM-DD).")] = None,
        tag_names: Annotated[str | None, Field(description="Semicolon-delimited tags to match.")] = None,
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
                "/category/tags",
                qp(
                    category_id=category_id,
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
                name=f"category_{category_id}_tags",
                mode=mode,
                fmt=response_format,
                title=f"Tags for category {category_id}",
                what=str(category_id),
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="fred_get_category_related_tags",
        annotations=READ_ONLY,
        description="Get tags related to a set of tags within a FRED category.",
    )
    async def fred_get_category_related_tags(
        category_id: Annotated[int, Field(description="FRED category id.")],
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
                "/category/related_tags",
                qp(
                    category_id=category_id,
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
                name=f"category_{category_id}_related_tags",
                mode=mode,
                fmt=response_format,
                title=f"Related tags for category {category_id}",
                what=tag_names,
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)
