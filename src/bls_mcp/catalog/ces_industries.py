"""CES industry / supersector codes.

In a CES series ID (e.g. CES0500000003) the layout is:
  CES + S(SA)/U(NSA) + supersector(2) + industry(6) + datatype(2)

This module covers the supersector-level (industry='000000') codes that
most macro work uses. Detailed 6-digit industry codes are far more
numerous and refreshed via ``scripts/refresh_bls_catalog.py``.

Source: https://download.bls.gov/pub/time.series/ce/ce.supersector
"""

from __future__ import annotations

from typing import Final

# 2-digit supersector code → name.
CES_SUPERSECTORS: Final[dict[str, str]] = {
    "00": "Total nonfarm",
    "05": "Total private",
    "06": "Goods-producing",
    "07": "Service-providing",
    "08": "Private service-providing",
    "10": "Mining and logging",
    "20": "Construction",
    "30": "Manufacturing",
    "31": "Durable goods manufacturing",
    "32": "Nondurable goods manufacturing",
    "40": "Trade, transportation, and utilities",
    "41": "Wholesale trade",
    "42": "Retail trade",
    "43": "Transportation and warehousing",
    "44": "Utilities",
    "50": "Information",
    "55": "Financial activities",
    "60": "Professional and business services",
    "65": "Education and health services",
    "70": "Leisure and hospitality",
    "80": "Other services",
    "90": "Government",
}

# Most-requested 6-digit industry codes for headline reporting. Codes for
# "all employees in this supersector" are <supersector>000000 (e.g.
# 00000000 for total nonfarm, 30000000 for manufacturing).
CES_INDUSTRIES: Final[dict[str, str]] = {
    "00000000": "Total nonfarm",
    "05000000": "Total private",
    "06000000": "Goods-producing",
    "07000000": "Service-providing",
    "08000000": "Private service-providing",
    "10000000": "Mining and logging",
    "20000000": "Construction",
    "30000000": "Manufacturing",
    "31000000": "Durable goods manufacturing",
    "32000000": "Nondurable goods manufacturing",
    "40000000": "Trade, transportation, and utilities",
    "41420000": "Wholesale trade",
    "42000000": "Retail trade",
    "43000000": "Transportation and warehousing",
    "44220000": "Utilities",
    "50000000": "Information",
    "55000000": "Financial activities",
    "60000000": "Professional and business services",
    "65000000": "Education and health services",
    "70000000": "Leisure and hospitality",
    "80000000": "Other services",
    "90000000": "Government",
}
