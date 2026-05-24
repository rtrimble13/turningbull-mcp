"""CPI series-ID construction and decoding.

CPI-U series ID format (11+ chars):
  CU + U/S + R + <area:4> + <item:variable>
  ^^   ^   ^    ^          ^
  |    |   |    area_code  item_code
  |    |   periodicity ('R' = regular)
  |    seasonal: U=NSA, S=SA
  Consumer-group prefix: CU=All Urban Consumers, CW=Urban Wage Earners,
  SU=C-CPI-U chained.

Examples:
  CUUR0000SA0   = CPI-U, NSA, US city average, All items
  CUSR0000SA0   = CPI-U, SA, US city average, All items
  CUSR0000SA0L1E = CPI-U, SA, US city avg, All items less food & energy
"""

from __future__ import annotations

from typing import Literal

from ..catalog.cpi_areas import CPI_AREAS
from ..catalog.cpi_items import CPI_ITEMS

Seasonal = Literal["NSA", "SA"]
ConsumerGroup = Literal["U", "W"]  # CU vs CW

_SEASONAL_CODE = {"NSA": "U", "SA": "S"}
_SEASONAL_INVERSE = {"U": "NSA", "S": "SA"}


def _suggest(table: dict[str, str], code: str) -> str | None:
    """Cheap fuzzy hint: any code that starts with the same first 2 chars."""
    code_u = code.upper()
    candidates = [k for k in table if k.startswith(code_u[:2])]
    if not candidates:
        return None
    return f"did you mean one of: {', '.join(sorted(candidates)[:5])}?"


def build_cpi_series_id(
    *,
    area_code: str,
    item_code: str,
    seasonal: Seasonal = "NSA",
    consumer_group: ConsumerGroup = "U",
) -> dict[str, str | bool]:
    """Construct and validate a CPI series ID.

    Returns ``{"series_id", "survey", "seasonal", "consumer_group",
    "area", "item", "validated": True}`` on success. Raises ``ValueError``
    with a helpful suggestion on a bad code.
    """
    area_code = area_code.strip().upper()
    item_code = item_code.strip().upper()
    if area_code not in CPI_AREAS:
        hint = _suggest(CPI_AREAS, area_code) or "see bls_list_areas(survey='CPI')."
        raise ValueError(f"unknown CPI area_code {area_code!r}; {hint}")
    if item_code not in CPI_ITEMS:
        hint = _suggest(CPI_ITEMS, item_code) or "see bls_list_items(survey='CPI')."
        raise ValueError(f"unknown CPI item_code {item_code!r}; {hint}")
    if seasonal not in _SEASONAL_CODE:
        raise ValueError(f"seasonal must be 'NSA' or 'SA', got {seasonal!r}")
    if consumer_group not in ("U", "W"):
        raise ValueError(f"consumer_group must be 'U' or 'W', got {consumer_group!r}")

    sid = f"C{consumer_group}{_SEASONAL_CODE[seasonal]}R{area_code}{item_code}"
    return {
        "series_id": sid,
        "survey": "CPI",
        "seasonal": seasonal,
        "consumer_group": (
            "All Urban Consumers" if consumer_group == "U" else "Urban Wage Earners"
        ),
        "area_code": area_code,
        "area": CPI_AREAS[area_code],
        "item_code": item_code,
        "item": CPI_ITEMS[item_code],
        "validated": True,
    }


def decode_cpi_series_id(series_id: str) -> dict[str, str | bool]:
    """Parse a CPI series ID into its components.

    Returns ``{"decoded": True, ...}`` on a recognized layout, or
    ``{"decoded": False, "reason": ...}`` otherwise. Pure local — no HTTP.
    """
    sid = (series_id or "").strip().upper()
    # Layout: CU/CW/SU + U/S + R + area(4) + item(variable, >=3)
    if len(sid) < 11 or sid[:2] not in ("CU", "CW", "SU"):
        return {"decoded": False, "reason": f"not a CPI series ID: {series_id!r}"}
    cg_char = sid[1]
    seasonal_char = sid[2]
    periodicity = sid[3]
    area_code = sid[4:8]
    item_code = sid[8:]
    seasonal = _SEASONAL_INVERSE.get(seasonal_char)
    if seasonal is None:
        return {"decoded": False, "reason": f"unknown CPI seasonal flag {seasonal_char!r}"}
    return {
        "decoded": True,
        "series_id": sid,
        "survey": "CPI",
        "consumer_group": (
            "All Urban Consumers" if cg_char == "U"
            else "Urban Wage Earners" if cg_char == "W"
            else "Chained CPI-U"
        ),
        "seasonal": seasonal,
        "periodicity": periodicity,
        "area_code": area_code,
        "area": CPI_AREAS.get(area_code, "(unknown area)"),
        "item_code": item_code,
        "item": CPI_ITEMS.get(item_code, "(unknown item)"),
    }
