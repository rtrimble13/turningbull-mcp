"""Typed wrappers for BEA's industry datasets.

Three tools: GDPbyIndustry, UnderlyingGDPbyIndustry, InputOutput.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import Frequency, OutputMode, ResponseFormat, YearSpec
from ..transform import flatten_data
from ._common import READ_ONLY, render_large_result, wrap_error


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="bea_get_gdp_by_industry",
        annotations=READ_ONLY,
        description=(
            "Fetch a GDPbyIndustry table. Returns value added, gross output, "
            "compensation, and price/quantity indexes broken down by NAICS "
            "industry. Tables: 1 (Value Added by Industry), 5 (Value Added "
            "as % of GDP), 6 (Components of Value Added), 8 (Quantity "
            "Indexes), 11 (Real Value Added), 15 (Gross Output). Set "
            "Industry='ALL' to get every NAICS sector at once."
        ),
    )
    async def bea_get_gdp_by_industry(
        table_id: Annotated[
            int,
            Field(description="GDPbyIndustry TableID (integer), e.g. 1 for Value Added by Industry."),
        ],
        frequency: Annotated[
            Frequency,
            Field(description="A (annual) or Q (quarterly)."),
        ],
        industry: Annotated[
            str,
            Field(
                default="ALL",
                description=(
                    "Industry code or 'ALL'. Multiple values allowed "
                    "(comma-separated). NAICS-aligned (e.g. 11 = Ag, "
                    "21 = Mining, 23 = Construction, 31G = Manufacturing)."
                ),
            ),
        ] = "ALL",
        year: Annotated[
            YearSpec,
            Field(default="LAST5", description="YYYY, comma list, or ALL/LAST5/LAST10/X."),
        ] = "LAST5",
        mode: Annotated[
            OutputMode,
            Field(description="inline (default) or summary."),
        ] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            params = {
                "TableID": table_id,
                "Frequency": frequency.value,
                "Industry": industry,
                "Year": year,
            }
            results = await get_client().call(
                "GetData", dataset="GDPbyIndustry", params=params
            )
            rows = flatten_data(results.get("Data") or [])
            return render_large_result(
                rows,
                name=f"bea_gdpbyind_{table_id}_{frequency.value}",
                mode=mode,
                fmt=response_format,
                title=f"GDPbyIndustry table {table_id} ({frequency.value})",
                what=f"GDPbyIndustry table {table_id}",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_get_underlying_gdp_by_industry",
        annotations=READ_ONLY,
        description=(
            "Fetch a UnderlyingGDPbyIndustry table — the finer industry "
            "breakdowns behind the headline GDPbyIndustry tables. Same "
            "parameter shape (TableID, Frequency, Industry, Year)."
        ),
    )
    async def bea_get_underlying_gdp_by_industry(
        table_id: Annotated[
            int,
            Field(description="UnderlyingGDPbyIndustry TableID (integer)."),
        ],
        frequency: Annotated[
            Frequency,
            Field(description="A (annual) or Q (quarterly)."),
        ],
        industry: Annotated[
            str,
            Field(default="ALL", description="Industry code or 'ALL'."),
        ] = "ALL",
        year: Annotated[
            YearSpec,
            Field(default="LAST5", description="YYYY, comma list, or ALL/LAST5/LAST10/X."),
        ] = "LAST5",
        mode: Annotated[
            OutputMode,
            Field(description="inline (default) or summary."),
        ] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            params = {
                "TableID": table_id,
                "Frequency": frequency.value,
                "Industry": industry,
                "Year": year,
            }
            results = await get_client().call(
                "GetData", dataset="UnderlyingGDPbyIndustry", params=params
            )
            rows = flatten_data(results.get("Data") or [])
            return render_large_result(
                rows,
                name=f"bea_ugdpbyind_{table_id}_{frequency.value}",
                mode=mode,
                fmt=response_format,
                title=f"UnderlyingGDPbyIndustry table {table_id} ({frequency.value})",
                what=f"UnderlyingGDPbyIndustry table {table_id}",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_get_input_output",
        annotations=READ_ONLY,
        description=(
            "Fetch an Input-Output table — supply-and-use, requirements, "
            "and impact tables that show how industries buy from and sell "
            "to each other. Annual. Required: TableID. Common tables: 56 "
            "(industry-by-commodity total requirements), 57 (commodity-by-"
            "industry), 63 (use of commodities by industries)."
        ),
    )
    async def bea_get_input_output(
        table_id: Annotated[
            int,
            Field(description="InputOutput TableID (integer)."),
        ],
        year: Annotated[
            YearSpec,
            Field(default="LAST5", description="YYYY, comma list, or ALL/LAST5/LAST10/X."),
        ] = "LAST5",
        mode: Annotated[
            OutputMode,
            Field(
                description=(
                    "inline (default) or summary. I-O tables can be wide; "
                    "use summary for full table pulls."
                )
            ),
        ] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            params = {"TableID": table_id, "Year": year}
            results = await get_client().call(
                "GetData", dataset="InputOutput", params=params
            )
            rows = flatten_data(results.get("Data") or [])
            return render_large_result(
                rows,
                name=f"bea_io_{table_id}",
                mode=mode,
                fmt=response_format,
                title=f"InputOutput table {table_id}",
                what=f"InputOutput table {table_id}",
            )
        except Exception as exc:
            return wrap_error(exc)
