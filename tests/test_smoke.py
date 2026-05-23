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
    classification,
    corporate,
    financials,
    indexes,
    macro,
    news,
    prices,
    screener,
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
    for m in (prices, news, financials, corporate, classification, indexes, macro, screener):
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
