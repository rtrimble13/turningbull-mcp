"""Unit tests for fred_mcp.

These tests mock httpx entirely — no real network calls. Coverage:
- the ``qp`` query-param helper drops None and unwraps enums
- the client injects ``api_key`` + ``file_type=json`` and targets the right host
- a missing key raises ``FredError`` before any request is made
- GeoFRED requests route to the geofred host
- every tool module registers and the full tool set is exposed
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from mcp.server.fastmcp import FastMCP

from fred_mcp.client import FredClient
from fred_mcp.errors import FredError
from fred_mcp.models import SortOrder, Units
from fred_mcp.tools import _common, categories, maps, releases, series, sources, tags


def _client_with_handler(handler, *, api_key: str | None = "test-key") -> FredClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return FredClient(http, api_key=api_key)


# ---------- qp helper --------------------------------------------------------


def test_qp_drops_none_and_unwraps_enums() -> None:
    out = _common.qp(a=None, b="x", limit=10, sort_order=SortOrder.desc, units=Units.pc1)
    assert out == {"b": "x", "limit": 10, "sort_order": "desc", "units": "pc1"}


# ---------- client injection -------------------------------------------------


async def test_client_injects_key_and_filetype() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"seriess": [{"id": "GNPCA"}]})

    client = _client_with_handler(handler)
    data = await client.get("/series", {"series_id": "GNPCA"})
    assert data == {"seriess": [{"id": "GNPCA"}]}
    assert captured["url"].startswith("https://api.stlouisfed.org/fred/series?")
    assert "api_key=test-key" in captured["url"]
    assert "file_type=json" in captured["url"]
    assert "series_id=GNPCA" in captured["url"]
    await client._http.aclose()


async def test_geo_get_targets_geofred_host() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"series_group": {}})

    client = _client_with_handler(handler)
    await client.geo_get("/series/group", {"series_id": "WIPCPI"})
    assert captured["url"].startswith("https://api.stlouisfed.org/geofred/series/group?")
    await client._http.aclose()


async def test_missing_key_raises_before_request() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("network should not be hit when key is missing")

    client = _client_with_handler(handler, api_key=None)
    with pytest.raises(FredError):
        await client.get("/series", {"series_id": "GNPCA"})
    await client._http.aclose()


async def test_http_error_maps_to_fred_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error_code": 400, "error_message": "Bad Request. Variable api_key has not been set."})

    client = _client_with_handler(handler)
    with pytest.raises(FredError) as exc:
        await client.get("/series", {"series_id": "GNPCA"})
    assert "400" in str(exc.value)
    await client._http.aclose()


# ---------- tool registration ------------------------------------------------


async def test_all_tools_registered() -> None:
    mcp = FastMCP("fred_test")
    for module in (categories, releases, series, sources, tags, maps):
        module.register(mcp)
    tools = await mcp.list_tools()
    names = {t.name for t in tools}

    expected = {
        # categories (6)
        "fred_get_category",
        "fred_get_category_children",
        "fred_get_category_related",
        "fred_get_category_series",
        "fred_get_category_tags",
        "fred_get_category_related_tags",
        # releases (9)
        "fred_get_releases",
        "fred_get_releases_dates",
        "fred_get_release",
        "fred_get_release_dates",
        "fred_get_release_series",
        "fred_get_release_sources",
        "fred_get_release_tags",
        "fred_get_release_related_tags",
        "fred_get_release_tables",
        # series (10)
        "fred_get_series",
        "fred_get_series_categories",
        "fred_get_series_observations",
        "fred_get_series_release",
        "fred_search_series",
        "fred_get_series_search_tags",
        "fred_get_series_search_related_tags",
        "fred_get_series_tags",
        "fred_get_series_updates",
        "fred_get_series_vintagedates",
        # sources (3)
        "fred_get_sources",
        "fred_get_source",
        "fred_get_source_releases",
        # tags (3)
        "fred_get_tags",
        "fred_get_related_tags",
        "fred_get_tags_series",
        # geofred / maps (4)
        "fred_get_geofred_shapes",
        "fred_get_geofred_series_group",
        "fred_get_geofred_series_data",
        "fred_get_geofred_regional_data",
    }
    assert names == expected
    assert len(expected) == 35
