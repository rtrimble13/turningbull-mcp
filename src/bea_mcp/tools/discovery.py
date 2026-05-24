"""BEA discovery tools.

Four thin wrappers around BEA's meta methods (``GetDataSetList``,
``GetParameterList``, ``GetParameterValues``, ``GetParameterValuesFiltered``)
that let the model learn the API surface at runtime, plus a pure-local
``bea_search_tables`` over the embedded ``POPULAR_TABLES`` catalog.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..catalog import POPULAR_TABLES, search_tables
from ..client import get_client
from ..models import BEADataset, ResponseFormat
from ._common import READ_ONLY, render_small_result, wrap_error


def _coerce_list(node: Any) -> list[dict[str, Any]]:
    """BEA returns single-element results as a dict and multi-element as a
    list. Normalize to a list for uniform downstream handling.
    """
    if node is None:
        return []
    if isinstance(node, list):
        return [x for x in node if isinstance(x, dict)]
    if isinstance(node, dict):
        return [node]
    return []


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="bea_list_datasets",
        annotations=READ_ONLY,
        description=(
            "List all BEA datasets exposed by the API. Returns "
            "[{DatasetName, DatasetDescription}] for ~13 datasets including "
            "NIPA (national accounts), Regional (state/county), GDPbyIndustry, "
            "FixedAssets, ITA (international transactions), IIP (intl "
            "investment position), InputOutput, IntlServTrade, IntlServSTA, "
            "MNE, NIUnderlyingDetail, UnderlyingGDPbyIndustry, "
            "APIDatasetMetaData. Calls method=GetDataSetList."
        ),
    )
    async def bea_list_datasets(
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            results = await get_client().call("GetDataSetList")
            datasets = _coerce_list(results.get("Dataset"))
            return render_small_result(
                datasets,
                response_format,
                title="BEA datasets",
                what="BEA dataset list",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_list_parameters",
        annotations=READ_ONLY,
        description=(
            "List the parameters (required + optional) accepted by a given "
            "BEA dataset. Returns [{ParameterName, ParameterDataType, "
            "ParameterDescription, ParameterIsRequiredFlag, "
            "ParameterDefaultValue, MultipleAcceptedFlag, AllValue}]. Use "
            "this before calling bea_get_data on an unfamiliar dataset. "
            "Calls method=GetParameterList."
        ),
    )
    async def bea_list_parameters(
        dataset: Annotated[
            BEADataset,
            Field(description="BEA dataset name (e.g. NIPA, Regional, GDPbyIndustry)."),
        ],
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            results = await get_client().call(
                "GetParameterList", dataset=dataset.value
            )
            params = _coerce_list(results.get("Parameter"))
            return render_small_result(
                params,
                response_format,
                title=f"BEA parameters for {dataset.value}",
                what=f"{dataset.value} parameters",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_list_parameter_values",
        annotations=READ_ONLY,
        description=(
            "List every valid value for one parameter of one dataset. E.g. "
            "all TableName values in NIPA, all GeoFips codes in Regional, "
            "all Industry codes in GDPbyIndustry. Useful for discovering the "
            "exact ID to pass to a typed tool. Calls "
            "method=GetParameterValues."
        ),
    )
    async def bea_list_parameter_values(
        dataset: Annotated[
            BEADataset,
            Field(description="BEA dataset name."),
        ],
        parameter: Annotated[
            str,
            Field(
                description=(
                    "Parameter name as returned by bea_list_parameters "
                    "(e.g. TableName, Frequency, Year, GeoFips, LineCode, "
                    "TableID, Industry, Indicator, AreaOrCountry)."
                )
            ),
        ],
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            results = await get_client().call(
                "GetParameterValues",
                dataset=dataset.value,
                params={"ParameterName": parameter},
            )
            values = _coerce_list(results.get("ParamValue")) or _coerce_list(
                results.get("_list")
            )
            return render_small_result(
                values,
                response_format,
                title=f"{dataset.value}.{parameter} values",
                what=f"{dataset.value}.{parameter}",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_list_parameter_values_filtered",
        annotations=READ_ONLY,
        description=(
            "Return valid values for one target parameter, constrained by "
            "the values of other parameters. E.g. 'what Years are available "
            "for NIPA TableName=T10101?' or 'what LineCodes exist for "
            "Regional TableName=CAINC4?'. Strict subset of "
            "bea_list_parameter_values when filters are supplied. Calls "
            "method=GetParameterValuesFiltered."
        ),
    )
    async def bea_list_parameter_values_filtered(
        dataset: Annotated[
            BEADataset,
            Field(description="BEA dataset name."),
        ],
        target_parameter: Annotated[
            str,
            Field(description="Parameter whose valid values you want returned."),
        ],
        filters: Annotated[
            dict[str, Any] | None,
            Field(
                default=None,
                description=(
                    "Map of {parameter_name: value} to constrain the result. "
                    "E.g. {'TableName': 'T10101', 'Frequency': 'Q'} when "
                    "asking which Year values exist for that NIPA table."
                ),
            ),
        ] = None,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            params: dict[str, Any] = {"TargetParameter": target_parameter}
            if filters:
                params.update(filters)
            results = await get_client().call(
                "GetParameterValuesFiltered",
                dataset=dataset.value,
                params=params,
            )
            values = _coerce_list(results.get("ParamValue")) or _coerce_list(
                results.get("_list")
            )
            return render_small_result(
                values,
                response_format,
                title=f"{dataset.value}.{target_parameter} (filtered)",
                what=f"{dataset.value}.{target_parameter}",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_search_tables",
        annotations=READ_ONLY,
        description=(
            "Search the embedded catalog of popular BEA tables (~45 entries "
            "spanning NIPA, FixedAssets, Regional, GDPbyIndustry, "
            "InputOutput, ITA, IIP). Pure local — no API key needed, no "
            "HTTP call. Returns ranked [{dataset, table, title, freq}]. For "
            "the full table inventory of a dataset, call "
            "bea_list_parameter_values(dataset, 'TableName' or 'TableID')."
        ),
    )
    async def bea_search_tables(
        query: Annotated[
            str,
            Field(
                description=(
                    "Free-text query, e.g. 'real GDP' or 'state personal "
                    "income' or 'current account'."
                )
            ),
        ] = "",
        dataset: Annotated[
            BEADataset | None,
            Field(default=None, description="Optionally restrict to one dataset."),
        ] = None,
        limit: Annotated[
            int,
            Field(default=25, ge=1, le=100, description="Max results to return."),
        ] = 25,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            if not query.strip() and dataset is None:
                hits = list(POPULAR_TABLES[:limit])
            else:
                hits = search_tables(
                    query,
                    dataset=dataset.value if dataset else None,
                    limit=limit,
                )
            return render_small_result(
                hits,
                response_format,
                title=f"BEA popular tables ({len(hits)})",
                what="popular table search",
            )
        except Exception as exc:
            return wrap_error(exc)
