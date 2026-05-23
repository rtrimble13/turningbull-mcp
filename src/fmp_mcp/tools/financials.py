"""Financial statement tools: income, balance sheet, cash flow, ratios, key metrics."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import OutputMode, Period, ResponseFormat, Symbol
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
