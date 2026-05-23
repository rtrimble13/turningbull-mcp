"""Unit tests for bls_mcp.

These tests mock httpx entirely — no real network calls. Coverage:
- successful multi-series v2 fetch
- chunking of >50 series IDs into separate POSTs
- v1 fallback fans out per-series GETs when no key is set
- error surfacing when status != "REQUEST_SUCCEEDED" (BLS message is included)
- date construction for M/Q/A/S periods (and the M13 annual-average case)
- value coercion (``"-"`` and empty strings become ``None``)
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from bls_mcp.client import (
    V1_BASE_URL,
    V2_BASE_URL,
    BLSClient,
    install_client,
)
from bls_mcp.errors import BLSError
from bls_mcp.tools.series import _fetch_all_series, _year_windows
from bls_mcp.transform import (
    coerce_value,
    period_to_iso_date,
    reshape_series,
)


# ---------- helpers ----------------------------------------------------------


def _series_response(series: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "REQUEST_SUCCEEDED",
        "message": [],
        "Results": {"series": series},
    }


def _make_client_with_handler(handler) -> BLSClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return BLSClient(http)


# ---------- pure transforms --------------------------------------------------


@pytest.mark.parametrize(
    ("year", "period", "expected"),
    [
        (2025, "M01", "2025-01-01"),
        (2025, "M03", "2025-03-01"),
        (2025, "M12", "2025-12-01"),
        (2025, "M13", "2025-12-31"),  # annual-average pseudo-period
        (2024, "Q01", "2024-01-01"),
        (2024, "Q02", "2024-04-01"),
        (2024, "Q04", "2024-10-01"),
        (2023, "A01", "2023-01-01"),
        (2023, "S01", "2023-01-01"),
        (2023, "S02", "2023-07-01"),
        ("2022", "M07", "2022-07-01"),  # year as string
    ],
)
def test_period_to_iso_date(year, period, expected) -> None:
    assert period_to_iso_date(year, period) == expected


@pytest.mark.parametrize("bad", ["M00", "M13" if False else "Q05", "X01", "", "Mxx"])
def test_period_to_iso_date_rejects_invalid(bad) -> None:
    with pytest.raises(ValueError):
        period_to_iso_date(2025, bad)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("319.799", 319.799),
        ("-", None),
        ("", None),
        (None, None),
        ("  ", None),
        (12, 12.0),
        (12.5, 12.5),
        ("not-a-number", None),
    ],
)
def test_coerce_value(raw, expected) -> None:
    assert coerce_value(raw) == expected


def test_reshape_series_sorts_and_propagates_calculations() -> None:
    raw = {
        "seriesID": "CUUR0000SA0",
        "catalog": {
            "series_title": "CPI-U: All items",
            "data_type_text": "Index 1982-84=100",
            "seasonality": "Not Seasonally Adjusted",
        },
        "data": [
            {
                "year": "2025",
                "period": "M02",
                "periodName": "February",
                "value": "319.0",
                "footnotes": [{}],
                "calculations": {
                    "net_changes": {"1": "0.5", "3": "1.2"},
                    "pct_changes": {"1": "0.2", "12": "3.1"},
                },
            },
            {
                "year": "2025",
                "period": "M01",
                "periodName": "January",
                "value": "-",
                "footnotes": [],
            },
        ],
    }
    shaped = reshape_series(raw)
    assert shaped["series_id"] == "CUUR0000SA0"
    assert shaped["title"] == "CPI-U: All items"
    assert shaped["units"] == "Index 1982-84=100"
    assert shaped["seasonal_adjustment"] == "Not Seasonally Adjusted"
    dates = [o["date"] for o in shaped["observations"]]
    assert dates == ["2025-01-01", "2025-02-01"]  # sorted oldest -> newest
    jan, feb = shaped["observations"]
    assert jan["value"] is None  # "-" becomes None
    assert feb["value"] == 319.0
    assert feb["pct_change_12m"] == 3.1
    assert feb["net_change_1m"] == 0.5


def test_reshape_series_empty_data_gets_note() -> None:
    shaped = reshape_series({"seriesID": "LNS14000000", "data": []})
    assert shaped["observations"] == []
    assert "No observations" in shaped["note"]


# ---------- client: v2 ------------------------------------------------------


async def test_v2_multi_series_fetch(monkeypatch) -> None:
    monkeypatch.setenv("BLS_API_KEY", "test-key")
    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == V2_BASE_URL
        body = json.loads(request.content)
        captured.append(body)
        return httpx.Response(
            200,
            json=_series_response(
                [
                    {
                        "seriesID": sid,
                        "data": [
                            {"year": "2024", "period": "M12", "value": "1.0"}
                        ],
                    }
                    for sid in body["seriesid"]
                ]
            ),
        )

    client = _make_client_with_handler(handler)
    series = await client.fetch(
        ["CUUR0000SA0", "LNS14000000"],
        start_year=2024,
        end_year=2024,
        catalog=True,
        calculations=True,
    )
    assert [s["seriesID"] for s in series] == ["CUUR0000SA0", "LNS14000000"]
    assert captured[0]["registrationkey"] == "test-key"
    assert captured[0]["startyear"] == "2024"
    assert captured[0]["catalog"] is True
    assert captured[0]["calculations"] is True
    assert "annualaverage" not in captured[0]  # not requested


async def test_v2_chunks_more_than_50_series(monkeypatch) -> None:
    monkeypatch.setenv("BLS_API_KEY", "test-key")
    install_client(None)  # type: ignore[arg-type]
    request_bodies: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        request_bodies.append(body["seriesid"])
        return httpx.Response(
            200,
            json=_series_response(
                [{"seriesID": sid, "data": []} for sid in body["seriesid"]]
            ),
        )

    client = _make_client_with_handler(handler)
    install_client(client)
    try:
        # 120 IDs -> three batches of 50, 50, 20
        series_ids = [f"SID{i:05d}" for i in range(120)]
        out = await _fetch_all_series(
            series_ids,
            start_year=2024,
            end_year=2024,
            include_calculations=False,
            include_annual_average=False,
            include_catalog=False,
        )
        assert [len(b) for b in request_bodies] == [50, 50, 20]
        # caller order preserved end-to-end
        assert [s["seriesID"] for s in out] == series_ids
    finally:
        install_client(None)  # type: ignore[arg-type]


async def test_v2_chunks_year_range_over_20_years(monkeypatch) -> None:
    monkeypatch.setenv("BLS_API_KEY", "test-key")
    request_years: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        request_years.append((body["startyear"], body["endyear"]))
        return httpx.Response(
            200,
            json=_series_response(
                [{"seriesID": body["seriesid"][0], "data": []}]
            ),
        )

    client = _make_client_with_handler(handler)
    install_client(client)
    try:
        await _fetch_all_series(
            ["LNS14000000"],
            start_year=1950,
            end_year=2025,
            include_calculations=False,
            include_annual_average=False,
            include_catalog=False,
        )
        # 1950..2025 = 76 years -> four 20-year windows (last one is 16 yrs)
        assert request_years == [
            ("1950", "1969"),
            ("1970", "1989"),
            ("1990", "2009"),
            ("2010", "2025"),
        ]
    finally:
        install_client(None)  # type: ignore[arg-type]


def test_year_windows_inclusive_bounds() -> None:
    # window size 20: [2000..2019], [2020..2025]
    assert _year_windows(2000, 2025, 20) == [(2000, 2019), (2020, 2025)]
    # exactly 20-year range fits in one
    assert _year_windows(2000, 2019, 20) == [(2000, 2019)]
    # bounds unset -> single passthrough
    assert _year_windows(None, None, 20) == [(None, None)]


# ---------- client: v1 fallback ---------------------------------------------


async def test_v1_fallback_when_no_key(monkeypatch) -> None:
    monkeypatch.delenv("BLS_API_KEY", raising=False)
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        seen_urls.append(str(request.url).split("?", 1)[0])
        sid = str(request.url).rsplit("/", 1)[-1].split("?", 1)[0]
        return httpx.Response(
            200,
            json=_series_response(
                [{"seriesID": sid, "data": [
                    {"year": "2024", "period": "M01", "value": "1.0"}
                ]}]
            ),
        )

    client = _make_client_with_handler(handler)
    assert client.using_v2 is False
    series = await client.fetch(["CUUR0000SA0", "LNS14000000"])
    assert seen_urls == [
        f"{V1_BASE_URL}CUUR0000SA0",
        f"{V1_BASE_URL}LNS14000000",
    ]
    assert [s["seriesID"] for s in series] == ["CUUR0000SA0", "LNS14000000"]


# ---------- error surfacing --------------------------------------------------


async def test_request_failed_status_raises_with_message(monkeypatch) -> None:
    monkeypatch.setenv("BLS_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "REQUEST_NOT_PROCESSED",
                "message": [
                    "Series does not exist for Series CUUR0000SA9999",
                    "No Data Available",
                ],
                "Results": {},
            },
        )

    client = _make_client_with_handler(handler)
    with pytest.raises(BLSError) as excinfo:
        await client.fetch(["CUUR0000SA9999"], start_year=2024, end_year=2024)
    msg = str(excinfo.value)
    assert "REQUEST_NOT_PROCESSED" in msg
    assert "Series does not exist" in msg
    assert "No Data Available" in msg


# ---------- merge behavior ---------------------------------------------------


async def test_fetch_all_series_backfills_missing_ids(monkeypatch) -> None:
    """BLS sometimes silently omits a series; we surface it with data: []."""
    monkeypatch.setenv("BLS_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        # Drop the second series — simulate BLS omitting an unknown ID.
        kept = body["seriesid"][:1]
        return httpx.Response(
            200,
            json=_series_response(
                [{"seriesID": sid, "data": [
                    {"year": "2024", "period": "M01", "value": "1.0"}
                ]} for sid in kept]
            ),
        )

    client = _make_client_with_handler(handler)
    install_client(client)
    try:
        out = await _fetch_all_series(
            ["KNOWN1", "UNKNOWN1"],
            start_year=2024,
            end_year=2024,
            include_calculations=False,
            include_annual_average=False,
            include_catalog=False,
        )
        assert [s["seriesID"] for s in out] == ["KNOWN1", "UNKNOWN1"]
        assert out[1]["data"] == []
    finally:
        install_client(None)  # type: ignore[arg-type]
