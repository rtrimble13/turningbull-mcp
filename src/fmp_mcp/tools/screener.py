"""Stock / fund screener tool."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import OutputMode, ResponseFormat
from ._common import READ_ONLY, render_large_result, wrap_error


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fmp_screen_stocks",
        annotations=READ_ONLY,
        description=(
            "Company / fund / ETF screener. All filters optional; only set "
            "parameters are forwarded. Returns rows of {symbol, companyName, "
            "marketCap, sector, industry, beta, price, lastAnnualDividend, "
            "volume, exchange, exchangeShortName, country, isEtf, isFund, "
            "isActivelyTrading}. Note parameter spellings: "
            "`marketCapLowerThan` not `LessThan`, `period=quarter` not "
            "`quarterly` (where applicable)."
        ),
    )
    async def fmp_screen_stocks(
        sector: Annotated[str | None, Field(description="Sector name. See fmp_list_sectors.")] = None,
        industry: Annotated[str | None, Field(description="Industry name. See fmp_list_industries.")] = None,
        country: Annotated[str | None, Field(description="ISO-2 country code, e.g. US.")] = None,
        exchange: Annotated[str | None, Field(description="Exchange code, e.g. NASDAQ.")] = None,
        market_cap_more_than: Annotated[
            float | None, Field(description="Min market cap (USD).")
        ] = None,
        market_cap_lower_than: Annotated[
            float | None, Field(description="Max market cap (USD).")
        ] = None,
        price_more_than: Annotated[float | None, Field(description="Min price.")] = None,
        price_lower_than: Annotated[float | None, Field(description="Max price.")] = None,
        beta_more_than: Annotated[float | None, Field(description="Min beta.")] = None,
        beta_lower_than: Annotated[float | None, Field(description="Max beta.")] = None,
        volume_more_than: Annotated[int | None, Field(description="Min volume.")] = None,
        volume_lower_than: Annotated[int | None, Field(description="Max volume.")] = None,
        dividend_more_than: Annotated[float | None, Field(description="Min last annual dividend.")] = None,
        dividend_lower_than: Annotated[float | None, Field(description="Max last annual dividend.")] = None,
        is_etf: Annotated[bool | None, Field(description="Restrict to ETFs (true) or non-ETFs (false).")] = None,
        is_fund: Annotated[bool | None, Field(description="Restrict to funds.")] = None,
        is_actively_trading: Annotated[bool | None, Field(description="Restrict to actively-trading symbols.")] = None,
        include_all_share_classes: Annotated[
            bool | None, Field(description="If true, return all share classes for a name.")
        ] = None,
        limit: Annotated[int, Field(ge=1, le=10000, description="Max rows to return.")] = 100,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            params: dict[str, object] = {"limit": limit}
            mapping: dict[str, object | None] = {
                "sector": sector,
                "industry": industry,
                "country": country,
                "exchange": exchange,
                "marketCapMoreThan": market_cap_more_than,
                "marketCapLowerThan": market_cap_lower_than,
                "priceMoreThan": price_more_than,
                "priceLowerThan": price_lower_than,
                "betaMoreThan": beta_more_than,
                "betaLowerThan": beta_lower_than,
                "volumeMoreThan": volume_more_than,
                "volumeLowerThan": volume_lower_than,
                "dividendMoreThan": dividend_more_than,
                "dividendLowerThan": dividend_lower_than,
                "isEtf": is_etf,
                "isFund": is_fund,
                "isActivelyTrading": is_actively_trading,
                "includeAllShareClasses": include_all_share_classes,
            }
            for k, v in mapping.items():
                if v is not None:
                    params[k] = v

            data = await client.get("/stable/company-screener", params)
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"screener_l{limit}",
                mode=mode,
                fmt=response_format,
                title="Screener results",
                what="screener",
            )
        except Exception as exc:
            return wrap_error(exc)
