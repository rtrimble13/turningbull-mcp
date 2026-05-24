"""Embedded BLS code tables and curated series catalog.

Discovery tools read from here rather than hitting the BLS download
endpoints at runtime — keeps the server hermetic and key-less for
discovery. The data is refreshed offline by ``scripts/refresh_bls_catalog.py``.
"""

from __future__ import annotations

from .popular import POPULAR_SERIES
from .surveys import SURVEY_PREFIXES, Survey, classify_series_id

__all__ = [
    "POPULAR_SERIES",
    "SURVEY_PREFIXES",
    "Survey",
    "classify_series_id",
]
