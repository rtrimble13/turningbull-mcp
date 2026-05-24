"""CPI area codes (subset).

Source: https://download.bls.gov/pub/time.series/cu/cu.area (filtered to
the metro areas and regions most often referenced in macro work). To
regenerate the full list, run ``scripts/refresh_bls_catalog.py``.
"""

from __future__ import annotations

from typing import Final

# code -> human-readable name. Codes are 4 chars in the CPI series ID.
CPI_AREAS: Final[dict[str, str]] = {
    "0000": "U.S. city average",
    # Regions
    "0100": "Northeast",
    "0110": "Northeast — size class A (large metros)",
    "0200": "Midwest",
    "0210": "Midwest — size class A",
    "0300": "South",
    "0310": "South — size class A",
    "0400": "West",
    "0410": "West — size class A",
    # Size classes
    "0001": "Size class A — over 2.5 million",
    "0002": "Size class B/C — under 2.5 million",
    # Major metros — A-size
    "A101": "New York-Newark-Jersey City, NY-NJ-PA",
    "A102": "Philadelphia-Camden-Wilmington, PA-NJ-DE-MD",
    "A103": "Boston-Cambridge-Newton, MA-NH",
    "A104": "Pittsburgh, PA",
    "A207": "Chicago-Naperville-Elgin, IL-IN-WI",
    "A208": "Detroit-Warren-Dearborn, MI",
    "A210": "Minneapolis-St. Paul-Bloomington, MN-WI",
    "A311": "Washington-Arlington-Alexandria, DC-VA-MD-WV",
    "A312": "Baltimore-Columbia-Towson, MD",
    "A316": "Miami-Fort Lauderdale-West Palm Beach, FL",
    "A317": "Tampa-St. Petersburg-Clearwater, FL",
    "A318": "Atlanta-Sandy Springs-Roswell, GA",
    "A319": "Houston-The Woodlands-Sugar Land, TX",
    "A320": "Dallas-Fort Worth-Arlington, TX",
    "A421": "Los Angeles-Long Beach-Anaheim, CA",
    "A422": "San Francisco-Oakland-Hayward, CA",
    "A423": "Seattle-Tacoma-Bellevue, WA",
    "A425": "Phoenix-Mesa-Scottsdale, AZ",
    "A429": "Riverside-San Bernardino-Ontario, CA",
    "A433": "San Diego-Carlsbad, CA",
    "A435": "Denver-Aurora-Lakewood, CO",
    "A437": "Urban Hawaii",
    "A439": "Urban Alaska",
}
