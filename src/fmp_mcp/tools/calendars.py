"""Event calendars: earnings, dividend, split, IPO, economic."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import (
    OptionalDate,
    OutputMode,
    ResponseFormat,
    Symbol,
)
from ._common import READ_ONLY, render_large_result, wrap_error


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fmp_get_earnings_calendar",
        annotations=READ_ONLY,
        description=(
            "Upcoming and past earnings announcements across the market. "
            "Optional from/to date filters (YYYY-MM-DD). Returns rows of "
            "{symbol, date, epsEstimated, eps, revenueEstimated, revenue, "
            "time, fiscalDateEnding, updatedFromDate}. Useful for earnings "
            "calendars, surprise tracking, and event-driven screening."
        ),
    )
    async def fmp_get_earnings_calendar(
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {}
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            data = await client.get("/stable/earnings-calendar", params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"earnings_calendar_{from_date or 'start'}_{to_date or 'latest'}",
                mode=mode,
                fmt=response_format,
                title="Earnings calendar",
                what="earnings calendar",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_earnings_surprises",
        annotations=READ_ONLY,
        description=(
            "Per-symbol earnings actual vs. estimate history. Returns rows of "
            "{date, symbol, actualEarningResult, estimatedEarning}. Compute "
            "surprise pct as (actual - estimate) / |estimate|. Helpful for "
            "earnings momentum strategies."
        ),
    )
    async def fmp_get_earnings_surprises(
        symbol: Annotated[Symbol, Field(description="Ticker, e.g. AAPL.")],
        limit: Annotated[int, Field(ge=1, le=200)] = 40,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/earnings-surprises", {"symbol": symbol, "limit": limit}
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_earnings_surprises_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Earnings surprises: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_per_symbol_earnings",
        annotations=READ_ONLY,
        description=(
            "Per-symbol earnings announcement history with both estimates and "
            "actuals. Returns rows of {symbol, date, epsEstimated, eps, "
            "revenueEstimated, revenue, fiscalDateEnding, updatedFromDate, "
            "time}. Equivalent to filtering the global earnings calendar to "
            "one symbol but uses the dedicated per-symbol endpoint."
        ),
    )
    async def fmp_get_per_symbol_earnings(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        limit: Annotated[int, Field(ge=1, le=200)] = 40,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/earnings", {"symbol": symbol, "limit": limit}
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_earnings_history_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Earnings history: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_dividend_calendar",
        annotations=READ_ONLY,
        description=(
            "Upcoming dividend events across the market. Optional from/to "
            "filters. Returns {symbol, date, recordDate, paymentDate, "
            "declarationDate, adjDividend, dividend, frequency}."
        ),
    )
    async def fmp_get_dividend_calendar(
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {}
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            data = await client.get("/stable/dividends-calendar", params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"dividend_calendar_{from_date or 'start'}_{to_date or 'latest'}",
                mode=mode,
                fmt=response_format,
                title="Dividend calendar",
                what="dividend calendar",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_split_calendar",
        annotations=READ_ONLY,
        description=(
            "Upcoming stock split events. Returns {symbol, date, numerator, "
            "denominator}. Use to detect splits that will affect price "
            "history adjustment."
        ),
    )
    async def fmp_get_split_calendar(
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {}
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            data = await client.get("/stable/splits-calendar", params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"split_calendar_{from_date or 'start'}_{to_date or 'latest'}",
                mode=mode,
                fmt=response_format,
                title="Split calendar",
                what="split calendar",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_ipo_calendar",
        annotations=READ_ONLY,
        description=(
            "Upcoming IPOs. Returns {symbol, company, date, exchange, "
            "actions, priceRange, shares, marketCap}. Useful for new-issue "
            "tracking."
        ),
    )
    async def fmp_get_ipo_calendar(
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {}
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            data = await client.get("/stable/ipos-calendar", params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"ipo_calendar_{from_date or 'start'}_{to_date or 'latest'}",
                mode=mode,
                fmt=response_format,
                title="IPO calendar",
                what="IPO calendar",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_economic_calendar",
        annotations=READ_ONLY,
        description=(
            "Scheduled macroeconomic data releases across major economies. "
            "Returns {date, country, event, actual, previous, change, "
            "estimate, impact, unit}. Distinct from fmp_get_economic_indicator "
            "(which returns time-series values)."
        ),
    )
    async def fmp_get_economic_calendar(
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {}
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            data = await client.get("/stable/economic-calendar", params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"economic_calendar_{from_date or 'start'}_{to_date or 'latest'}",
                mode=mode,
                fmt=response_format,
                title="Economic calendar",
                what="economic calendar",
            )
        except Exception as exc:
            return wrap_error(exc)
