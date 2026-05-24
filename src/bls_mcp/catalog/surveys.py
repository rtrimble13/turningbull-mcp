"""BLS survey enum and series-ID prefix routing.

A BLS series ID's first 2-3 characters identify the source survey. This
module provides the enum, the prefix → survey map, and a single
``classify_series_id`` helper used by the discovery and builder tools.
"""

from __future__ import annotations

from enum import Enum


class Survey(str, Enum):
    """BLS surveys exposed by the public data API."""

    CPI = "CPI"           # Consumer Price Index (prefixes CU, CW, SU)
    PPI = "PPI"           # Producer Price Index (WP, PC, WD)
    CES = "CES"           # Current Employment Statistics — establishment (CE)
    CPS = "CPS"           # Current Population Survey — household (LN)
    LAUS = "LAUS"         # Local Area Unemployment Statistics (LA)
    JOLTS = "JOLTS"       # Job Openings and Labor Turnover Survey (JT)
    OEWS = "OEWS"         # Occupational Employment and Wage Statistics (OE)
    ECI = "ECI"           # Employment Cost Index (CI)
    ECEC = "ECEC"         # Employer Costs for Employee Compensation (CM)
    PRODUCTIVITY = "PRODUCTIVITY"  # Productivity and Costs (PR)
    IMPORT_EXPORT = "IMPORT_EXPORT"  # International prices (EI, EU)
    QCEW = "QCEW"         # Quarterly Census of Employment and Wages (EN)
    UNKNOWN = "UNKNOWN"


# Series-ID prefix routing. Order matters: longer prefixes are tried first.
SURVEY_PREFIXES: tuple[tuple[str, Survey], ...] = (
    # CPI variants — must be checked before any 2-char prefix.
    ("CUU", Survey.CPI),
    ("CUS", Survey.CPI),
    ("CWU", Survey.CPI),
    ("CWS", Survey.CPI),
    ("SUU", Survey.CPI),    # C-CPI-U (chained)
    # PPI variants
    ("WPU", Survey.PPI),
    ("WPS", Survey.PPI),
    ("PCU", Survey.PPI),    # PPI industry
    ("WDU", Survey.PPI),    # PPI commodity
    # Establishment / household / area
    ("CES", Survey.CES),
    ("CEU", Survey.CES),
    ("LNS", Survey.CPS),
    ("LNU", Survey.CPS),
    ("LAS", Survey.LAUS),
    ("LAU", Survey.LAUS),
    # Other surveys
    ("JTS", Survey.JOLTS),
    ("JTU", Survey.JOLTS),
    ("OE",  Survey.OEWS),
    ("CIS", Survey.ECI),
    ("CIU", Survey.ECI),
    ("CMU", Survey.ECEC),
    ("PRS", Survey.PRODUCTIVITY),
    ("PRU", Survey.PRODUCTIVITY),
    ("EIU", Survey.IMPORT_EXPORT),
    ("ENU", Survey.QCEW),
)


def classify_series_id(series_id: str) -> Survey:
    """Return the survey a BLS series ID belongs to, or ``Survey.UNKNOWN``.

    Match is greedy on prefix length to disambiguate (e.g. CUS before CU).
    """
    sid = (series_id or "").strip().upper()
    if not sid:
        return Survey.UNKNOWN
    # Sort by length desc so longer-prefix matches win.
    for prefix, survey in sorted(SURVEY_PREFIXES, key=lambda x: -len(x[0])):
        if sid.startswith(prefix):
            return survey
    return Survey.UNKNOWN
