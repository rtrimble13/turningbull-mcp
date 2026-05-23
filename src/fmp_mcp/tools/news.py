"""News and press release tools."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import OptionalDate, OptionalSymbolList, OutputMode, ResponseFormat
from ._common import READ_ONLY, render_large_result, wrap_error


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fmp_get_stock_news",
        annotations=READ_ONLY,
        description=(
            "Company news. If `symbols` is provided, filters to those tickers; "
            "if omitted, returns the latest stock-news feed. Returns headline, "
            "publisher, publishedDate, url, snippet text, and symbol. Supports "
            "from/to date filters and limit/page pagination."
        ),
    )
    async def fmp_get_stock_news(
        symbols: Annotated[
            OptionalSymbolList,
            Field(description="Tickers to filter on, comma-separated. Omit for global feed."),
        ] = None,
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        page: Annotated[int, Field(ge=0, description="0-based page.")] = 0,
        limit: Annotated[int, Field(ge=1, le=250, description="Items per page.")] = 50,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {"page": page, "limit": limit}
            if symbols:
                params["symbols"] = symbols
                if from_date:
                    params["from"] = from_date
                if to_date:
                    params["to"] = to_date
                data = await client.get("/stable/news/stock", params)
            else:
                data = await client.get("/stable/news/stock-latest", params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"stock_news_{symbols or 'feed'}_p{page}",
                mode=mode,
                fmt=response_format,
                title=f"Stock news: {symbols or 'latest'}",
                what=symbols or "stock news",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_market_news",
        annotations=READ_ONLY,
        description=(
            "General/market-wide financial news feed. Returns headline, "
            "publisher, publishedDate, site, url, snippet text. Supports "
            "limit/page pagination."
        ),
    )
    async def fmp_get_market_news(
        page: Annotated[int, Field(ge=0, description="0-based page.")] = 0,
        limit: Annotated[int, Field(ge=1, le=250, description="Items per page.")] = 50,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/news/general-latest", {"page": page, "limit": limit}
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"market_news_p{page}",
                mode=mode,
                fmt=response_format,
                title="Market news",
                what="market news",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_press_releases",
        annotations=READ_ONLY,
        description=(
            "Official company press releases. If `symbols` is provided, "
            "filters to those tickers; if omitted, returns the latest "
            "press-release feed. Returns symbol, date, title, text, url."
        ),
    )
    async def fmp_get_press_releases(
        symbols: Annotated[
            OptionalSymbolList,
            Field(description="Tickers to filter on, comma-separated. Omit for global feed."),
        ] = None,
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        page: Annotated[int, Field(ge=0, description="0-based page.")] = 0,
        limit: Annotated[int, Field(ge=1, le=250, description="Items per page.")] = 50,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {"page": page, "limit": limit}
            if symbols:
                params["symbols"] = symbols
                if from_date:
                    params["from"] = from_date
                if to_date:
                    params["to"] = to_date
                data = await client.get("/stable/news/press-releases", params)
            else:
                data = await client.get("/stable/news/press-releases-latest", params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"press_releases_{symbols or 'feed'}_p{page}",
                mode=mode,
                fmt=response_format,
                title=f"Press releases: {symbols or 'latest'}",
                what=symbols or "press releases",
            )
        except Exception as exc:
            return wrap_error(exc)
