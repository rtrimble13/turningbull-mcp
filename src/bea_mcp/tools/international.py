"""Typed wrappers for BEA's international datasets.

Five tools: ITA (transactions), IIP (investment position), IntlServTrade,
IntlServSTA, MNE (multinational enterprises).
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
        name="bea_get_ita",
        annotations=READ_ONLY,
        description=(
            "Fetch International Transactions Accounts (ITA) data — the US "
            "balance of payments. Indicators include BalCurrAcct (current "
            "account), BalGds (goods), BalServ (services), BalGdsServ "
            "(goods+services), BalSecondaryInc (current transfers), and "
            "dozens of disaggregated trade/income flows. Use "
            "bea_list_parameter_values(ITA, 'Indicator') for the full list."
        ),
    )
    async def bea_get_ita(
        indicator: Annotated[
            str,
            Field(
                default="BalCurrAcct",
                description=(
                    "ITA Indicator name (e.g. BalCurrAcct, BalGds, BalServ). "
                    "Use ALL for every indicator (large response)."
                ),
            ),
        ] = "BalCurrAcct",
        area_or_country: Annotated[
            str,
            Field(
                default="AllCountries",
                description=(
                    "AreaOrCountry name (e.g. AllCountries, China, "
                    "EuropeanUnion, Mexico)."
                ),
            ),
        ] = "AllCountries",
        frequency: Annotated[
            Frequency,
            Field(description="A (annual) or Q (quarterly)."),
        ] = Frequency.A,
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
                "Indicator": indicator,
                "AreaOrCountry": area_or_country,
                "Frequency": frequency.value,
                "Year": year,
            }
            results = await get_client().call("GetData", dataset="ITA", params=params)
            rows = flatten_data(results.get("Data") or [])
            return render_large_result(
                rows,
                name=f"bea_ita_{indicator}_{area_or_country}_{frequency.value}",
                mode=mode,
                fmt=response_format,
                title=f"ITA {indicator} ({area_or_country}, {frequency.value})",
                what=f"ITA {indicator}",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_get_iip",
        annotations=READ_ONLY,
        description=(
            "Fetch International Investment Position (IIP) data — the "
            "stock of US assets abroad and foreign assets in the US "
            "(securities, FDI, reserves, etc.). Common TypeOfInvestment: "
            "IIPNetPos (net position), USAssets, USLiab. Components: All, "
            "ChgPos (change), etc."
        ),
    )
    async def bea_get_iip(
        type_of_investment: Annotated[
            str,
            Field(
                default="All",
                description=(
                    "IIP TypeOfInvestment, e.g. IIPNetPos, USAssets, "
                    "USLiab, or 'All'."
                ),
            ),
        ] = "All",
        component: Annotated[
            str,
            Field(
                default="All",
                description="Component, e.g. ChgPos, Pos, or 'All'.",
            ),
        ] = "All",
        frequency: Annotated[
            Frequency,
            Field(description="A (annual) or Q (quarterly)."),
        ] = Frequency.A,
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
                "TypeOfInvestment": type_of_investment,
                "Component": component,
                "Frequency": frequency.value,
                "Year": year,
            }
            results = await get_client().call("GetData", dataset="IIP", params=params)
            rows = flatten_data(results.get("Data") or [])
            return render_large_result(
                rows,
                name=f"bea_iip_{type_of_investment}_{frequency.value}",
                mode=mode,
                fmt=response_format,
                title=f"IIP {type_of_investment} ({frequency.value})",
                what=f"IIP {type_of_investment}",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_get_intl_serv_trade",
        annotations=READ_ONLY,
        description=(
            "Fetch International Services Trade (IntlServTrade) data — "
            "US exports and imports of services by type (travel, "
            "transport, financial services, intellectual property, etc.) "
            "and partner country. Annual data."
        ),
    )
    async def bea_get_intl_serv_trade(
        type_of_service: Annotated[
            str,
            Field(default="AllServiceTypes", description="Service category or AllServiceTypes."),
        ] = "AllServiceTypes",
        trade_direction: Annotated[
            str,
            Field(
                default="Balance",
                description="Balance, Exports, Imports, or All.",
            ),
        ] = "Balance",
        affiliation: Annotated[
            str,
            Field(
                default="AllAffiliations",
                description="Affiliated, Unaffiliated, or AllAffiliations.",
            ),
        ] = "AllAffiliations",
        area_or_country: Annotated[
            str,
            Field(default="AllCountries", description="Partner country or AllCountries."),
        ] = "AllCountries",
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
                "TypeOfService": type_of_service,
                "TradeDirection": trade_direction,
                "Affiliation": affiliation,
                "AreaOrCountry": area_or_country,
                "Year": year,
            }
            results = await get_client().call(
                "GetData", dataset="IntlServTrade", params=params
            )
            rows = flatten_data(results.get("Data") or [])
            return render_large_result(
                rows,
                name=f"bea_intlservtrade_{type_of_service}_{trade_direction}",
                mode=mode,
                fmt=response_format,
                title=f"IntlServTrade {type_of_service} ({trade_direction})",
                what=f"IntlServTrade {type_of_service}",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_get_intl_serv_sta",
        annotations=READ_ONLY,
        description=(
            "Fetch International Services Supplied Through Affiliates "
            "(IntlServSTA) data — services supplied by majority-owned "
            "affiliates of US MNEs abroad and foreign MNEs in the US."
        ),
    )
    async def bea_get_intl_serv_sta(
        channel: Annotated[
            str,
            Field(default="All", description="Channel of supply or 'All'."),
        ] = "All",
        destination: Annotated[
            str,
            Field(default="All", description="Destination country or 'All'."),
        ] = "All",
        industry: Annotated[
            str,
            Field(default="All", description="Industry of affiliate or 'All'."),
        ] = "All",
        area_or_country: Annotated[
            str,
            Field(default="AllCountries", description="Partner country or AllCountries."),
        ] = "AllCountries",
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
                "Channel": channel,
                "Destination": destination,
                "Industry": industry,
                "AreaOrCountry": area_or_country,
                "Year": year,
            }
            results = await get_client().call(
                "GetData", dataset="IntlServSTA", params=params
            )
            rows = flatten_data(results.get("Data") or [])
            return render_large_result(
                rows,
                name=f"bea_intlservsta_{channel}_{industry}",
                mode=mode,
                fmt=response_format,
                title=f"IntlServSTA {channel} ({industry})",
                what=f"IntlServSTA {channel}",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_get_mne",
        annotations=READ_ONLY,
        description=(
            "Fetch Multinational Enterprises (MNE) data — activities of US "
            "MNEs abroad and foreign MNEs in the US (sales, employment, "
            "assets, R&D). Many parameters; pass them via the typed args "
            "or fall back to bea_get_data for unusual combos. Use "
            "bea_list_parameter_values(MNE, ...) to discover values."
        ),
    )
    async def bea_get_mne(
        direction_of_investment: Annotated[
            str,
            Field(
                default="outward",
                description=(
                    "'outward' = US-owned foreign affiliates; "
                    "'inward' = foreign-owned US affiliates; 'parent'/'state'."
                ),
            ),
        ] = "outward",
        ownership_level: Annotated[
            str,
            Field(
                default="0",
                description=(
                    "Ownership threshold: 0 = all affiliates, 1 = "
                    "majority-owned only."
                ),
            ),
        ] = "0",
        classification: Annotated[
            str,
            Field(
                default="Country",
                description=(
                    "Classification dimension: Country, Industry, "
                    "CountryByIndustry, IndustryByCountry, or State (for "
                    "direction=state)."
                ),
            ),
        ] = "Country",
        series_id: Annotated[
            str,
            Field(
                default="ALL",
                description=(
                    "MNE SeriesID (e.g. 8 = sales, 12 = compensation, "
                    "20 = employment) or 'ALL'."
                ),
            ),
        ] = "ALL",
        country: Annotated[
            str,
            Field(default="ALL", description="Partner country code or 'ALL'."),
        ] = "ALL",
        industry: Annotated[
            str,
            Field(default="ALL", description="Industry code or 'ALL'."),
        ] = "ALL",
        state: Annotated[
            str,
            Field(default="ALL", description="State (for direction=state) or 'ALL'."),
        ] = "ALL",
        non_bank_affiliates_only: Annotated[
            bool,
            Field(default=False, description="If true, exclude bank affiliates."),
        ] = False,
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
                "DirectionOfInvestment": direction_of_investment,
                "OwnershipLevel": ownership_level,
                "Classification": classification,
                "SeriesID": series_id,
                "Country": country,
                "Industry": industry,
                "State": state,
                "NonbankAffiliatesOnly": "1" if non_bank_affiliates_only else "0",
                "Year": year,
            }
            results = await get_client().call("GetData", dataset="MNE", params=params)
            rows = flatten_data(results.get("Data") or [])
            return render_large_result(
                rows,
                name=f"bea_mne_{direction_of_investment}_{classification}_{series_id}",
                mode=mode,
                fmt=response_format,
                title=f"MNE {direction_of_investment} ({classification})",
                what=f"MNE {direction_of_investment}",
            )
        except Exception as exc:
            return wrap_error(exc)
