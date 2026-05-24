"""Multi-asset discovery: forex pairs, crypto, commodities lists & snapshot quotes.

Historical and per-symbol quotes for these assets already work through
``fmp_get_quote`` and ``fmp_get_historical_prices`` using the appropriate
symbol (e.g. ``EURUSD``, ``BTCUSD``, ``CLUSD``). The tools here add
discovery and batch snapshots.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import OutputMode, ResponseFormat
from ._common import READ_ONLY, render_large_result, render_small_result, wrap_error


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fmp_list_forex_pairs",
        annotations=READ_ONLY,
        description=(
            "List all forex pairs FMP supports. Returns {symbol, "
            "fromCurrency, toCurrency, fromName, toName}."
        ),
    )
    async def fmp_list_forex_pairs(
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get("/stable/forex-list", {})
            return render_small_result(
                data, response_format, title="Forex pairs", what="forex"
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_list_crypto",
        annotations=READ_ONLY,
        description=(
            "List all cryptocurrencies FMP supports. Returns {symbol, "
            "name, exchange, icoDate, circulatingSupply, totalSupply}."
        ),
    )
    async def fmp_list_crypto(
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get("/stable/cryptocurrency-list", {})
            return render_small_result(
                data, response_format, title="Cryptocurrencies", what="crypto"
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_list_commodities",
        annotations=READ_ONLY,
        description=(
            "List all commodities FMP supports (metals, energy, "
            "agriculture). Returns {symbol, name, currency, "
            "stockExchange, exchangeShortName, tradeMonth, "
            "currentTimezone}."
        ),
    )
    async def fmp_list_commodities(
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get("/stable/commodities-list", {})
            return render_small_result(
                data, response_format, title="Commodities", what="commodities"
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_all_forex_quotes",
        annotations=READ_ONLY,
        description=(
            "Snapshot quotes for all forex pairs. Useful for FX dashboards. "
            "Returns the same shape as fmp_get_quote per pair."
        ),
    )
    async def fmp_get_all_forex_quotes(
        mode: Annotated[
            OutputMode, Field(description="summary or inline.")
        ] = OutputMode.summary,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get("/stable/batch-forex-quotes", {})
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name="forex_quotes",
                mode=mode,
                fmt=response_format,
                title="Forex quotes",
                what="forex quotes",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_all_crypto_quotes",
        annotations=READ_ONLY,
        description=(
            "Snapshot quotes for all cryptocurrencies. Same shape as "
            "fmp_get_quote per coin."
        ),
    )
    async def fmp_get_all_crypto_quotes(
        mode: Annotated[
            OutputMode, Field(description="summary or inline.")
        ] = OutputMode.summary,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get("/stable/batch-crypto-quotes", {})
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name="crypto_quotes",
                mode=mode,
                fmt=response_format,
                title="Crypto quotes",
                what="crypto quotes",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_all_commodity_quotes",
        annotations=READ_ONLY,
        description=(
            "Snapshot quotes for all commodities. Same shape as "
            "fmp_get_quote per commodity."
        ),
    )
    async def fmp_get_all_commodity_quotes(
        mode: Annotated[
            OutputMode, Field(description="summary or inline.")
        ] = OutputMode.summary,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get("/stable/batch-commodity-quotes", {})
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name="commodity_quotes",
                mode=mode,
                fmt=response_format,
                title="Commodity quotes",
                what="commodity quotes",
            )
        except Exception as exc:
            return wrap_error(exc)
