"""Analyst estimates, price targets, upgrades/downgrades, and stock grades."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import (
    OptionalDate,
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
        name="fmp_get_analyst_estimates",
        annotations=READ_ONLY,
        description=(
            "Forward analyst estimates for revenue, EBITDA, EBIT, EPS by "
            "period. Returns {symbol, date, revenueAvg, revenueLow, "
            "revenueHigh, ebitdaAvg, epsAvg, epsLow, epsHigh, "
            "numAnalystsRevenue, numAnalystsEps}. Period ∈ annual | quarter."
        ),
    )
    async def fmp_get_analyst_estimates(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        period: Annotated[
            Period, Field(description="annual or quarter.")
        ] = Period.annual,
        limit: Annotated[int, Field(ge=1, le=200)] = 10,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/analyst-estimates",
                {"symbol": symbol, "period": period.value, "limit": limit},
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_analyst_estimates_{period.value}_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Analyst estimates ({period.value}): {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_price_target_consensus",
        annotations=READ_ONLY,
        description=(
            "Consensus analyst price target snapshot: {symbol, targetHigh, "
            "targetLow, targetConsensus, targetMedian}. Compare to current "
            "price (fmp_get_quote) to compute implied upside."
        ),
    )
    async def fmp_get_price_target_consensus(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/price-target-consensus", {"symbol": symbol}
            )
            return render_small_result(
                data,
                response_format,
                title=f"Price target consensus: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_price_target_summary",
        annotations=READ_ONLY,
        description=(
            "Rolling price target statistics: last month / quarter / year "
            "average targets and analyst counts. Returns {symbol, "
            "lastMonth*, lastQuarter*, lastYear*, allTime*, publishers}. "
            "Reveals direction of target revisions."
        ),
    )
    async def fmp_get_price_target_summary(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/price-target-summary", {"symbol": symbol}
            )
            return render_small_result(
                data,
                response_format,
                title=f"Price target summary: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_price_target_news",
        annotations=READ_ONLY,
        description=(
            "Firm-level price target changes as a news feed. Returns "
            "{symbol, publishedDate, newsURL, newsTitle, analystName, "
            "priceTarget, adjPriceTarget, priceWhenPosted, newsPublisher, "
            "analystCompany}."
        ),
    )
    async def fmp_get_price_target_news(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        page: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=250)] = 50,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/price-target-news",
                {"symbol": symbol, "page": page, "limit": limit},
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_price_target_news_p{page}_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Price target news: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_upgrades_downgrades",
        annotations=READ_ONLY,
        description=(
            "Rating change history: {symbol, publishedDate, newsURL, "
            "newsTitle, newsBaseURL, newsPublisher, newGrade, previousGrade, "
            "gradingCompany, action, priceWhenPosted}. Use for sentiment "
            "shift analysis."
        ),
    )
    async def fmp_get_upgrades_downgrades(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        page: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=250)] = 50,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/grades",
                {"symbol": symbol, "page": page, "limit": limit},
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_grades_p{page}_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Upgrades & downgrades: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_stock_grade_consensus",
        annotations=READ_ONLY,
        description=(
            "Consensus rating distribution across analyst firms: {symbol, "
            "strongBuy, buy, hold, sell, strongSell, consensus}."
        ),
    )
    async def fmp_get_stock_grade_consensus(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/grades-consensus", {"symbol": symbol}
            )
            return render_small_result(
                data,
                response_format,
                title=f"Grade consensus: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_latest_upgrades_downgrades",
        annotations=READ_ONLY,
        description=(
            "Market-wide latest rating changes feed. Optional date filters. "
            "Useful for daily sentiment scanning."
        ),
    )
    async def fmp_get_latest_upgrades_downgrades(
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        page: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=250)] = 50,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {"page": page, "limit": limit}
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            data = await client.get("/stable/grades-latest-news", params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"grades_latest_p{page}_l{limit}",
                mode=mode,
                fmt=response_format,
                title="Latest upgrades & downgrades",
                what="grades feed",
            )
        except Exception as exc:
            return wrap_error(exc)
