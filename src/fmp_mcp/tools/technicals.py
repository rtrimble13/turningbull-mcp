"""Technical indicators (SMA, EMA, WMA, DEMA, TEMA, Williams, RSI, ADX, stdev)."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import (
    IndicatorInterval,
    OptionalDate,
    OutputMode,
    ResponseFormat,
    Symbol,
    TechnicalIndicator,
)
from ._common import READ_ONLY, render_large_result, wrap_error


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fmp_get_technical_indicator",
        annotations=READ_ONLY,
        description=(
            "Technical indicator series for a symbol at the chosen interval. "
            "Indicator ∈ {sma, ema, wma, dema, tema, williams, rsi, adx, "
            "standardDeviation}. Returns OHLCV rows with the indicator value "
            "appended as a column matching the indicator name (e.g. `rsi`, "
            "`sma`). For longer-term technical work use interval=1day; for "
            "intraday signals choose 1min/5min/15min/30min/1hour/4hour. "
            "period_length is the lookback (e.g. 14 for RSI(14), 50 or 200 "
            "for moving averages). Daily depth is multi-year; 1min depth is "
            "roughly the last 30 days."
        ),
    )
    async def fmp_get_technical_indicator(
        symbol: Annotated[Symbol, Field(description="Ticker, e.g. AAPL.")],
        indicator: Annotated[
            TechnicalIndicator,
            Field(description="One of sma/ema/wma/dema/tema/williams/rsi/adx/standardDeviation."),
        ],
        period_length: Annotated[
            int, Field(ge=1, le=500, description="Lookback period (e.g. 14 for RSI, 50/200 for MA).")
        ] = 14,
        interval: Annotated[
            IndicatorInterval,
            Field(description="Bar interval: 1min, 5min, 15min, 30min, 1hour, 4hour, or 1day."),
        ] = IndicatorInterval.one_day,
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.summary,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {
                "symbol": symbol,
                "periodLength": period_length,
                "timeframe": interval.value,
            }
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            data = await client.get(
                f"/stable/technical-indicators/{indicator.value}", params
            )
            rows = data if isinstance(data, list) else []
            fname = (
                f"{symbol}_{indicator.value}_{period_length}_"
                f"{interval.value}_{from_date or 'start'}_{to_date or 'latest'}"
            )
            return render_large_result(
                rows,
                name=fname,
                mode=mode,
                fmt=response_format,
                title=f"{indicator.value.upper()}({period_length}) {interval.value}: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)
