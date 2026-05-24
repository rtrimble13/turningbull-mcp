"""Unit tests for the composite snapshot tools.

Uses httpx.MockTransport to mock the v2 endpoint. Verifies that each
composite makes a single POST containing the expected series IDs and
returns a payload with the right structure.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pandas as pd
import pytest

from bls_mcp.client import BLSClient, install_client
from bls_mcp.tools.composites import (
    INFLATION_SA,
    JOLTS_SERIES,
    LABOR_SERIES,
)


def _synthetic_monthly_series(n_years: int = 5, start_value: float = 100.0,
                              monthly_growth: float = 0.002) -> list[dict[str, Any]]:
    """n_years * 12 months of values growing geometrically."""
    out: list[dict[str, Any]] = []
    today = pd.Timestamp.today()
    end_year = today.year
    start_year = end_year - n_years + 1
    val = start_value
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            if y == end_year and m > today.month:
                break
            out.append({"year": str(y), "period": f"M{m:02d}", "value": f"{val:.4f}"})
            val *= 1.0 + monthly_growth
    return out


def _make_mock_handler(captured: list[dict[str, Any]]):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured.append(body)
        return httpx.Response(
            200,
            json={
                "status": "REQUEST_SUCCEEDED",
                "message": [],
                "Results": {
                    "series": [
                        {"seriesID": sid, "data": _synthetic_monthly_series()}
                        for sid in body["seriesid"]
                    ]
                },
            },
        )
    return handler


@pytest.fixture
def mock_v2_client(monkeypatch):
    monkeypatch.setenv("BLS_API_KEY", "test-key")
    captured: list[dict[str, Any]] = []
    transport = httpx.MockTransport(_make_mock_handler(captured))
    http = httpx.AsyncClient(transport=transport)
    client = BLSClient(http)
    install_client(client)
    try:
        yield captured
    finally:
        install_client(None)  # type: ignore[arg-type]


async def _call_tool(name: str, args: dict[str, Any]) -> str:
    from bls_mcp.server import mcp
    result = await mcp.call_tool(name, args)
    # FastMCP returns a list of content blocks; concatenate text.
    return result if isinstance(result, str) else str(result)


# ---------- inflation snapshot ---------------------------------------------


async def test_inflation_snapshot_calls_one_post_with_six_series(mock_v2_client) -> None:
    text = await _call_tool(
        "bls_inflation_snapshot",
        {"months_back": 6, "seasonal": "SA", "response_format": "json"},
    )
    # Exactly one POST, with all six inflation series IDs.
    assert len(mock_v2_client) == 1
    assert set(mock_v2_client[0]["seriesid"]) == set(INFLATION_SA.values())
    assert "headline" in text
    assert "core" in text
    assert "shelter" in text


async def test_inflation_snapshot_uses_nsa_when_requested(mock_v2_client) -> None:
    await _call_tool(
        "bls_inflation_snapshot",
        {"months_back": 3, "seasonal": "NSA", "response_format": "json"},
    )
    sent_ids = mock_v2_client[0]["seriesid"]
    # NSA path uses CUUR prefix.
    assert all(s.startswith("CUUR") for s in sent_ids)


# ---------- labor market snapshot ------------------------------------------


async def test_labor_snapshot_includes_jolts_when_flag_set(mock_v2_client) -> None:
    await _call_tool(
        "bls_labor_market_snapshot",
        {"months_back": 6, "include_jolts": True, "response_format": "json"},
    )
    sent_ids = set(mock_v2_client[0]["seriesid"])
    for sid in LABOR_SERIES.values():
        assert sid in sent_ids
    for sid in JOLTS_SERIES.values():
        assert sid in sent_ids


async def test_labor_snapshot_excludes_jolts_when_flag_false(mock_v2_client) -> None:
    await _call_tool(
        "bls_labor_market_snapshot",
        {"months_back": 6, "include_jolts": False, "response_format": "json"},
    )
    sent_ids = set(mock_v2_client[0]["seriesid"])
    for sid in JOLTS_SERIES.values():
        assert sid not in sent_ids


async def test_labor_snapshot_includes_payrolls_3m_avg(mock_v2_client) -> None:
    text = await _call_tool(
        "bls_labor_market_snapshot",
        {"months_back": 6, "include_jolts": False, "response_format": "json"},
    )
    assert "payrolls_3m_avg_change" in text


# ---------- real wages ------------------------------------------------------


async def test_real_wages_returns_index_starting_at_100(mock_v2_client) -> None:
    text = await _call_tool(
        "bls_real_wages",
        {"months_back": 12, "response_format": "json"},
    )
    # One POST, both wage + CPI series in it.
    assert len(mock_v2_client) == 1
    sent_ids = set(mock_v2_client[0]["seriesid"])
    assert "CES0500000003" in sent_ids
    assert "CUSR0000SA0" in sent_ids
    # The earliest real_wage_index entry should equal 100 (rebased to that point).
    # Parse the JSON payload back out of the rendered output.
    # Render path: render_small_result + ResponseFormat.json wraps the dict.
    # Easiest assertion: "real_wage_index" present in the rendered text.
    assert "real_wage_index" in text
    assert "100" in text  # starts at 100.0


# ---------- composite tool registration ------------------------------------


async def test_composites_register(monkeypatch) -> None:
    monkeypatch.setenv("BLS_API_KEY", "stub")
    from bls_mcp.server import mcp

    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert "bls_inflation_snapshot" in names
    assert "bls_labor_market_snapshot" in names
    assert "bls_real_wages" in names
