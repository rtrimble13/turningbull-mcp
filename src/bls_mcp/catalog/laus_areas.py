"""LAUS area codes — states and major metros.

A LAUS series ID's area code is 15 chars. State series use ST<FIPS>00000000000.
Full county-level codes are voluminous (~8000+ entries) and refreshed via
``scripts/refresh_bls_catalog.py``.

Source: https://download.bls.gov/pub/time.series/la/la.area
"""

from __future__ import annotations

from typing import Final

# State 2-digit FIPS codes -> name. Build a LAUS state series id with
#   "LA" + seasonal + "ST" + fips + "00000000000" + measure
# e.g. LAST480000000000003 = TX unemployment rate, NSA.
LAUS_STATES: Final[dict[str, str]] = {
    "01": "Alabama",
    "02": "Alaska",
    "04": "Arizona",
    "05": "Arkansas",
    "06": "California",
    "08": "Colorado",
    "09": "Connecticut",
    "10": "Delaware",
    "11": "District of Columbia",
    "12": "Florida",
    "13": "Georgia",
    "15": "Hawaii",
    "16": "Idaho",
    "17": "Illinois",
    "18": "Indiana",
    "19": "Iowa",
    "20": "Kansas",
    "21": "Kentucky",
    "22": "Louisiana",
    "23": "Maine",
    "24": "Maryland",
    "25": "Massachusetts",
    "26": "Michigan",
    "27": "Minnesota",
    "28": "Mississippi",
    "29": "Missouri",
    "30": "Montana",
    "31": "Nebraska",
    "32": "Nevada",
    "33": "New Hampshire",
    "34": "New Jersey",
    "35": "New Mexico",
    "36": "New York",
    "37": "North Carolina",
    "38": "North Dakota",
    "39": "Ohio",
    "40": "Oklahoma",
    "41": "Oregon",
    "42": "Pennsylvania",
    "44": "Rhode Island",
    "45": "South Carolina",
    "46": "Tennessee",
    "47": "Tennessee",
    "48": "Texas",
    "49": "Utah",
    "50": "Vermont",
    "51": "Virginia",
    "53": "Washington",
    "54": "West Virginia",
    "55": "Wisconsin",
    "56": "Wyoming",
    "72": "Puerto Rico",
}

# Pre-built state area codes (full 15-char form) — convenience for the builder.
LAUS_STATE_AREA_CODES: Final[dict[str, str]] = {
    name: f"ST{fips}00000000000" for fips, name in LAUS_STATES.items()
}
