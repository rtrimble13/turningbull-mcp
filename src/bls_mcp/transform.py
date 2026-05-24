"""BLS response reshaping: period -> ISO date, value coercion, series shape.

Kept pure (no I/O, no httpx) so unit tests can exercise it directly.
"""

from __future__ import annotations

from typing import Any

# All four calculation periods that BLS returns when calculations=true.
CALCULATION_PERIODS: tuple[int, ...] = (1, 3, 6, 12)

# Catalog fields surfaced under reshape_series()["metadata"]. Each entry is
# the public key followed by the BLS field aliases (BLS occasionally renames
# between releases — accept any match).
_METADATA_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("survey_name", ("survey_name", "surveyName")),
    ("survey_abbreviation", ("survey_abbreviation", "surveyAbbreviation")),
    ("area", ("area",)),
    ("area_code", ("area_code", "areaCode")),
    ("item", ("item",)),
    ("item_code", ("item_code", "itemCode")),
    ("industry", ("industry",)),
    ("industry_code", ("industry_code", "industryCode")),
    ("occupation", ("occupation",)),
    ("state", ("state",)),
    ("periodicity_code", ("periodicity_code", "periodicityCode")),
    ("begin_year", ("begin_year", "beginYear")),
    ("end_year", ("end_year", "endYear")),
    ("begin_period", ("begin_period", "beginPeriod")),
    ("end_period", ("end_period", "endPeriod")),
    ("commerce_industry", ("commerce_industry", "commerceIndustry")),
    ("footnote_codes", ("footnote_codes", "footnoteCodes")),
)


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


def _coerce_bool(raw: Any) -> bool:
    """BLS reports ``latest`` as the string ``"true"``."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() == "true"
    return False


def _reshape_observation(obs: dict[str, Any]) -> dict[str, Any]:
    year = obs.get("year")
    period = obs.get("period", "")
    calcs = obs.get("calculations")
    out: dict[str, Any] = {
        "date": period_to_iso_date(year, period),
        "year": str(year) if year is not None else None,
        "period": period,
        "period_name": obs.get("periodName"),
        "value": coerce_value(obs.get("value")),
        "footnotes": obs.get("footnotes") or [],
        "latest": _coerce_bool(obs.get("latest")),
    }
    for p in CALCULATION_PERIODS:
        out[f"net_change_{p}m"] = _calc(calcs, "net_changes", str(p))
        out[f"pct_change_{p}m"] = _calc(calcs, "pct_changes", str(p))
    aspects = obs.get("aspects")
    if aspects:
        out["aspects"] = aspects
    return out


def _catalog_field(catalog: dict[str, Any] | None, *keys: str) -> str | None:
    if not isinstance(catalog, dict):
        return None
    for k in keys:
        v = catalog.get(k)
        if v:
            return str(v)
    return None


def _build_metadata(catalog: dict[str, Any] | None) -> dict[str, str] | None:
    """Return the full catalog metadata block, or None when catalog is absent."""
    if not isinstance(catalog, dict):
        return None
    metadata: dict[str, str] = {}
    for public_key, aliases in _METADATA_FIELDS:
        val = _catalog_field(catalog, *aliases)
        if val is not None:
            metadata[public_key] = val
    return metadata or None


def filter_calculation_periods(
    observations: list[dict[str, Any]], periods: list[int]
) -> list[dict[str, Any]]:
    """Drop calculation columns whose period isn't in ``periods``.

    Operates on a list of reshaped observations. Returns new dicts; does not
    mutate inputs. An empty ``periods`` list drops every calculation column.
    """
    keep = {int(p) for p in periods}
    out: list[dict[str, Any]] = []
    for obs in observations:
        new = dict(obs)
        for p in CALCULATION_PERIODS:
            if p in keep:
                continue
            new.pop(f"net_change_{p}m", None)
            new.pop(f"pct_change_{p}m", None)
        out.append(new)
    return out


def reshape_series(
    series_obj: dict[str, Any], *, expose_metadata: bool = True
) -> dict[str, Any]:
    """Convert one BLS ``Results.series[i]`` entry to the public shape.

    Observations are sorted oldest→newest. Catalog fields fall back to
    ``None`` when ``catalog=true`` was not requested or the field is absent.
    The full catalog block is surfaced under ``metadata`` when
    ``expose_metadata`` is true; legacy top-level keys (``title``, ``units``,
    ``seasonal_adjustment``) are always populated for back-compat.
    """
    catalog = series_obj.get("catalog")
    raw_data = series_obj.get("data") or []
    observations = [_reshape_observation(o) for o in raw_data]
    observations.sort(key=lambda r: r["date"])

    result: dict[str, Any] = {
        "series_id": series_obj.get("seriesID"),
        "title": _catalog_field(catalog, "series_title", "seriesTitle"),
        "units": _catalog_field(catalog, "measure_data_type", "data_type_text"),
        "seasonal_adjustment": _catalog_field(catalog, "seasonality"),
        "observations": observations,
    }
    if expose_metadata:
        metadata = _build_metadata(catalog)
        if metadata:
            result["metadata"] = metadata
    if not observations:
        result["note"] = (
            "No observations returned for this series in the requested window. "
            "Verify the series ID and date range."
        )
    return result
