"""Pure series-ID construction helpers, validated against embedded code tables."""

from __future__ import annotations

from .ces import build_ces_series_id, decode_ces_series_id
from .cpi import build_cpi_series_id, decode_cpi_series_id
from .laus import build_laus_series_id, decode_laus_series_id

__all__ = [
    "build_cpi_series_id",
    "build_ces_series_id",
    "build_laus_series_id",
    "decode_cpi_series_id",
    "decode_ces_series_id",
    "decode_laus_series_id",
]
