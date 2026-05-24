"""Unit tests for BLS discovery: catalog, builders, decoders.

All tests here are pure (no HTTP, no env vars). They verify that the
embedded catalog and ID builders work without ``BLS_API_KEY``.
"""

from __future__ import annotations

import pytest

from bls_mcp.builders import (
    build_ces_series_id,
    build_cpi_series_id,
    build_laus_series_id,
    decode_ces_series_id,
    decode_cpi_series_id,
    decode_laus_series_id,
)
from bls_mcp.catalog import POPULAR_SERIES, Survey, classify_series_id


# ---------- catalog ---------------------------------------------------------


def test_popular_series_has_all_required_buckets() -> None:
    assert "Prices — CPI headline & core" in POPULAR_SERIES
    assert "Labor — Household (CPS)" in POPULAR_SERIES
    assert "Labor — Establishment (CES)" in POPULAR_SERIES
    assert "Labor — JOLTS" in POPULAR_SERIES
    assert "Productivity" in POPULAR_SERIES


def test_popular_series_entries_have_required_fields() -> None:
    required = {"id", "title", "units", "frequency", "seasonal_adjustment", "survey", "notes"}
    for bucket, entries in POPULAR_SERIES.items():
        for e in entries:
            missing = required - e.keys()
            assert not missing, f"{bucket}/{e.get('id')} missing {missing}"


def test_popular_series_has_at_least_50_entries() -> None:
    total = sum(len(v) for v in POPULAR_SERIES.values())
    assert total >= 50, f"only {total} curated entries; expected >= 50"


# ---------- survey classification ------------------------------------------


@pytest.mark.parametrize(
    ("series_id", "expected"),
    [
        ("CUUR0000SA0", Survey.CPI),
        ("CUSR0000SA0L1E", Survey.CPI),
        ("CWUR0000SA0", Survey.CPI),
        ("SUUR0000SA0", Survey.CPI),
        ("CES0000000001", Survey.CES),
        ("LNS14000000", Survey.CPS),
        ("LASST480000000000003", Survey.LAUS),
        ("JTS000000000000000JOR", Survey.JOLTS),
        ("WPSFD4", Survey.PPI),
        ("PRS85006092", Survey.PRODUCTIVITY),
        ("CIS1010000000000I", Survey.ECI),
        ("EIUIR000", Survey.IMPORT_EXPORT),
        ("ZZZ00000", Survey.UNKNOWN),
    ],
)
def test_classify_series_id(series_id, expected) -> None:
    assert classify_series_id(series_id) == expected


# ---------- CPI builder + decoder ------------------------------------------


def test_build_cpi_round_trip() -> None:
    built = build_cpi_series_id(
        area_code="0000", item_code="SA0", seasonal="NSA"
    )
    assert built["series_id"] == "CUUR0000SA0"
    assert built["area"] == "U.S. city average"
    assert built["item"] == "All items"
    assert built["validated"] is True

    decoded = decode_cpi_series_id("CUUR0000SA0")
    assert decoded["decoded"] is True
    assert decoded["survey"] == "CPI"
    assert decoded["seasonal"] == "NSA"
    assert decoded["area"] == "U.S. city average"
    assert decoded["item"] == "All items"


def test_build_cpi_sa_variant() -> None:
    built = build_cpi_series_id(
        area_code="0000", item_code="SA0L1E", seasonal="SA"
    )
    assert built["series_id"] == "CUSR0000SA0L1E"


def test_build_cpi_unknown_area_raises_with_suggestion() -> None:
    with pytest.raises(ValueError) as exc:
        build_cpi_series_id(area_code="ZZZZ", item_code="SA0")
    msg = str(exc.value)
    assert "ZZZZ" in msg
    # The suggestion machinery returns "see bls_list_areas..." when no codes
    # share the first 2 chars; that's still a helpful pointer.
    assert "CPI area_code" in msg


