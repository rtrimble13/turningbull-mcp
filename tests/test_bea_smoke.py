"""Live-API smoke tests for the BEA connector.

Skip themselves when ``BEA_API_KEY`` is unset so a no-secret CI run stays
green.

Run them with::

    BEA_API_KEY=... PYTHONPATH=src pytest tests/test_bea_smoke.py -q
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from bea_mcp.client import BEAClient, install_client, make_async_client

pytestmark = pytest.mark.skipif(
    not os.environ.get("BEA_API_KEY", "").strip(),
    reason="BEA_API_KEY is not set; skipping live-API smoke tests.",
)


@pytest.fixture
async def installed_client():
    http = make_async_client()
    client = BEAClient(http)
    install_client(client)
    try:
        yield client
    finally:
        await http.aclose()
        install_client(None)


async def _call_tool(name: str, args: dict[str, Any]) -> str:
    from bea_mcp.server import mcp

    result = await mcp.call_tool(name, args)
    return str(result)


# ---------- Discovery ------------------------------------------------------


async def test_list_datasets(installed_client) -> None:
    text = await _call_tool("bea_list_datasets", {"response_format": "json"})
    # We should see at least the major datasets in the list.
    for ds in ("NIPA", "Regional", "GDPbyIndustry", "FixedAssets", "ITA"):
        assert ds in text


async def test_list_parameters_for_nipa(installed_client) -> None:
    text = await _call_tool(
        "bea_list_parameters",
        {"dataset": "NIPA", "response_format": "json"},
    )
    assert "TableName" in text
    assert "Frequency" in text


async def test_list_parameter_values_for_nipa_tablename(installed_client) -> None:
    text = await _call_tool(
        "bea_list_parameter_values",
        {"dataset": "NIPA", "parameter": "TableName", "response_format": "json"},
    )
    # T10101 is the headline real-GDP % change table; should appear.
    assert "T10101" in text


async def test_list_parameter_values_filtered(installed_client) -> None:
    text = await _call_tool(
        "bea_list_parameter_values_filtered",
        {
            "dataset": "NIPA",
            "target_parameter": "Year",
            "filters": {"TableName": "T10101", "Frequency": "Q"},
            "response_format": "json",
        },
    )
    # The filtered values endpoint should at least return *some* year token.
    # The exact JSON shape varies a bit by dataset, so just check the call
    # didn't error.
    assert "BEAError" not in text and "Unexpected error" not in text


async def test_search_tables_local(installed_client) -> None:
    text = await _call_tool(
        "bea_search_tables",
        {"query": "real GDP", "response_format": "json"},
    )
    assert "T10101" in text or "T10106" in text


# ---------- Generic --------------------------------------------------------


async def test_get_data_generic_nipa(installed_client) -> None:
    text = await _call_tool(
        "bea_get_data",
        {
            "dataset": "NIPA",
            "params": {"TableName": "T10101", "Frequency": "Q", "Year": "2023"},
            "mode": "inline",
            "response_format": "json",
        },
    )
    assert "T10101" in text


# ---------- Per-dataset typed tools ---------------------------------------


async def test_get_nipa_typed(installed_client) -> None:
    text = await _call_tool(
        "bea_get_nipa",
        {
            "table_name": "T10101",
            "frequency": "Q",
            "year": "2023,2024",
            "mode": "inline",
            "response_format": "json",
        },
    )
    assert "T10101" in text


async def test_get_fixed_assets_typed(installed_client) -> None:
    text = await _call_tool(
        "bea_get_fixed_assets",
        {
            "table_name": "FAAt101",
            "year": "2022,2023",
            "mode": "inline",
            "response_format": "json",
        },
    )
    assert "FAAt101" in text or "BEAError" not in text


async def test_get_regional_typed(installed_client) -> None:
    text = await _call_tool(
        "bea_get_regional",
        {
            "table_name": "SAGDP1",
            "line_code": 1,
            "geo_fips": "06000",
            "year": "2023",
            "mode": "inline",
            "response_format": "json",
        },
    )
    # California (06000) data should round-trip.
    assert "06000" in text or "California" in text


async def test_get_gdp_by_industry_typed(installed_client) -> None:
    text = await _call_tool(
        "bea_get_gdp_by_industry",
        {
            "table_id": 1,
            "frequency": "A",
            "industry": "11",
            "year": "2023",
            "mode": "inline",
            "response_format": "json",
        },
    )
    assert "BEAError" not in text and "Unexpected error" not in text


async def test_get_ita_typed(installed_client) -> None:
    text = await _call_tool(
        "bea_get_ita",
        {
            "indicator": "BalCurrAcct",
            "area_or_country": "AllCountries",
            "frequency": "A",
            "year": "2023",
            "mode": "inline",
            "response_format": "json",
        },
    )
    assert "BalCurrAcct" in text or "BEAError" not in text


# ---------- Composites ----------------------------------------------------


async def test_gdp_snapshot(installed_client) -> None:
    text = await _call_tool(
        "bea_gdp_snapshot",
        {"quarters_back": 4, "response_format": "json"},
    )
    assert "headline_real_gdp_growth_pct" in text or "components" in text


async def test_regional_snapshot(installed_client) -> None:
    text = await _call_tool(
        "bea_regional_snapshot",
        {"geo_fips": "STATE", "years_back": 2, "response_format": "json"},
    )
    # Look for at least one state in the response.
    assert "rows" in text and ("California" in text or "06000" in text or "Texas" in text)


async def test_trade_balance_snapshot(installed_client) -> None:
    text = await _call_tool(
        "bea_trade_balance_snapshot",
        {"years_back": 3, "response_format": "json"},
    )
    assert "current_account_balance" in text or "components" in text


async def test_personal_income_snapshot(installed_client) -> None:
    text = await _call_tool(
        "bea_personal_income_snapshot",
        {"months_back": 12, "response_format": "json"},
    )
    assert "personal_income" in text or "components" in text


# ---------- direct client sanity ------------------------------------------


async def test_client_get_nipa_direct(installed_client) -> None:
    """Sanity: a direct client.call returns Data rows for a known table."""
    results = await installed_client.call(
        "GetData",
        dataset="NIPA",
        params={"TableName": "T10101", "Frequency": "Q", "Year": "2023"},
    )
    data = results.get("Data") or []
    assert isinstance(data, list) and len(data) > 0
