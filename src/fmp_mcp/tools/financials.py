"""Financial statement tools: income, balance sheet, cash flow, ratios, key metrics."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import (
    OutputMode,
    Period,
    ResponseFormat,
    SegmentationStructure,
    Symbol,
)
from ._common import READ_ONLY, render_large_result, wrap_error


async def _fetch_statement(
    path: str, symbol: str, period: Period, limit: int
) -> list[dict]:
    client = get_client()
    data = await client.get(
        path,
        {"symbol": symbol, "period": period.value, "limit": limit},
    )
    return data if isinstance(data, list) else []


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="fmp_get_income_statement",
        annotations=READ_ONLY,
        description=(
            "Income statement periods. Returns per-period rows with revenue, "
            "costOfRevenue, grossProfit, grossProfitRatio, operatingIncome, "
            "interestExpense, incomeBeforeTax, incomeTaxExpense, netIncome, "
            "eps, epsdiluted, weightedAverageShsOut, etc. `period` must be "
            "'annual' or 'quarter' (or Q1/Q2/Q3/Q4)."
        ),
    )
    async def fmp_get_income_statement(
        symbol: Annotated[Symbol, Field(description="Ticker, e.g. AAPL.")],
        period: Annotated[
            Period, Field(description="annual or quarter (or Q1..Q4).")
        ] = Period.annual,
        limit: Annotated[
            int, Field(ge=1, le=120, description="Max periods to return.")
        ] = 10,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            rows = await _fetch_statement(
                "/stable/income-statement", symbol, period, limit
            )
            return render_large_result(
                rows,
                name=f"{symbol}_income_{period.value}_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Income statement ({period.value}): {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_balance_sheet",
        annotations=READ_ONLY,
        description=(
            "Balance sheet periods. Returns cashAndCashEquivalents, "
            "shortTermInvestments, inventory, totalCurrentAssets, "
            "propertyPlantEquipmentNet, goodwill, intangibleAssets, totalAssets, "
            "accountPayables, shortTermDebt, longTermDebt, totalLiabilities, "
            "commonStock, retainedEarnings, totalStockholdersEquity, totalDebt, "
            "netDebt, etc."
        ),
    )
    async def fmp_get_balance_sheet(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        period: Annotated[Period, Field(description="annual or quarter.")] = Period.annual,
        limit: Annotated[int, Field(ge=1, le=120)] = 10,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            rows = await _fetch_statement(
                "/stable/balance-sheet-statement", symbol, period, limit
            )
            return render_large_result(
                rows,
                name=f"{symbol}_balance_{period.value}_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Balance sheet ({period.value}): {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_cash_flow",
        annotations=READ_ONLY,
        description=(
            "Cash flow statement periods. Returns netIncome, "
            "depreciationAndAmortization, stockBasedCompensation, "
            "changeInWorkingCapital, netCashProvidedByOperatingActivities, "
            "investmentsInPropertyPlantAndEquipment, dividendsPaid, "
            "commonStockRepurchased, freeCashFlow, capitalExpenditure, etc."
        ),
    )
    async def fmp_get_cash_flow(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        period: Annotated[Period, Field(description="annual or quarter.")] = Period.annual,
        limit: Annotated[int, Field(ge=1, le=120)] = 10,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            rows = await _fetch_statement(
                "/stable/cashflow-statement", symbol, period, limit
            )
            return render_large_result(
                rows,
                name=f"{symbol}_cashflow_{period.value}_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Cash flow ({period.value}): {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_financial_ratios",
        annotations=READ_ONLY,
        description=(
            "Period-by-period financial ratios: currentRatio, quickRatio, "
            "grossProfitMargin, operatingProfitMargin, netProfitMargin, "
            "returnOnAssets, returnOnEquity, returnOnCapitalEmployed, debtRatio, "
            "debtEquityRatio, priceEarningsRatio, priceToBookRatio, "
            "priceToSalesRatio, dividendYield, etc."
        ),
    )
    async def fmp_get_financial_ratios(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        period: Annotated[Period, Field(description="annual or quarter.")] = Period.annual,
        limit: Annotated[int, Field(ge=1, le=120)] = 10,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            rows = await _fetch_statement(
                "/stable/ratios", symbol, period, limit
            )
            return render_large_result(
                rows,
                name=f"{symbol}_ratios_{period.value}_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Ratios ({period.value}): {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_key_metrics",
        annotations=READ_ONLY,
        description=(
            "Pre-computed valuation/return key metrics by period: peRatio, "
            "pbRatio, priceToSalesRatio, enterpriseValue, "
            "enterpriseValueOverEBITDA, evToFreeCashFlow, earningsYield, "
            "freeCashFlowYield, debtToEquity, netDebtToEBITDA, currentRatio, "
            "interestCoverage, dividendYield, payoutRatio, roic, grahamNumber, "
            "workingCapital, investedCapital, revenuePerShare, "
            "freeCashFlowPerShare, bookValuePerShare, etc."
        ),
    )
    async def fmp_get_key_metrics(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        period: Annotated[Period, Field(description="annual or quarter.")] = Period.annual,
        limit: Annotated[int, Field(ge=1, le=120)] = 10,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[ResponseFormat, Field(description="markdown or json.")] = ResponseFormat.markdown,
    ) -> str:
        try:
            rows = await _fetch_statement(
                "/stable/key-metrics", symbol, period, limit
            )
            return render_large_result(
                rows,
                name=f"{symbol}_keymetrics_{period.value}_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Key metrics ({period.value}): {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_financial_growth",
        annotations=READ_ONLY,
        description=(
            "Period-over-period growth rates for every income statement, "
            "balance sheet, and cash flow line. Returns growthRevenue, "
            "growthGrossProfit, growthNetIncome, growthEPS, growthOperatingCashFlow, "
            "growthFreeCashFlow, etc. Saves recomputing YoY/QoQ growth by hand."
        ),
    )
    async def fmp_get_financial_growth(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        period: Annotated[Period, Field(description="annual or quarter.")] = Period.annual,
        limit: Annotated[int, Field(ge=1, le=120)] = 10,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            rows = await _fetch_statement(
                "/stable/financial-growth", symbol, period, limit
            )
            return render_large_result(
                rows,
                name=f"{symbol}_growth_{period.value}_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Financial growth ({period.value}): {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_enterprise_values",
        annotations=READ_ONLY,
        description=(
            "Enterprise value time series: {date, stockPrice, "
            "numberOfShares, marketCapitalization, minusCashAndCashEquivalents, "
            "addTotalDebt, enterpriseValue}. Useful for EV-based valuation and "
            "computing EV/EBITDA, EV/FCF over time."
        ),
    )
    async def fmp_get_enterprise_values(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        period: Annotated[Period, Field(description="annual or quarter.")] = Period.annual,
        limit: Annotated[int, Field(ge=1, le=120)] = 10,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            rows = await _fetch_statement(
                "/stable/enterprise-values", symbol, period, limit
            )
            return render_large_result(
                rows,
                name=f"{symbol}_ev_{period.value}_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Enterprise value ({period.value}): {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_owner_earnings",
        annotations=READ_ONLY,
        description=(
            "Buffett-style owner earnings: net income + D&A - maintenance "
            "CapEx + change in WC. Returns {symbol, date, period, "
            "ownersEarnings, averagePPE, maintenanceCapex, "
            "ownersEarningsPerShare}. Useful for cash-yield valuation."
        ),
    )
    async def fmp_get_owner_earnings(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        limit: Annotated[int, Field(ge=1, le=120)] = 10,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/owner-earnings",
                {"symbol": symbol, "limit": limit},
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_owner_earnings_l{limit}",
                mode=mode,
                fmt=response_format,
                title=f"Owner earnings: {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_revenue_product_segmentation",
        annotations=READ_ONLY,
        description=(
            "Revenue decomposition by product line / service for a symbol. "
            "Returns per-period dicts mapping segment name → revenue. "
            "Reveals growth drivers and segment mix shifts. structure='flat' "
            "returns one row per period with flattened columns; "
            "structure='grouped' preserves FMP's nested shape."
        ),
    )
    async def fmp_get_revenue_product_segmentation(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        period: Annotated[Period, Field(description="annual or quarter.")] = Period.annual,
        structure: Annotated[
            SegmentationStructure,
            Field(description="flat (default) or grouped."),
        ] = SegmentationStructure.flat,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/revenue-product-segmentation",
                {
                    "symbol": symbol,
                    "period": period.value,
                    "structure": structure.value,
                },
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_revenue_product_{period.value}",
                mode=mode,
                fmt=response_format,
                title=f"Revenue by product ({period.value}): {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="fmp_get_revenue_geographic_segmentation",
        annotations=READ_ONLY,
        description=(
            "Revenue decomposition by geographic region for a symbol. "
            "Returns per-period dicts mapping region → revenue. Surfaces "
            "geographic concentration risk (e.g. China exposure)."
        ),
    )
    async def fmp_get_revenue_geographic_segmentation(
        symbol: Annotated[Symbol, Field(description="Ticker.")],
        period: Annotated[Period, Field(description="annual or quarter.")] = Period.annual,
        structure: Annotated[
            SegmentationStructure,
            Field(description="flat (default) or grouped."),
        ] = SegmentationStructure.flat,
        mode: Annotated[OutputMode, Field(description="summary or inline.")] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            data = await client.get(
                "/stable/revenue-geographic-segmentation",
                {
                    "symbol": symbol,
                    "period": period.value,
                    "structure": structure.value,
                },
            )
            rows = data if isinstance(data, list) else []
            return render_large_result(
                rows,
                name=f"{symbol}_revenue_geo_{period.value}",
                mode=mode,
                fmt=response_format,
                title=f"Revenue by geography ({period.value}): {symbol}",
                what=symbol,
            )
        except Exception as exc:
            return wrap_error(exc)
