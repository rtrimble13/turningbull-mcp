"""Economic indicator and US treasury rate tools."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import (
    ECONOMIC_INDICATORS,
    OptionalDate,
    OutputMode,
    ResponseFormat,
)
from ._common import READ_ONLY, render_large_result, render_small_result, wrap_error


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fmp_list_economic_indicators",
        annotations=READ_ONLY,
        description=(
            "List the indicator `name` values accepted by fmp_get_economic_indicator. "
            "FMP does not expose a discovery endpoint; this is a curated, "
            "documented set."
        ),
    )
    async def fmp_list_economic_indicators(
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        data = [{"name": n} for n in ECONOMIC_INDICATORS]
        return render_small_result(
            data, response_format, title="Economic indicators", what="indicators"
        )

    @mcp.tool(
        name="fmp_get_economic_indicator",
        annotations=READ_ONLY,
        description=(
            "Time series for a named economic indicator (e.g. GDP, CPI, "
            "unemploymentRate, federalFunds). Returns rows of {date, value}. "
            "Call fmp_list_economic_indicators to discover valid `name` values."
        ),
    )
    async def fmp_get_economic_indicator(
        name: Annotated[
            str,
            Field(
                min_length=1,
                description="Indicator name. See fmp_list_economic_indicators.",
            ),
        ],
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {"name": name}
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            data = await client.get("/stable/economic-indicators", params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"econ_{name}_{from_date or 'start'}_{to_date or 'latest'}",
                mode=mode,
                fmt=response_format,
                title=f"Economic indicator: {name}",
                what=name,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_treasury_rates",
        annotations=READ_ONLY,
        description=(
            "US Treasury constant-maturity rates across tenors. Each row is a "
            "single day with fields: date, month1, month2, month3, month6, "
            "year1, year2, year3, year5, year7, year10, year20, year30. Daily "
            "resolution only."
        ),
    )
    async def fmp_get_treasury_rates(
        from_date: Annotated[OptionalDate, Field(description="Start date YYYY-MM-DD.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date YYYY-MM-DD.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {}
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            data = await client.get("/stable/treasury-rates", params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"treasury_{from_date or 'start'}_{to_date or 'latest'}",
                mode=mode,
                fmt=response_format,
                title="Treasury rates",
                what="treasury rates",
            )
        except Exception as exc:
            return wrap_error(exc)
