"""Generic BEA data fetch — the escape hatch.

When the typed per-dataset wrappers in ``national.py`` / ``international.py``
/ ``industry.py`` / ``regional.py`` don't cleanly fit, ``bea_get_data``
accepts an arbitrary parameter dict for any dataset.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import BEADataset, OutputMode, ResponseFormat
from ..transform import flatten_data
from ._common import READ_ONLY, render_large_result, wrap_error


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="bea_get_data",
        annotations=READ_ONLY,
        description=(
            "Generic GetData call against any BEA dataset. Pass the "
            "dataset-specific parameters as a dict (look them up with "
            "bea_list_parameters / bea_list_parameter_values first). "
            "Returns the BEA Data rows with `date` (ISO) and `value` "
            "(numeric) added alongside the original fields. Use "
            "mode=summary for large pulls — they get written to CSV+Parquet "
            "under $BEA_OUTPUT_DIR and the response includes a digest."
        ),
    )
    async def bea_get_data(
        dataset: Annotated[
            BEADataset,
            Field(description="BEA dataset name (e.g. NIPA, Regional, ITA)."),
        ],
        params: Annotated[
            dict[str, Any],
            Field(
                description=(
                    "Dataset-specific parameters. Examples: NIPA → "
                    "{TableName: T10101, Frequency: Q, Year: LAST5}; "
                    "Regional → {TableName: CAINC4, LineCode: 1, "
                    "GeoFips: STATE, Year: 2023}; GDPbyIndustry → "
                    "{TableID: 1, Frequency: A, Industry: ALL, "
                    "Year: LAST5}. Values may be strings, ints, or lists "
                    "(lists are joined with commas)."
                )
            ),
        ],
        mode: Annotated[
            OutputMode,
            Field(
                description=(
                    "inline (default) returns rows in the response; summary "
                    "writes to CSV+Parquet under $BEA_OUTPUT_DIR and returns "
                    "a file digest."
                )
            ),
        ] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            results = await get_client().call(
                "GetData",
                dataset=dataset.value,
                params=params,
            )
            data = results.get("Data") or []
            if not isinstance(data, list):
                data = [data]
            rows = flatten_data(data)
            safe_params = "_".join(
                f"{k}={v}" for k, v in list(params.items())[:3]
            )[:80]
            return render_large_result(
                rows,
                name=f"bea_{dataset.value}_{safe_params}",
                mode=mode,
                fmt=response_format,
                title=f"BEA {dataset.value} ({len(rows)} rows)",
                what=f"{dataset.value} {params}",
            )
        except Exception as exc:
            return wrap_error(exc)
