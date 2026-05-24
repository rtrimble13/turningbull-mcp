"""Earnings call transcripts."""

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
        name="fmp_list_earnings_transcripts",
        annotations=READ_ONLY,
        description=(
            "List available earnings call transcripts for a symbol. Returns "
            "{symbol, quarter, year, date} per available transcript. Use to "
            "look up which year+quarter to pass to fmp_get_earnings_transcript."
        ),
    )
    async def fmp_list_earnings_transcripts(
        symbol: Annotated[Symbol, Field(description="Ticker, e.g. AAPL.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/earning-call-transcript-dates", {"symbol": symbol}
            )
            return render_small_result(
                data,
                response_format,
                title=f"Transcript dates: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_earnings_transcript",
        annotations=READ_ONLY,
        description=(
            "Full text of one earnings call transcript. Returns {symbol, "
            "quarter, year, date, content}. Transcripts can be tens of "
            "thousands of words — default mode=summary writes the transcript "
            "to disk; use mode=inline to read inline (may be very large)."
        ),
    )
    async def fmp_get_earnings_transcript(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        year: Annotated[int, Field(ge=2000, le=2100, description="Fiscal year.")],
        quarter: Annotated[int, Field(ge=1, le=4, description="Fiscal quarter (1-4).")],
        mode: Annotated[OutputMode, Field(description="summary (default) or inline.")] = OutputMode.summary,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/earning-call-transcript",
                {"symbol": symbol, "year": year, "quarter": quarter},
            )
            rows = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
            return render_large_result(
                rows,
                name=f"{symbol}_transcript_{year}Q{quarter}",
                mode=mode,
                fmt=response_format,
                title=f"Earnings transcript: {symbol} {year}Q{quarter}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_latest_transcripts",
        annotations=READ_ONLY,
        description=(
            "Most recent earnings call transcripts across the market. "
            "Returns rows of {symbol, period, fiscalYear, date, content}. "
            "May require a premium FMP plan; expect a 403-style error on "
            "free keys."
        ),
    )
    async def fmp_get_latest_transcripts(
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        page: Annotated[int, Field(ge=0)] = 0,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.summary,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/earning-call-transcript-latest",
                {"limit": limit, "page": page},
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"latest_transcripts_p{page}_l{limit}",
                mode=mode,
                fmt=response_format,
                title="Latest earnings transcripts",
                what="transcripts",
            )
        except Exception as exc:
            return wrap_error(exc)
