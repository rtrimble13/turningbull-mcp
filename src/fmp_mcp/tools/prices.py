"""Price history and quote tools."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import (
    Interval,
    OptionalDate,
    OutputMode,
    ResponseFormat,
    Symbol,
    SymbolList,
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
        name="fmp_get_quote",
        annotations=READ_ONLY,
        description=(
            "Fetch a real-time/delayed quote for one or more comma-separated "
            "symbols. Equities, ETFs, indexes (e.g. ^GSPC), forex, crypto, and "
            "commodities are supported. Returns: list of objects with fields "
            "symbol, name, price, change, changesPercentage, dayLow, dayHigh, "
            "yearHigh, yearLow, marketCap, volume, avgVolume, open, "
            "previousClose, eps, pe, sharesOutstanding, timestamp."
        ),
    )
    async def fmp_get_quote(
        symbols: Annotated[
            SymbolList,
            Field(description="One or more tickers, comma-separated. Example: AAPL,MSFT,^GSPC"),
        ],
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            sym_list = symbols.split(",")
            if len(sym_list) == 1:
                data = await client.get("/stable/quote", {"symbol": sym_list[0]})
            else:
                data = await client.get("/stable/batch-quote", {"symbols": symbols})
            return render_small_result(
                data, response_format, title=f"Quote: {symbols}", what=symbols
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_historical_prices",
        annotations=READ_ONLY,
        description=(
            "Daily end-of-day OHLCV history for one symbol. Returns daily bars "
            "with date, open, high, low, close, volume, change, changePercent, "
            "vwap. Use adjClose if returned for return calculations. "
            "Automatically chunks ranges longer than ~5 years. Works for "
            "equities, ETFs, and index symbols (e.g. ^GSPC). For large pulls "
            "use mode='summary' (default) to write the dataset to disk; use "
            "mode='inline' to receive rows in the response."
        ),
    )
    async def fmp_get_historical_prices(
        symbol: Annotated[Symbol, Field(description="Ticker, e.g. AAPL or ^GSPC.")],
        from_date: Annotated[
            OptionalDate,
            Field(description="Start date YYYY-MM-DD. If unset, FMP returns the default depth."),
        ] = None,
        to_date: Annotated[
            OptionalDate,
            Field(description="End date YYYY-MM-DD. If unset, latest available."),
        ] = None,
        mode: Annotated[
            OutputMode,
            Field(description="summary writes to disk and returns a digest; inline returns rows."),
        ] = OutputMode.summary,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown (default) or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            ranges: list[tuple[str | None, str | None]]
            if from_date and to_date:
                ranges = [(a, b) for a, b in chunk_date_range(from_date, to_date)]
            else:
                ranges = [(from_date, to_date)]

            rows: list[dict] = []
            for f, t in ranges:
                params: dict[str, object] = {"symbol": symbol}
                if f:
                    params["from"] = f
                if t:
                    params["to"] = t
                data = await client.get("/stable/historical-price-eod/full", params)
                if isinstance(data, list):
                    rows.extend(data)
                elif isinstance(data, dict) and isinstance(data.get("historical"), list):
                    rows.extend(data["historical"])

            unique_rows = dedupe_by_date(rows)

            fname = f"{symbol}_daily_{from_date or 'start'}_{to_date or 'latest'}"
            return render_large_result(
                unique_rows,
                name=fname,
                mode=mode,
                fmt=response_format,
                title=f"Daily prices: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_intraday_prices",
        annotations=READ_ONLY,
        description=(
            "Intraday OHLCV bars at the chosen interval (1min/5min/15min/30min/"
            "1hour/4hour). Required: symbol, interval. Use from/to to window "
            "long pulls; 1min depth is roughly the last 30 days. Returns date, "
            "open, high, low, close, volume."
        ),
    )
    async def fmp_get_intraday_prices(
        symbol: Annotated[Symbol, Field(description="Ticker, e.g. AAPL.")],
        interval: Annotated[
            Interval, Field(description="Bar interval: 1min, 5min, 15min, 30min, 1hour, 4hour.")
        ],
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        nonadjusted: Annotated[
            bool,
            Field(description="If true, request non-split-adjusted prices."),
        ] = False,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.summary,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {"symbol": symbol}
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            if nonadjusted:
                params["nonadjusted"] = True
            data = await client.get(f"/stable/historical-chart/{interval.value}", params)
            rows = data if isinstance(data, list) else []
            fname = f"{symbol}_{interval.value}_{from_date or 'start'}_{to_date or 'latest'}"
            return render_large_result(
                rows,
                name=fname,
                mode=mode,
                fmt=response_format,
                title=f"Intraday {interval.value}: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)
