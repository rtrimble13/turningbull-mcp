"""Composite "analyst snapshot" tools that bundle multiple FMP calls into one output.

Parallel to the BLS connector's snapshot tools. Each tool issues several
calls concurrently and renders a single consolidated view.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import IndicatorInterval, ResponseFormat, Symbol
from ._common import READ_ONLY, render_small_result, wrap_error


async def _safe_get(path: str, params: dict[str, Any] | None = None) -> Any:
    """Issue a client.get but swallow exceptions to keep composite resilient.

    Composite tools call many endpoints; one 403 (premium gate) or 404
    shouldn't blank the whole snapshot. Failed sub-calls become
    ``{"error": "..."}`` entries in the composite dict so the analyst
    still sees what did succeed.
    """
    try:
        return await get_client().get(path, params or {})
    except Exception as exc:
        return {"error": str(exc)}


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fmp_company_snapshot",
        annotations=READ_ONLY,
        description=(
            "One-pager company snapshot: profile + latest quote + latest "
            "annual key metrics + analyst price target consensus + latest "
            "3 news headlines. Equivalent to a Bloomberg DES page in one "
            "MCP call."
        ),
    )
    async def fmp_company_snapshot(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            profile, quote, metrics, target, news = await asyncio.gather(
                _safe_get("/stable/profile", {"symbol": symbol}),
                _safe_get("/stable/quote", {"symbol": symbol}),
                _safe_get("/stable/key-metrics", {"symbol": symbol, "period": "annual", "limit": 1}),
                _safe_get("/stable/price-target-consensus", {"symbol": symbol}),
                _safe_get("/stable/news/stock", {"symbols": symbol, "limit": 3}),
            )
            payload = {
                "symbol": symbol,
                "profile": profile,
                "quote": quote,
                "latestKeyMetrics": metrics,
                "priceTargetConsensus": target,
                "recentNews": news,
            }
            return render_small_result(
                payload,
                response_format,
                title=f"Company snapshot: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_valuation_snapshot",
        annotations=READ_ONLY,
        description=(
            "Valuation one-pager: DCF + latest key metrics + price target "
            "consensus + peers + Piotroski/Altman scores + rating. "
            "Composite of /stable/discounted-cash-flow, key-metrics, "
            "price-target-consensus, stock-peers, financial-scores, "
            "ratings-snapshot. Failed sub-calls (e.g. premium-gated) "
            "appear as {error: ...} so the rest is still usable."
        ),
    )
    async def fmp_valuation_snapshot(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            dcf, metrics, target, peers, scores, rating = await asyncio.gather(
                _safe_get("/stable/discounted-cash-flow", {"symbol": symbol}),
                _safe_get("/stable/key-metrics", {"symbol": symbol, "period": "annual", "limit": 1}),
                _safe_get("/stable/price-target-consensus", {"symbol": symbol}),
                _safe_get("/stable/stock-peers", {"symbol": symbol}),
                _safe_get("/stable/financial-scores", {"symbol": symbol}),
                _safe_get("/stable/ratings-snapshot", {"symbol": symbol}),
            )
            payload = {
                "symbol": symbol,
                "dcf": dcf,
                "latestKeyMetrics": metrics,
                "priceTargetConsensus": target,
                "peers": peers,
                "financialScores": scores,
                "rating": rating,
            }
            return render_small_result(
                payload,
                response_format,
                title=f"Valuation snapshot: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_earnings_prep",
        annotations=READ_ONLY,
        description=(
            "Earnings prep one-pager: next earnings date + last 4 "
            "surprises + transcript dates + latest analyst estimates + "
            "grade consensus."
        ),
    )
    async def fmp_earnings_prep(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            calendar, surprises, transcripts, estimates, grades = await asyncio.gather(
                _safe_get("/stable/earnings", {"symbol": symbol, "limit": 1}),
                _safe_get("/stable/earnings-surprises", {"symbol": symbol, "limit": 4}),
                _safe_get("/stable/earning-call-transcript-dates", {"symbol": symbol}),
                _safe_get("/stable/analyst-estimates", {"symbol": symbol, "period": "quarter", "limit": 4}),
                _safe_get("/stable/grades-consensus", {"symbol": symbol}),
            )
            payload = {
                "symbol": symbol,
                "nextEarnings": calendar,
                "recentSurprises": surprises,
                "transcriptDates": transcripts,
                "forwardEstimates": estimates,
                "gradeConsensus": grades,
            }
            return render_small_result(
                payload,
                response_format,
                title=f"Earnings prep: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_technical_snapshot",
        annotations=READ_ONLY,
        description=(
            "Technical one-pager: latest quote + RSI(14) + SMA(50) + "
            "SMA(200) + EMA(12) + EMA(26) + ADX(14) at the chosen "
            "interval (default 1day). Returns the latest value of each "
            "indicator alongside the current quote."
        ),
    )
    async def fmp_technical_snapshot(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        interval: Annotated[
            IndicatorInterval, Field(description="Bar interval (default 1day).")
        ] = IndicatorInterval.one_day,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            tf = interval.value

            async def latest(indicator: str, period: int) -> Any:
                data = await _safe_get(
                    f"/stable/technical-indicators/{indicator}",
                    {"symbol": symbol, "periodLength": period, "timeframe": tf},
                )
                if isinstance(data, list) and data:
                    return data[0]
                return data

            quote, rsi14, sma50, sma200, ema12, ema26, adx14 = await asyncio.gather(
                _safe_get("/stable/quote", {"symbol": symbol}),
                latest("rsi", 14),
                latest("sma", 50),
                latest("sma", 200),
                latest("ema", 12),
                latest("ema", 26),
                latest("adx", 14),
            )
            payload = {
                "symbol": symbol,
                "interval": tf,
                "quote": quote,
                "rsi14": rsi14,
                "sma50": sma50,
                "sma200": sma200,
                "ema12": ema12,
                "ema26": ema26,
                "adx14": adx14,
            }
            return render_small_result(
                payload,
                response_format,
                title=f"Technical snapshot ({tf}): {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_ownership_snapshot",
        annotations=READ_ONLY,
        description=(
            "Ownership one-pager: current shares float + institutional "
            "holder summary + last 90-day insider statistics. "
            "Composite tool — failed sub-calls appear as {error: ...}."
        ),
    )
    async def fmp_ownership_snapshot(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            shares_float, institutional, insider_stats = await asyncio.gather(
                _safe_get("/stable/shares-float", {"symbol": symbol}),
                _safe_get(
                    "/stable/institutional-ownership/symbol-positions-summary",
                    {"symbol": symbol},
                ),
                _safe_get(
                    "/stable/insider-trading-statistics",
                    {"symbol": symbol, "limit": 4},
                ),
            )
            payload = {
                "symbol": symbol,
                "sharesFloat": shares_float,
                "institutionalHolders": institutional,
                "insiderStatistics": insider_stats,
            }
            return render_small_result(
                payload,
                response_format,
                title=f"Ownership snapshot: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)
