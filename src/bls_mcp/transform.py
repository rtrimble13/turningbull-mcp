"""BLS response reshaping: period -> ISO date, value coercion, series shape.

Kept pure (no I/O, no httpx) so unit tests can exercise it directly.
"""

from __future__ import annotations

from typing import Any


def period_to_iso_date(year: str | int, period: str) -> str:
    """Convert a BLS ``(year, period)`` pair to an ISO YYYY-MM-DD date.

    - ``M01``–``M12`` → first day of that month.
    - ``M13``         → year-end annual average; mapped to Dec 31 of ``year``.
    - ``Q01``–``Q04`` → first day of the quarter (Jan/Apr/Jul/Oct 1).
    - ``S01``/``S02`` → semiannual; first day of H1 (Jan 1) or H2 (Jul 1).
    - ``A01``         → annual; mapped to Jan 1 of ``year``.

    Unknown periods raise ``ValueError`` so callers see a real error rather
    than silently mis-dating an observation.
    """
    y = int(year)
    p = (period or "").strip().upper()
    if not p:
        raise ValueError(f"empty period for year {year!r}")

    code, _, rest = p[0], p[1:2], p[1:]
    try:
        n = int(rest)
    except ValueError as exc:
        raise ValueError(f"unrecognized BLS period {period!r}") from exc

    if code == "M":
        if n == 13:
            # M13 is the annual-average pseudo-period BLS uses when
            # annualaverage=true is requested. Anchor it to year-end.
            return f"{y:04d}-12-31"
        if 1 <= n <= 12:
            return f"{y:04d}-{n:02d}-01"
        raise ValueError(f"month period out of range: {period!r}")
    if code == "Q":
        if 1 <= n <= 4:
            month = (n - 1) * 3 + 1
            return f"{y:04d}-{month:02d}-01"
        raise ValueError(f"quarter period out of range: {period!r}")
    if code == "S":
        if n == 1:
            return f"{y:04d}-01-01"
        if n == 2:
            return f"{y:04d}-07-01"
        raise ValueError(f"semiannual period out of range: {period!r}")
    if code == "A":
        return f"{y:04d}-01-01"
    raise ValueError(f"unrecognized BLS period {period!r}")


def coerce_value(raw: Any) -> float | None:
    """BLS reports ``"-"`` and empty strings for missing values."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _calc(calculations: dict[str, Any] | None, kind: str, key: str) -> float | None:
    if not isinstance(calculations, dict):
        return None
    bucket = calculations.get(kind)
    if not isinstance(bucket, dict):
        return None
    return coerce_value(bucket.get(key))


def _reshape_observation(obs: dict[str, Any]) -> dict[str, Any]:
    year = obs.get("year")
    period = obs.get("period", "")
    return {
        "date": period_to_iso_date(year, period),
        "year": str(year) if year is not None else None,
        "period": period,
        "period_name": obs.get("periodName"),
        "value": coerce_value(obs.get("value")),
        "footnotes": obs.get("footnotes") or [],
        "net_change_1m": _calc(obs.get("calculations"), "net_changes", "1"),
        "pct_change_1m": _calc(obs.get("calculations"), "pct_changes", "1"),
        "pct_change_12m": _calc(obs.get("calculations"), "pct_changes", "12"),
    }


def _catalog_field(catalog: dict[str, Any] | None, *keys: str) -> str | None:
    if not isinstance(catalog, dict):
        return None
    for k in keys:
        v = catalog.get(k)
        if v:
            return str(v)
    return None


def reshape_series(series_obj: dict[str, Any]) -> dict[str, Any]:
    """Convert one BLS ``Results.series[i]`` entry to the public shape.

    Observations are sorted oldest→newest. Catalog fields fall back to
    ``None`` when ``catalog=true`` was not requested or the field is absent.
    """
    catalog = series_obj.get("catalog")
    raw_data = series_obj.get("data") or []
    observations = [_reshape_observation(o) for o in raw_data]
    observations.sort(key=lambda r: r["date"])

    result: dict[str, Any] = {
        "series_id": series_obj.get("seriesID"),
        "title": _catalog_field(catalog, "series_title"),
        "units": _catalog_field(catalog, "measure_data_type", "data_type_text"),
        "seasonal_adjustment": _catalog_field(catalog, "seasonality"),
        "observations": observations,
    }
    if not observations:
        result["note"] = (
            "No observations returned for this series in the requested window. "
            "Verify the series ID and date range."
        )
    return result
