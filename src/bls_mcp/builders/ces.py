"""CES series-ID construction and decoding.

CES series ID format (13 chars):
  CES + S/U + <supersector:2> + <industry:6> + <datatype:2>
  ^^^   ^    ^                  ^              ^
  |     |    supersector code    industry      data type
  |     seasonal: S=SA, U=NSA
  Survey prefix: CES (SA-friendly) or CEU (NSA full path).

Examples:
  CES0000000001 = SA, total nonfarm supersector, all-industry, all-employees
  CES0500000003 = SA, total private supersector, AHE all employees
"""

from __future__ import annotations

from typing import Literal

from ..catalog.ces_datatypes import CES_DATATYPES
from ..catalog.ces_industries import CES_INDUSTRIES, CES_SUPERSECTORS

Seasonal = Literal["NSA", "SA"]

_SEASONAL_CODE = {"SA": "S", "NSA": "U"}
_SEASONAL_INVERSE = {"S": "SA", "U": "NSA"}


def _suggest(table: dict[str, str], code: str) -> str | None:
    candidates = [k for k in table if k.startswith(code[:1])]
    if not candidates:
        return None
    return f"did you mean one of: {', '.join(sorted(candidates)[:5])}?"


def build_ces_series_id(
    *,
    supersector: str,
    industry: str = "00000000",
    datatype: str,
    seasonal: Seasonal = "SA",
) -> dict[str, str | bool]:
    """Construct and validate a CES series ID.

    ``supersector`` is 2 chars (e.g. '00' total nonfarm). ``industry`` is 6
    chars or 8 chars (the full 8-char form pre-pads with the supersector;
    most callers pass the 8-char form like '00000000'). ``datatype`` is 2
    chars (e.g. '01' all-employees, '03' AHE).
    """
    supersector = supersector.strip()
    industry = industry.strip()
    datatype = datatype.strip()
    if supersector not in CES_SUPERSECTORS:
        hint = _suggest(CES_SUPERSECTORS, supersector) or "see bls_list_items(survey='CES')."
        raise ValueError(f"unknown CES supersector {supersector!r}; {hint}")
    # Accept 6-char industry by left-padding with the supersector.
    if len(industry) == 6:
        industry_full = f"{supersector}{industry}"
    else:
        industry_full = industry
    if len(industry_full) != 8:
        raise ValueError(
            f"CES industry must be 6 or 8 chars, got {industry!r} ({len(industry)} chars)"
        )
    if industry_full not in CES_INDUSTRIES:
        hint = _suggest(CES_INDUSTRIES, industry_full) or "see bls_list_items(survey='CES')."
        raise ValueError(f"unknown CES industry {industry_full!r}; {hint}")
    if datatype not in CES_DATATYPES:
        hint = _suggest(CES_DATATYPES, datatype) or "see bls_list_items(survey='CES')."
        raise ValueError(f"unknown CES datatype {datatype!r}; {hint}")
    if seasonal not in _SEASONAL_CODE:
        raise ValueError(f"seasonal must be 'NSA' or 'SA', got {seasonal!r}")

    sid = f"CE{_SEASONAL_CODE[seasonal]}{supersector}{industry_full[2:]}{datatype}"
    return {
        "series_id": sid,
        "survey": "CES",
        "seasonal": seasonal,
        "supersector_code": supersector,
        "supersector": CES_SUPERSECTORS[supersector],
        "industry_code": industry_full,
        "industry": CES_INDUSTRIES[industry_full],
        "datatype_code": datatype,
        "datatype": CES_DATATYPES[datatype],
        "validated": True,
    }


def decode_ces_series_id(series_id: str) -> dict[str, str | bool]:
    """Parse a CES series ID into its components.

    Returns ``{"decoded": True, ...}`` on success or
    ``{"decoded": False, "reason": ...}`` otherwise.
    """
    sid = (series_id or "").strip().upper()
    if len(sid) != 13 or sid[:2] not in ("CE",) or sid[2] not in ("S", "U"):
        return {"decoded": False, "reason": f"not a CES series ID: {series_id!r}"}
    seasonal = _SEASONAL_INVERSE[sid[2]]
    supersector = sid[3:5]
    industry = sid[3:11]  # 8-char industry includes the supersector
    datatype = sid[11:13]
    return {
        "decoded": True,
        "series_id": sid,
        "survey": "CES",
        "seasonal": seasonal,
        "supersector_code": supersector,
        "supersector": CES_SUPERSECTORS.get(supersector, "(unknown supersector)"),
        "industry_code": industry,
        "industry": CES_INDUSTRIES.get(industry, "(unknown industry)"),
        "datatype_code": datatype,
        "datatype": CES_DATATYPES.get(datatype, "(unknown datatype)"),
    }
