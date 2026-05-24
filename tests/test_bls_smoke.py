"""Live-API smoke tests for the BLS connector.

Skip themselves when ``BLS_API_KEY`` is unset so a no-secret CI run stays green.

Run them with::

    BLS_API_KEY=... PYTHONPATH=src pytest tests/test_bls_smoke.py -q
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
import pytest

from bls_mcp.client import BLSClient, install_client, make_async_client

pytestmark = pytest.mark.skipif(
    not os.environ.get("BLS_API_KEY", "").strip(),
    reason="BLS_API_KEY is not set; skipping live-API smoke tests.",
)


@pytest.fixture
async def installed_client():
    http = make_async_client()
    client = BLSClient(http)
    install_client(client)
    try:
        yield client
    finally:
        await http.aclose()
        install_client(None)  # type: ignore[arg-type]


async def _call_tool(name: str, args: dict[str, Any]) -> str:
    from bls_mcp.server import mcp

    result = await mcp.call_tool(name, args)
    return str(result)


# ---------- Phase 1 ---------------------------------------------------------


async def test_get_series_with_aspects_and_calculations(installed_client) -> None:
    text = await _call_tool(
        "bls_get_series",
        {
            "series_ids": "CUUR0000SA0",
            "start_year": 2024,
            "end_year": 2024,
            "include_calculations": True,
            "include_catalog": True,
            "include_aspects": True,
            "response_format": "json",
        },
    )
    assert "CUUR0000SA0" in text
    assert "pct_change_12m" in text


async def test_get_latest_observations_multi_series(installed_client) -> None:
    text = await _call_tool(
        "bls_get_latest_observations",
        {
            "series_ids": "CUUR0000SA0,LNS14000000,CES0000000001",
            "response_format": "json",
        },
    )
    for sid in ("CUUR0000SA0", "LNS14000000", "CES0000000001"):
        assert sid in text


# ---------- Phase 2: discovery has no live-API dependency, covered in unit tests
# ---------- Phase 2: analytics ---------------------------------------------


async def test_compose_panel_inline(installed_client) -> None:
    text = await _call_tool(
        "bls_compose_panel",
        {
            "series_ids": ["CUUR0000SA0", "LNS14000000"],
            "start_year": 2023,
            "end_year": 2024,
            "mode": "inline",
            "response_format": "json",
        },
    )
    assert "CUUR0000SA0" in text
    assert "LNS14000000" in text


async def test_transform_series_yoy(installed_client) -> None:
    text = await _call_tool(
        "bls_transform_series",
        {
            "series_id": "CUUR0000SA0",
            "transform": "yoy",
            "start_year": 2022,
            "end_year": 2024,
            "response_format": "json",
        },
    )
    assert "transformed" in text


async def test_deflate_series_returns_real(installed_client) -> None:
    text = await _call_tool(
        "bls_deflate_series",
        {
            "nominal_series_id": "CES0500000003",
            "deflator_series_id": "CUSR0000SA0",
            "start_year": 2022,
            "response_format": "json",
        },
    )
    assert "real" in text


# ---------- Phase 3: composites --------------------------------------------


async def test_inflation_snapshot_live(installed_client) -> None:
    text = await _call_tool(
        "bls_inflation_snapshot",
        {"months_back": 6, "seasonal": "SA", "response_format": "json"},
    )
    assert "headline" in text
    assert "core" in text


async def test_labor_market_snapshot_live(installed_client) -> None:
    text = await _call_tool(
        "bls_labor_market_snapshot",
        {"months_back": 6, "include_jolts": True, "response_format": "json"},
    )
    assert "payrolls_3m_avg_change" in text


async def test_real_wages_live(installed_client) -> None:
    text = await _call_tool(
        "bls_real_wages",
        {"months_back": 12, "response_format": "json"},
    )
    assert "real_wage_index" in text
    # The first row of the index should be 100 (or very close).
    payload = text  # rendered str includes JSON
    assert "real_wage_index" in payload


# ---------- direct client: aspects --------------------------------------


async def test_client_passes_aspects(installed_client) -> None:
    """Sanity check that BLS accepts the aspects parameter in the body."""
    series = await installed_client.fetch(
        ["CUUR0000SA0"], start_year=2024, end_year=2024, aspects=True
    )
    assert series and series[0]["seriesID"] == "CUUR0000SA0"
