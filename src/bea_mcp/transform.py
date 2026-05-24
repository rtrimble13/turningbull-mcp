"""Pure reshaping helpers for BEA API responses.

BEA's GetData responses are a flat list of records (``Results.Data``) where
each record has a ``TimePeriod`` like ``2024``, ``2024Q1``, ``2024M01``,
plus a ``DataValue`` string. These helpers normalize them to a friendly
shape: ISO date, numeric value, and a stable column ordering.
"""

from __future__ import annotations

import re
from typing import Any

PERIOD_QUARTER_RE = re.compile(r"^(\d{4})Q([1-4])$")
PERIOD_MONTH_RE = re.compile(r"^(\d{4})M(\d{2})$")
PERIOD_YEAR_RE = re.compile(r"^(\d{4})$")


def time_period_to_iso(period: str | None) -> str | None:
    """Turn a BEA ``TimePeriod`` token into an ISO date string.

    - ``2024``      → ``2024-01-01``
    - ``2024Q1``    → ``2024-01-01`` (start of quarter)
    - ``2024M01``   → ``2024-01-01``
    - Anything else is returned unchanged so the caller can still see it.
    """
    if not period:
        return None
    s = str(period).strip()
    m = PERIOD_MONTH_RE.match(s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    m = PERIOD_QUARTER_RE.match(s)
    if m:
        month = {"1": "01", "2": "04", "3": "07", "4": "10"}[m.group(2)]
        return f"{m.group(1)}-{month}-01"
    m = PERIOD_YEAR_RE.match(s)
    if m:
        return f"{m.group(1)}-01-01"
    return s


def _coerce_value(v: Any) -> float | None:
    """Best-effort numeric parse of BEA's string DataValue.

    BEA returns "1,234.5" (comma-grouped), "(D)" (suppressed), and "(NA)".
    We strip commas and return ``None`` for non-numeric markers.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s.startswith("(") or s in {"NA", "N/A", "..."}:
        return None
    try:
        return float(s.replace(",", ""))
    except (TypeError, ValueError):
        return None


def flatten_data(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize BEA ``Results.Data`` rows.

    Adds ``date`` (ISO) and ``value`` (numeric) alongside every original
    field BEA returned. The original ``TimePeriod`` and ``DataValue``
    columns are preserved so the caller can audit the parse if needed.
    """
    out: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        normalized = dict(r)
        normalized["date"] = time_period_to_iso(r.get("TimePeriod"))
        normalized["value"] = _coerce_value(r.get("DataValue"))
        out.append(normalized)
    return out


def latest_by_series(rows: list[dict[str, Any]], key: str = "SeriesCode") -> dict[str, dict[str, Any]]:
    """For each distinct ``key`` (default SeriesCode) return the row with the
    latest ``date`` (ISO). Useful for composite snapshots.
    """
    by_key: dict[str, dict[str, Any]] = {}
    for r in rows:
        k = r.get(key)
        if k is None:
            continue
        prev = by_key.get(k)
        if prev is None or (r.get("date") or "") > (prev.get("date") or ""):
            by_key[k] = r
    return by_key
