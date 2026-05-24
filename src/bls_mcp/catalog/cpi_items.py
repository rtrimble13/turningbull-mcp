"""CPI item codes (curated subset of the most-requested items).

Source: https://download.bls.gov/pub/time.series/cu/cu.item

Item codes are variable-length suffixes on a CPI series ID. The most-used
entries are aggregates (SA0, SAF1, SAH1, ...) plus a few common detailed
items. To regenerate the full list (hundreds of entries), run
``scripts/refresh_bls_catalog.py``.
"""

from __future__ import annotations

from typing import Final

CPI_ITEMS: Final[dict[str, str]] = {
    # Headline aggregates
    "SA0":    "All items",
    "SA0L1":  "All items less food",
    "SA0L1E": "All items less food and energy (Core CPI)",
    "SA0L2":  "All items less shelter",
    "SA0LE":  "All items less energy",
    "SA0E":   "Energy",
    # Major group aggregates
    "SAF1":   "Food",
    "SAF11":  "Food at home",
    "SEFV":   "Food away from home",
    "SAH":    "Housing",
    "SAH1":   "Shelter",
    "SAH2":   "Fuels and utilities",
    "SAH3":   "Household furnishings and operations",
    "SAA":    "Apparel",
    "SAT":    "Transportation",
    "SAT1":   "Private transportation",
    "SAT2":   "Public transportation",
    "SAM":    "Medical care",
    "SAM1":   "Medical care commodities",
    "SAM2":   "Medical care services",
    "SAR":    "Recreation",
    "SAE":    "Education and communication",
    "SAS":    "Services",
    "SAS2":   "Transportation services",
    "SAS4":   "Medical care services",
    "SASLE":  "Services less energy services",
    "SAC":    "Commodities",
    "SACL1E": "Commodities less food and energy commodities",
    # Detailed shelter items
    "SEHA":   "Rent of primary residence",
    "SEHC":   "Owners' equivalent rent of residences",
    "SEHC01": "Owners' equivalent rent of primary residence",
    "SEHF":   "Lodging away from home",
    # Detailed transportation items
    "SETA":   "Private transportation",
    "SETA01": "New vehicles",
    "SETA02": "Used cars and trucks",
    "SETB":   "Motor fuel",
    "SETB01": "Gasoline (all types)",
    "SETB02": "Other motor fuels",
    # Detailed energy items
    "SEHE":   "Energy services",
    "SEHE01": "Electricity",
    "SEHE02": "Utility (piped) gas service",
    # Detailed food items
    "SEFR":   "Food at restaurants",
}