def test_build_cpi_unknown_item_raises() -> None:
    with pytest.raises(ValueError) as exc:
        build_cpi_series_id(area_code="0000", item_code="ZZZ999")
    assert "item_code" in str(exc.value)


def test_decode_cpi_unknown_returns_decoded_false() -> None:
    result = decode_cpi_series_id("LNS14000000")
    assert result["decoded"] is False
    assert "not a CPI series ID" in str(result["reason"])


# ---------- CES builder + decoder ------------------------------------------


def test_build_ces_round_trip_total_nonfarm() -> None:
    built = build_ces_series_id(
        supersector="00", industry="00000000", datatype="01", seasonal="SA"
    )
    assert built["series_id"] == "CES0000000001"
    assert built["supersector"] == "Total nonfarm"
    assert built["datatype"] == "All employees, thousands"
    decoded = decode_ces_series_id("CES0000000001")
    assert decoded["decoded"] is True
    assert decoded["supersector_code"] == "00"
    assert decoded["datatype_code"] == "01"


def test_build_ces_ahe_private() -> None:
    built = build_ces_series_id(
        supersector="05", industry="00000000", datatype="03", seasonal="SA"
    )
    assert built["series_id"] == "CES0500000003"


def test_build_ces_short_industry_padded() -> None:
    """6-char industry should be left-padded with the supersector."""
    built = build_ces_series_id(
        supersector="30", industry="000000", datatype="01", seasonal="SA"
    )
    assert built["series_id"] == "CES3000000001"


def test_build_ces_unknown_datatype_raises() -> None:
    with pytest.raises(ValueError) as exc:
        build_ces_series_id(supersector="00", datatype="99")
    assert "datatype" in str(exc.value)


# ---------- LAUS builder + decoder -----------------------------------------


def test_build_laus_state_unemployment_rate() -> None:
    built = build_laus_series_id(state_fips="48", measure="03", seasonal="SA")
    assert built["series_id"] == "LASST480000000000003"
    assert built["area"] == "Texas"
    assert built["measure"] == "Unemployment rate"
    decoded = decode_laus_series_id("LASST480000000000003")
    assert decoded["decoded"] is True
    assert decoded["area"] == "Texas"
    assert decoded["measure_code"] == "03"


def test_build_laus_nsa_variant() -> None:
    built = build_laus_series_id(state_fips="06", measure="05", seasonal="NSA")
    assert built["series_id"].startswith("LAU")
    assert built["area"] == "California"
    assert built["measure"] == "Employment"


def test_build_laus_zero_pad_fips() -> None:
    """Single-digit FIPS (e.g. '6' for California) should still work."""
    built = build_laus_series_id(state_fips="6", measure="03")
    assert built["area"] == "California"


def test_build_laus_requires_state_or_area() -> None:
    with pytest.raises(ValueError):
        build_laus_series_id(measure="03")


def test_build_laus_rejects_both_state_and_area() -> None:
    with pytest.raises(ValueError):
        build_laus_series_id(state_fips="48", area_code="ST480000000000000", measure="03")


def test_build_laus_unknown_measure_raises() -> None:
    with pytest.raises(ValueError):
        build_laus_series_id(state_fips="48", measure="ZZ")


def test_decode_laus_unknown() -> None:
    result = decode_laus_series_id("CES0000000001")
    assert result["decoded"] is False


# ---------- Phase 2 tools registration -------------------------------------


def test_discovery_tools_register(monkeypatch) -> None:
    """All Phase 2 discovery tools should appear on the MCP server."""
    # Avoid the lifespan warning during import.
    monkeypatch.setenv("BLS_API_KEY", "stub")
    from bls_mcp.server import mcp

    import asyncio

    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert "bls_search_series" in names
    assert "bls_build_series_id" in names
    assert "bls_describe_series" in names
    assert "bls_list_areas" in names
    assert "bls_list_items" in names
