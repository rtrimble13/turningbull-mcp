"""Stock index tools: listing, quotes, constituents."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import IndexName, ResponseFormat, SymbolList
from ._common import READ_ONLY, render_small_result, wrap_error


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fmp_list_indexes",
        annotations=READ_ONLY,
        description=(
            "List the market indexes FMP exposes. Each row: "
            "{symbol, name, exchange, currency}. Use the `symbol` (e.g. ^GSPC) "
            "with fmp_get_quote or fmp_get_historical_prices."
        ),
    )
    async def fmp_list_indexes(
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get("/stable/indexes-list")
            return render_small_result(data, response_format, title="Indexes", what="indexes")
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_index_quote",
        annotations=READ_ONLY,
        description=(
            "Quote for one or more index symbols (e.g. ^GSPC, ^IXIC, ^DJI). "
            "Same response shape as fmp_get_quote. For index price history "
            "call fmp_get_historical_prices with the index symbol."
        ),
    )
    async def fmp_get_index_quote(
        symbols: Annotated[
            SymbolList, Field(description="Index symbols, comma-separated. Example: ^GSPC,^IXIC")
        ],
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            sym_list = symbols.split(",")
            if len(sym_list) == 1:
                data = await client.get("/stable/quote", {"symbol": sym_list[0]})
            else:
                data = await client.get("/stable/batch-quote", {"symbols": symbols})
            return render_small_result(
                data, response_format, title=f"Index quote: {symbols}", what=symbols
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_index_constituents",
        annotations=READ_ONLY,
        description=(
            "Members of a major US index: S&P 500, Nasdaq 100, or Dow Jones. "
            "Returns {symbol, name, sector, subSector, headQuarter, "
            "dateFirstAdded, cik, founded}."
        ),
    )
    async def fmp_get_index_constituents(
        index: Annotated[
            IndexName,
            Field(description="One of: sp500, nasdaq, dowjones."),
        ],
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        path_map = {
            IndexName.sp500: "/stable/sp500-constituent",
            IndexName.nasdaq: "/stable/nasdaq-constituent",
            IndexName.dowjones: "/stable/dowjones-constituent",
        }
        try:
            data = await get_client().get(path_map[index])
            return render_small_result(
                data, response_format, title=f"{index.value} constituents", what=index.value
            )
        except Exception as exc:
            return wrap_error(exc)
