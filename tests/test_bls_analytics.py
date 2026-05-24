"""Unit tests for BLS analytics helpers.

Pure pandas math — no HTTP. Synthetic series exercise the corner cases:
panel alignment, YoY with leading NaNs, deflation against a custom base.
"""

from __future__ import annotations

import pandas as pd
import pytest

from bls_mcp.tools.analytics import (
    deflate,
    index_to_base,
    log_diff,
    mom_annualized,
    pivot_to_panel,
    reshaped_to_long,
    yoy,
)


def _monthly_index(start: str, n: int) -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=n, freq="MS")


def test_reshaped_to_long_handles_empty() -> None:
    df = reshaped_to_long([])
    assert df.empty
    assert list(df.columns) == ["series_id", "date", "value"]


def test_pivot_to_panel_aligns_dates() -> None:
    """Two series with overlapping months should produce a union-indexed wide frame."""
    reshaped = [
        {
            "series_id": "A",
            "observations": [
                {"date": "2024-01-01", "value": 100.0},
                {"date": "2024-02-01", "value": 101.0},
            ],
        },
        {
            "series_id": "B",
            "observations": [
                {"date": "2024-02-01", "value": 50.0},
                {"date": "2024-03-01", "value": 52.0},
            ],
        },
    ]
    long = reshaped_to_long(reshaped)
    wide = pivot_to_panel(long)
    assert list(wide.columns) == ["A", "B"]
    assert list(wide.index.strftime("%Y-%m-%d")) == ["2024-01-01", "2024-02-01", "2024-03-01"]
    # B has no January value -> NaN.
    assert pd.isna(wide.loc["2024-01-01", "B"])
    assert wide.loc["2024-02-01", "A"] == 101.0
    assert wide.loc["2024-02-01", "B"] == 50.0


def test_yoy_leading_nan_and_value() -> None:
    idx = _monthly_index("2023-01-01", 13)
    s = pd.Series(range(100, 113), index=idx, dtype=float)
    df = pd.DataFrame({"X": s})
    out = yoy(df, periods=12)
    # First 12 entries should be NaN; 13th should be 12/100*100 = 12.0%.
    assert out["X"].iloc[:12].isna().all()
    assert pytest.approx(out["X"].iloc[12]) == 12.0


def test_mom_annualized_known_value() -> None:
    idx = _monthly_index("2024-01-01", 2)
    # MoM 1% → annualized = ((1.01)^12 - 1)*100 ≈ 12.6825
    df = pd.DataFrame({"X": [100.0, 101.0]}, index=idx)
    out = mom_annualized(df)
    assert pytest.approx(out["X"].iloc[1], rel=1e-6) == ((1.01) ** 12 - 1) * 100


def test_log_diff_known_value() -> None:
    import math
    idx = _monthly_index("2024-01-01", 2)
    df = pd.DataFrame({"X": [100.0, 110.0]}, index=idx)
    out = log_diff(df, periods=1)
    expected = (math.log(110.0) - math.log(100.0)) * 100.0
    assert pytest.approx(out["X"].iloc[1], rel=1e-6) == expected


def test_index_to_base_first_row_default() -> None:
    idx = _monthly_index("2024-01-01", 3)
    df = pd.DataFrame({"X": [200.0, 220.0, 240.0]}, index=idx)
    out = index_to_base(df)
    assert pytest.approx(out["X"].iloc[0]) == 100.0
    assert pytest.approx(out["X"].iloc[1]) == 110.0
    assert pytest.approx(out["X"].iloc[2]) == 120.0


def test_index_to_base_explicit_base_period() -> None:
    idx = _monthly_index("2024-01-01", 4)
    df = pd.DataFrame({"X": [100.0, 110.0, 120.0, 130.0]}, index=idx)
    out = index_to_base(df, base_period="2024-02-01")
    assert pytest.approx(out["X"].iloc[1]) == 100.0
    assert pytest.approx(out["X"].iloc[3]) == 130.0 / 110.0 * 100


def test_deflate_known_values() -> None:
    """Synthetic data with a known answer: wages double, CPI 1.5x → real 4/3 vs base."""
    idx = _monthly_index("2023-01-01", 13)
    nominal = pd.Series([100.0] * 12 + [200.0], index=idx)
    deflator = pd.Series([100.0] * 12 + [150.0], index=idx)
    out = deflate(nominal, deflator, base_period="2023-01-01")
    # base_val=100 → real_13 = 200 / (150/100) = 133.333...
    assert pytest.approx(out["real"].iloc[12], rel=1e-6) == 200.0 / 1.5
    # YoY at row 12: nominal +100%, deflator +50% → real ≈ +33.33%
    assert pytest.approx(out["nominal_yoy_pct"].iloc[12], rel=1e-6) == 100.0
    assert pytest.approx(out["real_yoy_pct"].iloc[12], rel=1e-3) == 33.333333


def test_deflate_handles_missing_overlap() -> None:
    """If deflator base date precedes nominal data, fallback to first non-null."""
    idx = _monthly_index("2024-01-01", 3)
    nominal = pd.Series([100.0, 110.0, 121.0], index=idx)
    deflator = pd.Series([200.0, 210.0, 220.0], index=idx)
    out = deflate(nominal, deflator)
    # Default base = first non-null deflator = 200.
    assert pytest.approx(out["real"].iloc[0]) == 100.0
    assert pytest.approx(out["real"].iloc[1]) == 110.0 / (210.0 / 200.0)
