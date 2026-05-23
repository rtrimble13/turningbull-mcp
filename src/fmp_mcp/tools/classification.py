"""Sector and industry classification tools."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import OptionalDate, OutputMode, ResponseFormat
from ._common import READ_ONLY, render_large_result, render_small_result, wrap_error


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fmp_list_sectors",
        annotations=READ_ONLY,
        description="List the sector names FMP exposes (use these as `sector` filter values).",
    )
    async def fmp_list_sectors(
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get("/stable/available-sectors")
            return render_small_result(data, response_format, title="Sectors", what="sectors")
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_list_industries",
        annotations=READ_ONLY,
        description="List the industry names FMP exposes (use these as `industry` filter values).",
    )
    async def fmp_list_industries(
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            data = await get_client().get("/stable/available-industries")
            return render_small_result(data, response_format, title="Industries", what="industries")
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_sector_performance",
        annotations=READ_ONLY,
        description=(
            "Sector performance. Without `sector`, returns a snapshot for all "
            "sectors (optionally filtered by `date` and `exchange`). With "
            "`sector` plus `from_date`/`to_date`, returns the historical "
            "performance series. Response rows: {date, sector, exchange, "
            "averageChange}."
        ),
    )
    async def fmp_get_sector_performance(
        sector: Annotated[
            str | None,
            Field(description="Sector name. Provide together with from/to for the historical series."),
        ] = None,
        from_date: Annotated[OptionalDate, Field(description="Start date for historical series.")] = None,
        to_date: Annotated[OptionalDate, Field(description="End date for historical series.")] = None,
        snapshot_date: Annotated[
            OptionalDate, Field(description="Snapshot date YYYY-MM-DD (snapshot mode).")
        ] = None,
        exchange: Annotated[str | None, Field(description="Exchange filter.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            if sector and (from_date or to_date):
                params: dict[str, object] = {"sector": sector}
                if from_date:
                    params["from"] = from_date
                if to_date:
                    params["to"] = to_date
                if exchange:
                    params["exchange"] = exchange
                data = await client.get("/stable/historical-sector-performance", params)
                rows = data if isinstance(data, list) else []
                return render_large_result(
                    rows,
                    name=f"sector_perf_{sector}_{from_date or 'start'}_{to_date or 'latest'}",
                    mode=mode,
                    fmt=response_format,
                    title=f"Historical sector performance: {sector}",
                    what=sector,
                )

            params = {}
            if snapshot_date:
                params["date"] = snapshot_date
            if exchange:
                params["exchange"] = exchange
            if sector:
                params["sector"] = sector
            data = await client.get("/stable/sector-performance-snapshot", params)
            return render_small_result(
                data, response_format, title="Sector performance snapshot", what="sector performance"
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_sector_pe",
        annotations=READ_ONLY,
        description=(
            "Sector P/E ratios. Without `sector`, returns the snapshot for "
            "all sectors at `snapshot_date` (required). With `sector` plus "
            "`from_date`/`to_date`, returns the historical sector P/E series."
        ),
    )
    async def fmp_get_sector_pe(
        snapshot_date: Annotated[
            OptionalDate, Field(description="Snapshot date (required if `sector` is not set).")
        ] = None,
        sector: Annotated[str | None, Field(description="Sector name.")] = None,
        from_date: Annotated[OptionalDate, Field(description="Historical series start.")] = None,
        to_date: Annotated[OptionalDate, Field(description="Historical series end.")] = None,
        exchange: Annotated[str | None, Field(description="Exchange filter.")] = None,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            if sector and (from_date or to_date):
                params: dict[str, object] = {"sector": sector}
                if from_date:
                    params["from"] = from_date
                if to_date:
                    params["to"] = to_date
                if exchange:
                    params["exchange"] = exchange
                data = await client.get("/stable/historical-sector-pe", params)
                rows = data if isinstance(data, list) else []
                return render_large_result(
                    rows,
                    name=f"sector_pe_{sector}_{from_date or 'start'}_{to_date or 'latest'}",
                    mode=mode,
                    fmt=response_format,
                    title=f"Historical sector P/E: {sector}",
                    what=sector,
                )

            if not snapshot_date:
                return (
                    "**FMP error.** `snapshot_date` is required for the sector P/E snapshot "
                    "(or provide `sector` + `from_date`/`to_date` for the historical series)."
                )
            params = {"date": snapshot_date}
            if exchange:
                params["exchange"] = exchange
            if sector:
                params["sector"] = sector
            data = await client.get("/stable/sector-pe-snapshot", params)
            return render_small_result(
                data, response_format, title=f"Sector P/E snapshot: {snapshot_date}", what="sector P/E"
            )
        except Exception as exc:
            return wrap_error(exc)
