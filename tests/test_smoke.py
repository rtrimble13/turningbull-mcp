"""Smoke tests for the FMP MCP server.

These tests hit the real FMP API. They're skipped automatically when
FMP_API_KEY is not set, so a CI run without secrets stays green.

Run a single category, e.g.:
    pytest tests/test_smoke.py::test_quote -q
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest

from fmp_mcp.client import FMPClient, install_client, make_async_client
from fmp_mcp.models import ResponseFormat
from fmp_mcp.tools import (
    calendars,
    classification,
    composites,
    corporate,
    estimates,
    etf,
    filings,
    financials,
    indexes,
    macro,
    movers,
    multiasset,
    news,
    ownership,
    prices,
    screener,
    technicals,
    transcripts,
    valuation,
)
from mcp.server.fastmcp import FastMCP

pytestmark = pytest.mark.skipif(
    not os.environ.get("FMP_API_KEY", "").strip(),
    reason="FMP_API_KEY is not set; skipping live-API smoke tests.",
)


@pytest.fixture(scope="module")
async def server() -> Any:
    http = make_async_client()
    install_client(FMPClient(http))
    mcp = FastMCP("fmp_mcp_test")
    for m in (
        prices,
        news,
        financials,
        corporate,
        classification,
        indexes,
        macro,
        screener,
        technicals,
        calendars,
        estimates,
        transcripts,
        valuation,
        ownership,
        filings,
        movers,
        etf,
        multiasset,
        composites,
    ):
        m.register(mcp)
    yield mcp
    await http.aclose()


def _assert_not_error(text: str) -> None:
    assert text, "tool returned empty text"
    assert "FMP error" not in text and "Unexpected error" not in text, text[:400]


async def _call(server: FastMCP, name: str, **kwargs: Any) -> str:
    result = await server.call_tool(name, kwargs)
    # FastMCP returns a (content_list, structured) tuple; older versions just
    # return content_list. Normalize to the first text chunk.
    if isinstance(result, tuple):
        content = result[0]
    else:
        content = result
    text = "\n".join(
        getattr(c, "text", "") for c in content if getattr(c, "type", None) == "text"
    )
    return text


async def test_quote(server: FastMCP) -> None:
    text = await _call(server, "fmp_get_quote", symbols="AAPL", response_format=ResponseFormat.json.value)
    _assert_not_error(text)
    assert "AAPL" in text


async def test_historical_prices(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_historical_prices",
        symbol="AAPL",
        from_date="2024-01-01",
        to_date="2024-03-01",
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_index_quote(server: FastMCP) -> None:
    text = await _call(server, "fmp_get_index_quote", symbols="^GSPC", response_format=ResponseFormat.json.value)
    _assert_not_error(text)


async def test_profile(server: FastMCP) -> None:
    text = await _call(server, "fmp_get_company_profile", symbol="AAPL", response_format=ResponseFormat.json.value)
    _assert_not_error(text)
    assert "AAPL" in text or "Apple" in text


async def test_income_statement(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_income_statement",
        symbol="AAPL",
        period="annual",
        limit=2,
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_search(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_search_symbol",
        query="Apple",
        mode="name",
        limit=5,
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_list_sectors(server: FastMCP) -> None:
    text = await _call(server, "fmp_list_sectors", response_format=ResponseFormat.json.value)
    _assert_not_error(text)


async def test_index_list(server: FastMCP) -> None:
    text = await _call(server, "fmp_list_indexes", response_format=ResponseFormat.json.value)
    _assert_not_error(text)


async def test_treasury(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_treasury_rates",
        from_date="2025-01-01",
        to_date="2025-02-01",
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_screener(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_screen_stocks",
        sector="Technology",
        country="US",
        market_cap_more_than=1_000_000_000_000,
        limit=5,
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_market_news(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_market_news",
        page=0,
        limit=5,
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


# ----- New modules: Phase 1 -----


async def test_technical_indicator(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_technical_indicator",
        symbol="AAPL",
        indicator="rsi",
        period_length=14,
        interval="1day",
        from_date="2025-01-01",
        to_date="2025-03-01",
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_earnings_calendar(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_earnings_calendar",
        from_date="2025-01-01",
        to_date="2025-01-15",
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_analyst_estimates(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_analyst_estimates",
        symbol="AAPL",
        period="annual",
        limit=3,
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_price_target_consensus(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_price_target_consensus",
        symbol="AAPL",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_dividend_history(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_dividend_history",
        symbol="KO",
        limit=10,
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_split_history(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_split_history",
        symbol="AAPL",
        limit=10,
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_stock_peers(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_stock_peers",
        symbol="AAPL",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_financial_growth(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_financial_growth",
        symbol="AAPL",
        period="annual",
        limit=3,
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_enterprise_values(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_enterprise_values",
        symbol="AAPL",
        period="annual",
        limit=3,
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


# ----- Phase 2 -----


async def test_dcf(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_dcf",
        symbol="AAPL",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_financial_score(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_financial_score",
        symbol="AAPL",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_insider_trades(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_insider_trades",
        symbol="AAPL",
        transaction_type="ALL",
        page=0,
        limit=5,
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_list_sec_filings(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_list_sec_filings",
        symbol="AAPL",
        form_type="10-K",
        page=0,
        limit=5,
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


# ----- Phase 3 -----


async def test_gainers(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_gainers",
        limit=5,
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


# ----- Phase 4 -----


async def test_etf_holdings(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_etf_holdings",
        symbol="SPY",
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_etf_holders(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_get_etf_holders",
        symbol="AAPL",
        mode="inline",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_list_forex_pairs(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_list_forex_pairs",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


# ----- Phase 5 (composites) -----


async def test_company_snapshot(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_company_snapshot",
        symbol="AAPL",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)


async def test_technical_snapshot(server: FastMCP) -> None:
    text = await _call(
        server,
        "fmp_technical_snapshot",
        symbol="AAPL",
        interval="1day",
        response_format=ResponseFormat.json.value,
    )
    _assert_not_error(text)
