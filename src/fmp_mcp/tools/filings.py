"""SEC filings: per-symbol filings list, form-type search, 8-K feed, M&A."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import (
    FormType,
    OptionalDate,
    OutputMode,
    ResponseFormat,
    Symbol,
)
from ._common import READ_ONLY, render_large_result, render_small_result, wrap_error


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fmp_list_sec_filings",
        annotations=READ_ONLY,
        description=(
            "All SEC filings for a symbol with optional form-type and date "
            "filters. Returns {symbol, cik, filingDate, acceptedDate, "
            "formType, link, finalLink}. finalLink points to the actual "
            "filing on SEC EDGAR."
        ),
    )
    async def fmp_list_sec_filings(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        form_type: Annotated[
            FormType, Field(description="Form filter. ALL to skip.")
        ] = FormType.all,
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        page: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=1000)] = 100,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {
                "symbol": symbol,
                "page": page,
                "limit": limit,
            }
            if form_type != FormType.all:
                params["type"] = form_type.value
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            data = await client.get("/stable/sec-filings-search/symbol", params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_filings_{form_type.value}_p{page}_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"SEC filings: {symbol} ({form_type.value})",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_search_filings_by_form_type",
        annotations=READ_ONLY,
        description=(
            "Stream every recent SEC filing of a given form type across "
            "the market. Useful for tracking, e.g., every new 10-K, every "
            "new 8-K, or every new S-1. Returns {symbol, cik, filingDate, "
            "acceptedDate, formType, link, finalLink}."
        ),
    )
    async def fmp_search_filings_by_form_type(
        form_type: Annotated[
            FormType, Field(description="Form to filter (10-K, 10-Q, 8-K, etc.).")
        ],
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        page: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=1000)] = 100,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            if form_type == FormType.all:
                return "**Error.** form_type=ALL is not valid here; pick a specific form."
            client = get_client()
            params: dict[str, object] = {
                "formType": form_type.value,
                "page": page,
                "limit": limit,
            }
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            data = await client.get(
                "/stable/sec-filings-search/form-type", params
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"filings_{form_type.value}_p{page}_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"SEC filings: {form_type.value}",
                what=form_type.value,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_8k_feed",
        annotations=READ_ONLY,
        description=(
            "Real-time 8-K material event feed. Useful for detecting M&A, "
            "executive departures, regulatory actions, earnings preannouncements. "
            "Returns the same shape as fmp_list_sec_filings filtered to 8-K."
        ),
    )
    async def fmp_get_8k_feed(
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        page: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=1000)] = 100,
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
            data = await client.get("/stable/sec-filings-8k", params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"8k_feed_p{page}_l{limit}",
                mode=mode,
                fmt=response_format,
                title="8-K filings feed",
                what="8-K",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_search_mergers_acquisitions",
        annotations=READ_ONLY,
        description=(
            "Search announced mergers and acquisitions by company name. "
            "Returns {companyName, cik, symbol, targetedCompanyName, "
            "targetedCik, targetedSymbol, transactionDate, acceptedDate, "
            "link}."
        ),
    )
    async def fmp_search_mergers_acquisitions(
        name: Annotated[str, Field(min_length=2, description="Company name fragment.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/mergers-acquisitions-search", {"name": name}
            )
            return render_small_result(
                data,
                response_format,
                title=f"M&A search: {name}",
                what=name,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_latest_mergers_acquisitions",
        annotations=READ_ONLY,
        description=(
            "Latest announced M&A deals across the market. Returns the "
            "same shape as fmp_search_mergers_acquisitions."
        ),
    )
    async def fmp_get_latest_mergers_acquisitions(
        page: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/mergers-acquisitions-latest",
                {"page": page, "limit": limit},
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"ma_latest_p{page}_l{limit}",
                mode=mode,
                fmt=response_format,
                title="Latest M&A",
                what="M&A",
            )
        except Exception as exc:
            return wrap_error(exc)
