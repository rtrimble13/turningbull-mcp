"""LAUS measure codes.

Last 2 chars of a LAUS series ID.
Source: https://download.bls.gov/pub/time.series/la/la.measure
"""

from __future__ import annotations

from typing import Final

LAUS_MEASURES: Final[dict[str, str]] = {
    "03": "Unemployment rate",
    "04": "Unemployment",          # level
    "05": "Employment",            # level
    "06": "Labor force",           # level
    "07": "Employment-population ratio",
    "08": "Labor force participation rate",
}
