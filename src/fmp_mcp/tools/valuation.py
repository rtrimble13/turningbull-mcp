"""Valuation: DCF variants, financial scores (Piotroski + Altman Z), letter ratings."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import (
    OutputMode,
    Period,
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
        name="fmp_get_dcf",
        annotations=READ_ONLY,
        description=(
            "FMP's basic discounted cash flow fair value: {symbol, date, "
            "dcf, Stock Price}. Compare dcf to current price for implied "
            "upside / downside."
        ),
    )
    async def fmp_get_dcf(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/discounted-cash-flow", {"symbol": symbol}
            )
            return render_small_result(
                data,
                response_format,
                title=f"DCF: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_advanced_dcf",
        annotations=READ_ONLY,
        description=(
            "Detailed multi-stage DCF with revenue/margin/CapEx assumptions "
            "broken out per year. Returns {year, symbol, revenue, "
            "ebitdaPercentage, ebit, depreciation, totalCash, totalDebt, "
            "wacc, terminalValue, enterpriseValue, equityValue, dcfPerShare, "
            "...}. PREMIUM endpoint — may 403 on free plans."
        ),
    )
    async def fmp_get_advanced_dcf(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/custom-discounted-cash-flow", {"symbol": symbol}
            )
            rows = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
            return render_large_result(
                rows,
                name=f"{symbol}_advanced_dcf",
                mode=mode,
                fmt=response_format,
                title=f"Advanced DCF: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_levered_dcf",
        annotations=READ_ONLY,
        description=(
            "Levered DCF — values equity directly via FCFE rather than "
            "enterprise FCF. Returns the same shape as advanced DCF with "
            "leverage-adjusted terminal value. PREMIUM endpoint."
        ),
    )
    async def fmp_get_levered_dcf(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/custom-levered-discounted-cash-flow",
                {"symbol": symbol},
            )
            rows = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
            return render_large_result(
                rows,
                name=f"{symbol}_levered_dcf",
                mode=mode,
                fmt=response_format,
                title=f"Levered DCF: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_historical_dcf",
        annotations=READ_ONLY,
        description=(
            "Historical DCF fair value time series. Returns {symbol, date, "
            "dcf, Stock Price} per period. Useful for tracking whether the "
            "stock has historically traded above/below DCF."
        ),
    )
    async def fmp_get_historical_dcf(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        period: Annotated[
            Period, Field(description="annual or quarter.")
        ] = Period.annual,
        limit: Annotated[int, Field(ge=1, le=200)] = 40,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/historical-discounted-cash-flow-statement",
                {"symbol": symbol, "period": period.value, "limit": limit},
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_historical_dcf_{period.value}_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Historical DCF ({period.value}): {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_financial_score",
        annotations=READ_ONLY,
        description=(
            "Quality scores in one call: Piotroski F-Score (0-9, quality "
            "of fundamentals) and Altman Z-Score (bankruptcy risk; <1.81 "
            "= distress, >2.99 = safe). Returns {symbol, "
            "altmanZScore, piotroskiScore, workingCapital, totalAssets, "
            "retainedEarnings, ebit, marketCap, totalLiabilities, revenue}."
        ),
    )
    async def fmp_get_financial_score(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/financial-scores", {"symbol": symbol}
            )
            return render_small_result(
                data,
                response_format,
                title=f"Financial scores: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_company_rating",
        annotations=READ_ONLY,
        description=(
            "FMP's overall letter-grade rating with sub-scores: "
            "{symbol, date, rating, ratingScore, ratingRecommendation, "
            "ratingDetailsDCFScore, ratingDetailsROEScore, "
            "ratingDetailsROAScore, ratingDetailsDEScore, "
            "ratingDetailsPEScore, ratingDetailsPBScore}. Composite "
            "fundamental health snapshot."
        ),
    )
    async def fmp_get_company_rating(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/ratings-snapshot", {"symbol": symbol}
            )
            return render_small_result(
                data,
                response_format,
                title=f"Rating: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_historical_rating",
        annotations=READ_ONLY,
        description=(
            "Historical FMP rating time series — useful for tracking "
            "quality trajectory over time. Returns the same fields as "
            "fmp_get_company_rating per date."
        ),
    )
    async def fmp_get_historical_rating(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        limit: Annotated[int, Field(ge=1, le=2000)] = 100,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/ratings-historical",
                {"symbol": symbol, "limit": limit},
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_rating_history_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Historical rating: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)
