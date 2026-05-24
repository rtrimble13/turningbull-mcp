"""CES data-type codes.

The last 2 characters of a CES series ID identify the measure.
Source: https://download.bls.gov/pub/time.series/ce/ce.datatype
"""

from __future__ import annotations

from typing import Final

CES_DATATYPES: Final[dict[str, str]] = {
    "01": "All employees, thousands",
    "02": "Average weekly hours of all employees",
    "03": "Average hourly earnings of all employees, dollars",
    "06": "Production and nonsupervisory employees, thousands",
    "07": "Average weekly hours of production and nonsupervisory employees",
    "08": "Average hourly earnings of production and nonsupervisory employees, dollars",
    "10": "Women employees, thousands",
    "11": "Average weekly earnings of all employees, dollars",
    "12": "Average weekly overtime hours of all employees (mfg only)",
    "30": "Average weekly earnings of production and nonsupervisory employees, dollars",
    "32": "Average weekly overtime hours of production employees (mfg only)",
}
