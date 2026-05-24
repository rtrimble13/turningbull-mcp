"""Ownership signals: insider trades (Form 4), 13F institutional holdings, political trades."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import (
    CIK,
    InsiderTransactionType,
    OptionalSymbol,
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
        name="fmp_get_insider_trades",
        annotations=READ_ONLY,
        description=(
            "SEC Form 4 insider transactions. Returns {symbol, filingDate, "
            "transactionDate, reportingCik, reportingName, transactionType, "
            "securitiesOwned, securitiesTransacted, price, formType, link}. "
            "Large insider purchases signal management confidence."
        ),
    )
    async def fmp_get_insider_trades(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        transaction_type: Annotated[
            InsiderTransactionType,
            Field(description="ALL, P-Purchase, S-Sale, A-Award, M-Exempt, G-Gift."),
        ] = InsiderTransactionType.all,
        page: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
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
            if transaction_type != InsiderTransactionType.all:
                params["transactionType"] = transaction_type.value
            data = await client.get("/stable/insider-trading", params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_insider_{transaction_type.value}_p{page}_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Insider trades: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_insider_statistics",
        annotations=READ_ONLY,
        description=(
            "Quarterly summary of insider activity for a symbol. Returns "
            "{symbol, cik, year, quarter, acquiredTransactions, "
            "disposedTransactions, acquiredDisposedRatio, totalAcquired, "
            "totalDisposed, averageAcquired, averageDisposed, "
            "totalCompensation}. Cleaner read than per-trade scrolling."
        ),
    )
    async def fmp_get_insider_statistics(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/insider-trading-statistics",
                {"symbol": symbol, "limit": limit},
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_insider_stats_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Insider statistics: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_institutional_holders",
        annotations=READ_ONLY,
        description=(
            "Top institutional holders of a stock with shares held, "
            "weight %, and quarter-over-quarter change. Returns rows of "
            "{date, investorsHolding, lastInvestorsHolding, "
            "investorsHoldingChange, numberOf13Fshares, "
            "lastNumberOf13Fshares, numberOf13FsharesChange, "
            "totalInvested, lastTotalInvested, totalInvestedChange, "
            "ownershipPercent}."
        ),
    )
    async def fmp_get_institutional_holders(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/institutional-ownership/symbol-positions-summary",
                {"symbol": symbol},
            )
            rows = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
            return render_large_result(
                rows,
                name=f"{symbol}_institutional",
                mode=mode,
                fmt=response_format,
                title=f"Institutional holders: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_form_13f",
        annotations=READ_ONLY,
        description=(
            "Form 13F quarterly holdings for one institutional investor by "
            "CIK. Returns per-position rows with CUSIP, security name, "
            "shares, market value, weight. Use fmp_search_institution to "
            "look up a CIK by name first."
        ),
    )
    async def fmp_get_form_13f(
        cik: Annotated[CIK, Field(description="10-digit SEC CIK of the institution.")],
        year: Annotated[int, Field(ge=1990, le=2100, description="Filing year.")],
        quarter: Annotated[int, Field(ge=1, le=4, description="Filing quarter (1-4).")],
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.summary,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/institutional-ownership/extract",
                {"cik": cik, "year": year, "quarter": quarter},
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"13f_{cik}_{year}Q{quarter}",
                mode=mode,
                fmt=response_format,
                title=f"13F: CIK {cik} {year}Q{quarter}",
                what=f"CIK {cik}",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_search_institution",
        annotations=READ_ONLY,
        description=(
            "Search for an institutional investor by name. Returns "
            "{cik, name}. Pass the CIK to fmp_get_form_13f."
        ),
    )
    async def fmp_search_institution(
        name: Annotated[str, Field(min_length=2, description="Institution name fragment.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/institutional-ownership/list", {"name": name}
            )
            return render_small_result(
                data,
                response_format,
                title=f"Institutions matching: {name}",
                what=name,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_senate_trades",
        annotations=READ_ONLY,
        description=(
            "US Senator stock trades (STOCK Act disclosures). Filter by "
            "symbol or leave blank for global feed. Returns {firstName, "
            "lastName, office, link, dateRecieved, transactionDate, "
            "owner, assetDescription, assetType, type, amount, comment, "
            "symbol}."
        ),
    )
    async def fmp_get_senate_trades(
        symbol: Annotated[OptionalSymbol, Field(description="Optional ticker filter.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {}
            path = "/stable/senate-latest"
            if symbol:
                params["symbol"] = symbol
                path = "/stable/senate-trades"
            data = await client.get(path, params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"senate_trades_{symbol or 'all'}",
                mode=mode,
                fmt=response_format,
                title=f"Senate trades: {symbol or 'all'}",
                what=symbol or "senate feed",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_house_trades",
        annotations=READ_ONLY,
        description=(
            "US House Representative stock trades. Same shape as senate "
            "trades. Useful niche alpha signal."
        ),
    )
    async def fmp_get_house_trades(
        symbol: Annotated[OptionalSymbol, Field(description="Optional ticker filter.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {}
            path = "/stable/house-latest"
            if symbol:
                params["symbol"] = symbol
                path = "/stable/house-trades"
            data = await client.get(path, params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"house_trades_{symbol or 'all'}",
                mode=mode,
                fmt=response_format,
                title=f"House trades: {symbol or 'all'}",
                what=symbol or "house feed",
            )
        except Exception as exc:
            return wrap_error(exc)
