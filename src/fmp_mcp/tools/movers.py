"""Market movers: gainers, losers, most active, pre/post-market quotes."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import (
    OutputMode,
    ResponseFormat,
    Symbol,
)
from ._common import (
    READ_ONLY,
    render_large_result,
    render_small_result,
    wrap_error,
)


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fmp_get_gainers",
        annotations=READ_ONLY,
        description=(
            "Top daily gainers. Returns {symbol, name, change, price, "
            "changesPercentage, exchange}. Intraday momentum screen."
        ),
    )
    async def fmp_get_gainers(
        limit: Annotated[int, Field(ge=1, le=500)] = 50,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get("/stable/biggest-gainers", {})
            rows = (data if isinstance(data, list) else [])[:limit]
            return render_large_result(
                rows,
                name=f"gainers_l{limit}",
                mode=mode,
                fmt=response_format,
                title="Top gainers",
                what="gainers",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_losers",
        annotations=READ_ONLY,
        description=(
            "Top daily losers. Same shape as fmp_get_gainers."
        ),
    )
    async def fmp_get_losers(
        limit: Annotated[int, Field(ge=1, le=500)] = 50,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get("/stable/biggest-losers", {})
            rows = (data if isinstance(data, list) else [])[:limit]
            return render_large_result(
                rows,
                name=f"losers_l{limit}",
                mode=mode,
                fmt=response_format,
                title="Top losers",
                what="losers",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_most_active",
        annotations=READ_ONLY,
        description=(
            "Most active stocks by volume. Same shape as fmp_get_gainers."
        ),
    )
    async def fmp_get_most_active(
        limit: Annotated[int, Field(ge=1, le=500)] = 50,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get("/stable/most-actives", {})
            rows = (data if isinstance(data, list) else [])[:limit]
            return render_large_result(
                rows,
                name=f"most_active_l{limit}",
                mode=mode,
                fmt=response_format,
                title="Most active",
                what="most active",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_aftermarket_quote",
        annotations=READ_ONLY,
        description=(
            "After-hours quote for a symbol: {symbol, price, bid, ask, "
            "bidSize, askSize, volume, timestamp}. Useful for next-day "
            "gap analysis."
        ),
    )
    async def fmp_get_aftermarket_quote(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/aftermarket-quote", {"symbol": symbol}
            )
            return render_small_result(
                data,
                response_format,
                title=f"After-market quote: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_aftermarket_trades",
        annotations=READ_ONLY,
        description=(
            "After-hours trade prints for a symbol. Returns rows of "
            "{symbol, price, tradeSize, timestamp}. Used to gauge "
            "after-hours activity intensity."
        ),
    )
    async def fmp_get_aftermarket_trades(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/aftermarket-trade", {"symbol": symbol}
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_aftermarket_trades",
                mode=mode,
                fmt=response_format,
                title=f"After-market trades: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_premarket_quote",
        annotations=READ_ONLY,
        description=(
            "Pre-market quote for a symbol. Same shape as "
            "fmp_get_aftermarket_quote."
        ),
    )
    async def fmp_get_premarket_quote(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/premarket-quote", {"symbol": symbol}
            )
            return render_small_result(
                data,
                response_format,
                title=f"Pre-market quote: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)
