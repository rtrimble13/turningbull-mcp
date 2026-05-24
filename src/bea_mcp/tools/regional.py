"""Typed wrapper for BEA's Regional dataset.

State, county, MSA-level GDP, personal income, employment, and population.
Required parameters: TableName, LineCode, GeoFips, Year.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import GeoFips, OutputMode, ResponseFormat, TableName, YearSpec
from ..transform import flatten_data
from ._common import READ_ONLY, render_large_result, wrap_error


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="bea_get_regional",
        annotations=READ_ONLY,
        description=(
            "Fetch a Regional table — state, county, MSA, or BEA region "
            "data. Required: TableName (e.g. CAINC4 personal income, "
            "SAGDP1 state GDP summary, SAGDP9N real GDP, SAEMP25N "
            "employment, CAINC1 county personal income), LineCode (the "
            "row within the table — e.g. 1 = personal income), GeoFips "
            "(5-digit FIPS, comma list, or token like STATE/COUNTY/MSA). "
            "Use bea_list_parameter_values(Regional, 'TableName') and "
            "bea_list_parameter_values_filtered(Regional, 'LineCode', "
            "{TableName: ...}) to discover valid IDs."
        ),
    )
    async def bea_get_regional(
        table_name: Annotated[
            TableName,
            Field(description="Regional TableName, e.g. CAINC4 or SAGDP9N."),
        ],
        line_code: Annotated[
            int,
            Field(
                description=(
                    "Row in the table — every cell type (e.g. 1 = personal "
                    "income, 2 = population, 3 = per-capita income). Get "
                    "valid codes via bea_list_parameter_values_filtered."
                )
            ),
        ],
        geo_fips: Annotated[
            GeoFips,
            Field(
                description=(
                    "Geographic identifier. 5-digit FIPS (06000 = California), "
                    "comma list, or token STATE/COUNTY/MSA/CSA."
                )
            ),
        ],
        year: Annotated[
            YearSpec,
            Field(
                default="LAST10",
                description="YYYY, comma list, or ALL/LAST5/LAST10/X.",
            ),
        ] = "LAST10",
        mode: Annotated[
            OutputMode,
            Field(
                description=(
                    "inline (default) or summary. Use summary when you ask "
                    "for COUNTY level — there are 3000+ counties."
                )
            ),
        ] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            params = {
                "TableName": table_name,
                "LineCode": line_code,
                "GeoFips": geo_fips,
                "Year": year,
            }
            results = await get_client().call(
                "GetData", dataset="Regional", params=params
            )
            rows = flatten_data(results.get("Data") or [])
            return render_large_result(
                rows,
                name=f"bea_regional_{table_name}_L{line_code}_{geo_fips[:20]}",
                mode=mode,
                fmt=response_format,
                title=f"Regional {table_name} L{line_code} ({geo_fips})",
                what=f"Regional {table_name} L{line_code}",
            )
        except Exception as exc:
            return wrap_error(exc)
