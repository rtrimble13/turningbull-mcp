"""Corporate information tools: profile, symbol search, executives, float, market cap."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import (
    OptionalDate,
    OutputMode,
    ResponseFormat,
    SearchMode,
    Symbol,
)
from ._common import (
    READ_ONLY,
    chunk_date_range,
    dedupe_by_date,
    render_large_result,
    render_small_result,
    wrap_error,
)


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fmp_get_company_profile",
        annotations=READ_ONLY,
        description=(
            "Company profile: symbol, companyName, sector, industry, exchange, "
            "country, mktCap, description, ceo, fullTimeEmployees, website, "
            "ipoDate, beta, volAvg, lastDiv, range, price, isEtf, "
            "isActivelyTrading, isAdr, isFund."
        ),
    )
    async def fmp_get_company_profile(
        symbol: Annotated[Symbol, Field(description="Ticker, e.g. AAPL.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get("/stable/profile", {"symbol": symbol})
            return render_small_result(
                data, response_format, title=f"Profile: {symbol}", what=symbol
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_search_symbol",
        annotations=READ_ONLY,
        description=(
            "Search for a ticker by name or partial symbol. mode='name' uses "
            "/stable/search-name (good for 'Apple' → AAPL); mode='symbol' uses "
            "/stable/search-symbol (good for partial tickers). Returns array "
            "of {symbol, name, currency, exchangeFullName, exchange}."
        ),
    )
    async def fmp_search_symbol(
        query: Annotated[str, Field(min_length=1, description="Search string.")],
        mode: Annotated[
            SearchMode,
            Field(description="name (name-based) or symbol (ticker-based)."),
        ] = SearchMode.name,
        limit: Annotated[int, Field(ge=1, le=100, description="Max results.")] = 20,
        exchange: Annotated[
            str | None, Field(description="Optional exchange filter, e.g. NASDAQ.")
        ] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            path = "/stable/search-name" if mode == SearchMode.name else "/stable/search-symbol"
            params: dict[str, object] = {"query": query, "limit": limit}
            if exchange:
                params["exchange"] = exchange
            data = await client.get(path, params)
            return render_small_result(
                data, response_format, title=f"Search ({mode.value}): {query}", what=query
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_company_executives",
        annotations=READ_ONLY,
        description=(
            "Key executives / management for a symbol. Returns array of "
            "{title, name, pay, currencyPay, gender, yearBorn, titleSince}."
        ),
    )
    async def fmp_get_company_executives(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get("/stable/key-executives", {"symbol": symbol})
            return render_small_result(
                data, response_format, title=f"Executives: {symbol}", what=symbol
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_shares_float",
        annotations=READ_ONLY,
        description=(
            "Float and outstanding share data for a symbol. Returns "
            "{symbol, date, freeFloat, floatShares, outstandingShares, source}."
        ),
    )
    async def fmp_get_shares_float(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get("/stable/shares-float", {"symbol": symbol})
            return render_small_result(
                data, response_format, title=f"Shares float: {symbol}", what=symbol
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_market_cap",
        annotations=READ_ONLY,
        description=(
            "Market capitalization for a symbol. If `from_date` or `to_date` "
            "is provided, returns the historical-market-cap time series "
            "(automatically chunked for ranges over ~5 years); otherwise "
            "returns the current point-in-time market cap. Both modes return "
            "rows of {symbol, date, marketCap}."
        ),
    )
    async def fmp_get_market_cap(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        from_date: Annotated[
            OptionalDate, Field(description="Start date YYYY-MM-DD for historical mode.")
        ] = None,
        to_date: Annotated[
            OptionalDate, Field(description="End date YYYY-MM-DD for historical mode.")
        ] = None,
        limit: Annotated[
            int, Field(ge=1, le=5000, description="Max rows per chunk.")
        ] = 1000,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            if not from_date and not to_date:
                data = await client.get("/stable/market-cap", {"symbol": symbol})
                return render_small_result(
                    data,
                    response_format,
                    title=f"Market cap: {symbol}",
                    what=symbol,
                )

            ranges = (
                chunk_date_range(from_date, to_date)
                if from_date and to_date
                else [(from_date, to_date)]
            )
            rows: list[dict] = []
            for f, t in ranges:
                params: dict[str, object] = {"symbol": symbol, "limit": limit}
                if f:
                    params["from"] = f
                if t:
                    params["to"] = t
                data = await client.get("/stable/historical-market-cap", params)
                if isinstance(data, list):
                    rows.extend(data)

            unique_rows = dedupe_by_date(rows)

            return render_large_result(
                unique_rows,
                name=f"{symbol}_marketcap_{from_date or 'start'}_{to_date or 'latest'}",
                mode=mode,
                fmt=response_format,
                title=f"Historical market cap: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)
