"""LAUS series-ID construction and decoding.

LAUS series ID format (20 chars):
  LA + S/U + <area:15> + <measure:2>
  ^^   ^    ^            ^
  |    |    area code    measure: 03=unemp rate, 04=unemp, 05=emp, 06=labor force
  |    seasonal: S=SA, U=NSA
  Survey prefix LA.

For state series the area code is ``ST<FIPS>00000000000`` (15 chars).

Examples:
  LASST480000000000003 = Texas unemployment rate (SA)
  LAUST060000000000003 = California unemployment rate (NSA)
"""

from __future__ import annotations

from typing import Literal

from ..catalog.laus_areas import LAUS_STATES
from ..catalog.laus_measures import LAUS_MEASURES

Seasonal = Literal["NSA", "SA"]

_SEASONAL_CODE = {"SA": "S", "NSA": "U"}
_SEASONAL_INVERSE = {"S": "SA", "U": "NSA"}


def build_laus_series_id(
    *,
    state_fips: str | None = None,
    area_code: str | None = None,
    measure: str,
    seasonal: Seasonal = "SA",
) -> dict[str, str | bool]:
    """Construct and validate a LAUS series ID.

    Pass either ``state_fips`` (2-digit FIPS code) for a state-level series
    OR an explicit 15-char ``area_code``. ``measure`` is 2 chars (e.g.
    '03' for unemployment rate).
    """
    if state_fips is not None and area_code is not None:
        raise ValueError("Pass either state_fips OR area_code, not both.")
    if state_fips is None and area_code is None:
        raise ValueError("Pass state_fips (e.g. '48' for Texas) or a full area_code.")

    if state_fips is not None:
        state_fips = state_fips.strip().zfill(2)
        if state_fips not in LAUS_STATES:
            raise ValueError(
                f"unknown state FIPS {state_fips!r}. Valid codes: "
                f"{', '.join(sorted(LAUS_STATES)[:5])}..."
            )
        area_resolved = f"ST{state_fips}00000000000"
        area_name = LAUS_STATES[state_fips]
    else:
        assert area_code is not None
        area_resolved = area_code.strip().upper()
        if len(area_resolved) != 15:
            raise ValueError(
                f"LAUS area_code must be 15 chars, got {area_code!r} ({len(area_resolved)})"
            )
        # Best-effort name resolution.
        area_name = "(custom area)"
        if area_resolved.startswith("ST"):
            fips = area_resolved[2:4]
            area_name = LAUS_STATES.get(fips, area_name)

    measure = measure.strip()
    if measure not in LAUS_MEASURES:
        raise ValueError(
            f"unknown LAUS measure {measure!r}. Valid: "
            f"{', '.join(f'{k}={v}' for k, v in LAUS_MEASURES.items())}"
        )
    if seasonal not in _SEASONAL_CODE:
        raise ValueError(f"seasonal must be 'NSA' or 'SA', got {seasonal!r}")

    sid = f"LA{_SEASONAL_CODE[seasonal]}{area_resolved}{measure}"
    return {
        "series_id": sid,
        "survey": "LAUS",
        "seasonal": seasonal,
        "area_code": area_resolved,
        "area": area_name,
        "measure_code": measure,
        "measure": LAUS_MEASURES[measure],
        "validated": True,
    }


def decode_laus_series_id(series_id: str) -> dict[str, str | bool]:
    """Parse a LAUS series ID into its components."""
    sid = (series_id or "").strip().upper()
    if len(sid) != 20 or sid[:2] != "LA" or sid[2] not in ("S", "U"):
        return {"decoded": False, "reason": f"not a LAUS series ID: {series_id!r}"}
    seasonal = _SEASONAL_INVERSE[sid[2]]
    area_code = sid[3:18]
    measure_code = sid[18:20]
    area_name = "(unknown area)"
    if area_code.startswith("ST"):
        fips = area_code[2:4]
        area_name = LAUS_STATES.get(fips, area_name)
    return {
        "decoded": True,
        "series_id": sid,
        "survey": "LAUS",
        "seasonal": seasonal,
        "area_code": area_code,
        "area": area_name,
        "measure_code": measure_code,
        "measure": LAUS_MEASURES.get(measure_code, "(unknown measure)"),
    }
