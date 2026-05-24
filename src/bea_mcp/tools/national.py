"""Typed wrappers for BEA's national-accounts datasets.

Three tools — one per dataset — that take only the parameters the dataset
actually accepts and forward to GetData. Big NIPA pulls (Year=ALL on a
monthly table) easily produce 5k+ rows; default to mode=summary then.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import (
    Frequency,
    OptionalYearSpec,
    OutputMode,
    ResponseFormat,
    TableName,
    YearSpec,
)
from ..transform import flatten_data
from ._common import READ_ONLY, render_large_result, wrap_error


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="bea_get_nipa",
        annotations=READ_ONLY,
        description=(
            "Fetch a NIPA (National Income and Product Accounts) table. "
            "Covers GDP, personal income, PCE, corporate profits, government "
            "receipts/expenditures, foreign transactions. Common tables: "
            "T10101 (% change real GDP), T10102 (contributions to GDP "
            "growth), T10105 (GDP current $), T20100 (personal income), "
            "T20600 (personal income, monthly), T20305 (PCE by product), "
            "T11400 (corporate profits). Use bea_search_tables or "
            "bea_list_parameter_values(NIPA, 'TableName') for the full list."
        ),
    )
    async def bea_get_nipa(
        table_name: Annotated[
            TableName,
            Field(description="NIPA TableName, e.g. T10101."),
        ],
        frequency: Annotated[
            Frequency,
            Field(description="A (annual), Q (quarterly), or M (monthly; subset of tables)."),
        ],
        year: Annotated[
            YearSpec,
            Field(
                default="LAST10",
                description=(
                    "YYYY, comma list, or ALL/LAST5/LAST10/X. Defaults to "
                    "LAST10 for a reasonable history window."
                ),
            ),
        ] = "LAST10",
        show_millions: Annotated[
            bool,
            Field(
                default=False,
                description=(
                    "If true (and supported by the table), return values in "
                    "millions of dollars instead of the table's default unit."
                ),
            ),
        ] = False,
        mode: Annotated[
            OutputMode,
            Field(
                description=(
                    "inline (default) returns the rows; summary writes to "
                    "CSV+Parquet under $BEA_OUTPUT_DIR."
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
                "Frequency": frequency.value,
                "Year": year,
            }
            if show_millions:
                params["ShowMillions"] = "Y"
            results = await get_client().call("GetData", dataset="NIPA", params=params)
            rows = flatten_data(results.get("Data") or [])
            return render_large_result(
                rows,
                name=f"bea_nipa_{table_name}_{frequency.value}",
                mode=mode,
                fmt=response_format,
                title=f"NIPA {table_name} ({frequency.value})",
                what=f"NIPA {table_name}",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_get_ni_underlying_detail",
        annotations=READ_ONLY,
        description=(
            "Fetch a NIUnderlyingDetail table — the deeper line-item "
            "breakdowns behind the headline NIPA tables (e.g. detailed PCE "
            "by sub-category, detailed investment by asset type). Use "
            "bea_list_parameter_values(NIUnderlyingDetail, 'TableName') for "
            "the full list."
        ),
    )
    async def bea_get_ni_underlying_detail(
        table_name: Annotated[
            TableName,
            Field(description="NIUnderlyingDetail TableName, e.g. U70405."),
        ],
        frequency: Annotated[
            Frequency,
            Field(description="A (annual), Q (quarterly), or M (monthly)."),
        ],
        year: Annotated[
            YearSpec,
            Field(default="LAST10", description="YYYY, comma list, or ALL/LAST5/LAST10/X."),
        ] = "LAST10",
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
                "TableName": table_name,
                "Frequency": frequency.value,
                "Year": year,
            }
            results = await get_client().call(
                "GetData", dataset="NIUnderlyingDetail", params=params
            )
            rows = flatten_data(results.get("Data") or [])
            return render_large_result(
                rows,
                name=f"bea_niud_{table_name}_{frequency.value}",
                mode=mode,
                fmt=response_format,
                title=f"NIUnderlyingDetail {table_name} ({frequency.value})",
                what=f"NIUnderlyingDetail {table_name}",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_get_fixed_assets",
        annotations=READ_ONLY,
        description=(
            "Fetch a FixedAssets table — the stock and depreciation of "
            "tangible fixed assets and consumer durable goods. Tables are "
            "annual. Common: FAAt101 (net stock, current cost), FAAt201 "
            "(depreciation). Use bea_list_parameter_values(FixedAssets, "
            "'TableName') for the full list."
        ),
    )
    async def bea_get_fixed_assets(
        table_name: Annotated[
            TableName,
            Field(description="FixedAssets TableName, e.g. FAAt101."),
        ],
        year: Annotated[
            OptionalYearSpec,
            Field(
                default="ALL",
                description="YYYY, comma list, or ALL/LAST5/LAST10/X. Defaults to ALL.",
            ),
        ] = "ALL",
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
            params = {"TableName": table_name, "Year": year}
            results = await get_client().call(
                "GetData", dataset="FixedAssets", params=params
            )
            rows = flatten_data(results.get("Data") or [])
            return render_large_result(
                rows,
                name=f"bea_fixedassets_{table_name}",
                mode=mode,
                fmt=response_format,
                title=f"FixedAssets {table_name}",
                what=f"FixedAssets {table_name}",
            )
        except Exception as exc:
            return wrap_error(exc)
