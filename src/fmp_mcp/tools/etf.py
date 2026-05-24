"""ETF and mutual fund tools: holdings, holders (reverse lookup), profile, weightings."""

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
        name="fmp_get_etf_holdings",
        annotations=READ_ONLY,
        description=(
            "Constituent holdings of an ETF. Returns rows of {symbol, "
            "asset, sharesNumber, weightPercentage, marketValue, "
            "updatedAt}. SPY, QQQ, IWM, sector ETFs all supported."
        ),
    )
    async def fmp_get_etf_holdings(
        symbol: Annotated[Symbol, Field(description="ETF ticker, e.g. SPY.")],
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.summary,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/etf/holdings", {"symbol": symbol}
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_etf_holdings",
                mode=mode,
                fmt=response_format,
                title=f"ETF holdings: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_etf_holders",
        annotations=READ_ONLY,
        description=(
            "Reverse lookup: which ETFs hold a given stock, with weight "
            "and share count. Returns rows of {etfSymbol, etfName, "
            "weightPercentage, sharesNumber, marketValue, updatedAt}."
        ),
    )
    async def fmp_get_etf_holders(
        symbol: Annotated[Symbol, Field(description="Stock ticker, e.g. AAPL.")],
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/etf/holder", {"symbol": symbol}
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_etf_holders",
                mode=mode,
                fmt=response_format,
                title=f"ETFs holding {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_etf_info",
        annotations=READ_ONLY,
        description=(
            "ETF profile: {symbol, name, description, isin, assetClass, "
            "domicile, etfCompany, expenseRatio, aum, nav, navCurrency, "
            "inceptionDate}. Used for ETF screening."
        ),
    )
    async def fmp_get_etf_info(
        symbol: Annotated[Symbol, Field(description="ETF ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/etf/info", {"symbol": symbol}
            )
            return render_small_result(
                data,
                response_format,
                title=f"ETF info: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_etf_country_weightings",
        annotations=READ_ONLY,
        description=(
            "ETF allocation by country. Returns rows of {country, "
            "weightPercentage}."
        ),
    )
    async def fmp_get_etf_country_weightings(
        symbol: Annotated[Symbol, Field(description="ETF ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/etf/country-weightings", {"symbol": symbol}
            )
            return render_small_result(
                data,
                response_format,
                title=f"ETF country weights: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_etf_sector_weightings",
        annotations=READ_ONLY,
        description=(
            "ETF allocation by sector. Returns rows of {sector, "
            "weightPercentage}."
        ),
    )
    async def fmp_get_etf_sector_weightings(
        symbol: Annotated[Symbol, Field(description="ETF ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/etf/sector-weightings", {"symbol": symbol}
            )
            return render_small_result(
                data,
                response_format,
                title=f"ETF sector weights: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_mutual_fund_holdings",
        annotations=READ_ONLY,
        description=(
            "Holdings for a mutual fund symbol. Same shape as ETF "
            "holdings. PREMIUM endpoint on some plans."
        ),
    )
    async def fmp_get_mutual_fund_holdings(
        symbol: Annotated[Symbol, Field(description="Mutual fund ticker.")],
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.summary,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/funds/holdings", {"symbol": symbol}
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_mutual_fund_holdings",
                mode=mode,
                fmt=response_format,
                title=f"Mutual fund holdings: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)
